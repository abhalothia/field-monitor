"""Native field-capture boundary for reviewed, allocation-scoped observations.

This is deliberately not a chat or upload API.  A manager issues a short-lived
opaque pass for one ready field-information request and one published template.
The field browser may submit one structured candidate under that pass; it can
never choose a person, crop allocation, reviewer, work transition, or an
agronomic conclusion.  A manager later accepts/rejects the candidate through
the canonical season/template service.
"""

import base64
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import hmac
import json
import secrets
from pathlib import PurePath
from typing import Any, Optional, Tuple

from ffl.domain.models import FieldCaptureCandidate, FieldCapturePass, SignalTemplate
from ffl.persistence import repository
from ffl.services import evidence, season, templates
from ffl.services.allocation_relationship_coverage import active_person_allocation_coverage


class FieldCaptureUnavailable(ValueError):
    """The required server-owned field identity authority is absent."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(value: str, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("{0} is required".format(field_name))
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("{0} must be an ISO-8601 timestamp".format(field_name)) from error
    if parsed.tzinfo is None:
        raise ValueError("{0} must include a timezone".format(field_name))
    return parsed.astimezone(timezone.utc)


def _secret_digest(signing_key: str, token: str) -> str:
    return hmac.new(signing_key.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()


def _require_signing_key(signing_key: Optional[str]) -> str:
    if not isinstance(signing_key, str) or len(signing_key.strip()) < 32:
        raise FieldCaptureUnavailable("field capture signing authority is not configured")
    return signing_key


def _template_by_id(conn, template_id: str, template_version: int):
    row = conn.execute(
        "SELECT * FROM signal_templates WHERE id = ? AND version = ?", (template_id, template_version)
    ).fetchone()
    if row is None:
        raise ValueError("signal template ID and version do not match")
    if row["status"] != "published":
        raise ValueError("signal template must be published")
    return row


def _request_and_assignment(conn, capture_pass):
    request = repository.get_field_information_request(conn, capture_pass.field_information_request_id)
    if request is None:
        raise ValueError("field information request does not exist")
    allocation = repository.get_crop_allocation(conn, request.allocation_id)
    if allocation is None:
        raise ValueError("crop allocation does not exist")
    if request.status != "ready":
        raise ValueError("field capture request is not ready")
    coverage = active_person_allocation_coverage(conn, request.target_person_id, request.allocation_id)
    if not coverage.eligible:
        raise ValueError("target person lacks an active explicit relationship to the crop allocation")
    return request, allocation


def issue_capture_pass(
    conn, signing_key: Optional[str], field_information_request_id: str, signal_template_id: str,
    signal_template_version: int, issued_by_person_id: str, expires_at: str,
) -> Tuple[FieldCapturePass, str]:
    """Issue one opaque field capability after all scope is verified server-side."""
    secret = _require_signing_key(signing_key)
    request = repository.get_field_information_request(conn, field_information_request_id)
    if request is None:
        raise ValueError("field information request does not exist")
    if request.status != "ready":
        raise ValueError("field capture pass requires a ready field information request")
    coverage = active_person_allocation_coverage(conn, request.target_person_id, request.allocation_id)
    if not coverage.eligible:
        raise ValueError("target person lacks an active explicit relationship to the crop allocation")
    _template_by_id(conn, signal_template_id, signal_template_version)
    if _parse_timestamp(expires_at, "expires_at") <= _now():
        raise ValueError("expires_at must be in the future")

    token = secrets.token_urlsafe(32)
    return (
        repository.create_field_capture_pass(
            conn, request.id, signal_template_id, signal_template_version,
            _secret_digest(secret, token), issued_by_person_id, expires_at,
        ),
        token,
    )


def resolve_capture_pass(conn, signing_key: Optional[str], token: str, *, allow_used: bool = False):
    secret = _require_signing_key(signing_key)
    if not isinstance(token, str) or len(token) < 32 or len(token) > 256:
        raise ValueError("field capture authorization is invalid")
    capture_pass = repository.get_field_capture_pass_by_token_hash(conn, _secret_digest(secret, token))
    if capture_pass is None:
        raise ValueError("field capture authorization is invalid")
    if capture_pass.status != "active" and not (allow_used and capture_pass.status == "used"):
        raise ValueError("field capture authorization is no longer active")
    if _parse_timestamp(capture_pass.expires_at, "expires_at") <= _now():
        raise ValueError("field capture authorization has expired")
    request, allocation = _request_and_assignment(conn, capture_pass)
    template = _template_by_id(conn, capture_pass.signal_template_id, capture_pass.signal_template_version)
    return capture_pass, request, allocation, template


def capture_context(conn, signing_key: Optional[str], token: str) -> dict:
    """Return the minimal display context for the pass holder, never contact data."""
    _capture_pass, request, allocation, template = resolve_capture_pass(conn, signing_key, token)
    block = conn.execute(
        "SELECT name FROM operational_blocks WHERE id = ?", (allocation.operational_block_id,)
    ).fetchone()
    return {
        "assignment": {
            "allocation": {
                "block_name": block["name"] if block is not None else "Assigned field",
                "crop_name": allocation.crop_name,
                "cultivar": allocation.cultivar,
            },
            "request": {
                "kind": request.request_kind,
                "evidence_required": request.evidence_required,
                "due_at": request.due_at,
                "copy_en": request.request_copy_en,
                "copy_hi": request.request_copy_hi,
            },
            "template": {
                "name": template["name"],
                "version": template["version"],
                "fields": json.loads(template["fields_json"]),
            },
        }
    }


def _validated_values(template_row, values: Any) -> dict:
    if not isinstance(values, dict):
        raise ValueError("values must be an object")
    template = SignalTemplate(
        template_row["id"], template_row["name"], template_row["version"], template_row["status"],
        json.loads(template_row["fields_json"]),
        template_row["owner_id"], template_row["published_at"],
    )
    return templates.validate_signal_payload(template, values)


def _decode_evidence(payload: Any) -> tuple[bytes, str, Optional[str]]:
    if not isinstance(payload, dict):
        raise ValueError("evidence must be an object")
    encoded = payload.get("content_base64")
    media_type = payload.get("media_type")
    filename = payload.get("filename")
    if not isinstance(encoded, str) or not encoded:
        raise ValueError("evidence content is required")
    if not isinstance(media_type, str) or not media_type.startswith("image/"):
        raise ValueError("field capture evidence must be an image")
    if filename is not None:
        if not isinstance(filename, str) or len(filename) > 180:
            raise ValueError("evidence filename is invalid")
        filename = PurePath(filename).name or None
    try:
        content = base64.b64decode(encoded.encode("ascii"), validate=True)
    except (UnicodeEncodeError, ValueError) as error:
        raise ValueError("evidence content must be valid base64") from error
    if not content:
        raise ValueError("evidence content is required")
    return content, media_type, filename


def submit_capture_candidate(
    conn, signing_key: Optional[str], token: str, idempotency_key: str, observed_at: str,
    values: Any, evidence_payload: Any, evidence_store,
) -> tuple[FieldCaptureCandidate, bool]:
    """Retain approved-format proof and create one review-only candidate.

    The caller does not submit the person, allocation, template, or evidence
    artifact ID.  Those all come from the signed pass and retained bytes.
    """
    capture_pass, request, allocation, template = resolve_capture_pass(
        conn, signing_key, token, allow_used=True
    )
    existing = repository.get_field_capture_candidate_by_pass_and_idempotency(
        conn, capture_pass.id, idempotency_key
    )
    if existing is not None:
        return existing, False
    if capture_pass.status != "active":
        raise ValueError("field capture authorization is no longer active")
    observed_at = _parse_timestamp(observed_at, "observed_at").isoformat()
    validated_values = _validated_values(template, values)

    artifact = None
    if evidence_payload is not None:
        content, media_type, filename = _decode_evidence(evidence_payload)
        artifact = evidence.retain_evidence(
            conn, content, media_type, filename, created_by_person_id=request.target_person_id,
            store=evidence_store,
        )
    if request.evidence_required and artifact is None:
        raise ValueError("this field request requires retained evidence")

    try:
        with conn:
            candidate = repository.create_field_capture_candidate(
                conn, request.id, capture_pass.id, allocation.id, request.target_person_id,
                template["id"], template["version"], observed_at, validated_values,
                artifact.id if artifact is not None else None, idempotency_key,
            )
            used = conn.execute(
                "UPDATE field_capture_passes SET status = 'used' WHERE id = ? AND status = 'active'",
                (capture_pass.id,),
            )
            if used.rowcount != 1 and candidate.status == "review":
                raise ValueError("field capture authorization is no longer active")
    except Exception:
        raise
    return candidate, True


def accept_capture_candidate(conn, candidate_id: str, reviewer_id: str):
    """Explicitly publish one valid candidate through the canonical season service."""
    candidate = repository.get_field_capture_candidate(conn, candidate_id)
    if candidate is None:
        raise ValueError("field capture candidate does not exist")
    if candidate.status == "accepted":
        return candidate
    if candidate.status != "review":
        raise ValueError("field capture candidate cannot be accepted")
    request = repository.get_field_information_request(conn, candidate.field_information_request_id)
    if request is None:
        raise ValueError("field information request does not exist")
    if request.evidence_required and candidate.evidence_artifact_id is None:
        raise ValueError("this field request requires retained evidence")
    reviewed_at = _now().isoformat()
    with conn:
        claimed = repository.claim_field_capture_candidate_for_acceptance(conn, candidate.id)
        if claimed is None:
            current = repository.get_field_capture_candidate(conn, candidate.id)
            if current is not None and current.status == "accepted":
                return current
            raise ValueError("field capture candidate cannot be accepted")
        signal = season.record_field_signal(
            conn, claimed.allocation_id, claimed.signal_template_id,
            claimed.signal_template_version, claimed.observed_at, claimed.actor_person_id,
            claimed.values, claimed.evidence_artifact_id, status="submitted", commit=False,
        )
        accepted = repository.accept_field_capture_candidate(
            conn, claimed.id, reviewer_id, signal.id, reviewed_at
        )
    return accepted


def reject_capture_candidate(conn, candidate_id: str, reviewer_id: str):
    candidate = repository.get_field_capture_candidate(conn, candidate_id)
    if candidate is None:
        raise ValueError("field capture candidate does not exist")
    if candidate.status == "rejected":
        return candidate
    if candidate.status != "review":
        raise ValueError("field capture candidate cannot be rejected")
    return repository.reject_field_capture_candidate(conn, candidate.id, reviewer_id, _now().isoformat())


def field_candidate_manager_detail(conn, candidate_id: str) -> dict:
    candidate = repository.get_field_capture_candidate(conn, candidate_id)
    if candidate is None:
        raise ValueError("field capture candidate does not exist")
    actor = repository.get_person(conn, candidate.actor_person_id)
    artifact = repository.get_evidence_artifact(conn, candidate.evidence_artifact_id) if candidate.evidence_artifact_id else None
    detail = asdict(candidate)
    # Storage references and content hashes are not browser evidence URLs.
    detail.pop("evidence_artifact_id", None)
    detail["actor"] = {"name": actor.name, "role": actor.role} if actor else None
    detail["evidence"] = (
        {"id": artifact.id, "media_type": artifact.media_type, "size_bytes": artifact.size_bytes}
        if artifact is not None else {"present": False}
    )
    return detail


def field_candidate_field_summary(candidate, artifact) -> dict:
    return {
        "id": candidate.id,
        "status": candidate.status,
        "evidence": (
            {"present": True, "media_type": artifact.media_type, "size_bytes": artifact.size_bytes}
            if artifact is not None else {"present": False}
        ),
    }
