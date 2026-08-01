import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from ffl.communications import persistence
from ffl.communications import private
from ffl.communications.ports import CommunicationsProvider, ProviderRejectedError
from ffl.persistence import repository
from ffl.services import evidence, operations, season


WORK_PROMPT_PURPOSE = "work_prompt"


def _suppress_opted_out_endpoint(conn: sqlite3.Connection, endpoint_id: str, provenance: str) -> None:
    if persistence.has_active_consent(conn, endpoint_id, WORK_PROMPT_PURPOSE):
        persistence.set_consent(conn, endpoint_id, WORK_PROMPT_PURPOSE, False, provenance)


def send_work_prompt(
    conn: sqlite3.Connection, provider: CommunicationsProvider, work_item_id: str, endpoint_id: str,
    template_id: str, initiated_by_person_id: str, idempotency_key: str,
) -> Dict[str, Any]:
    endpoint = conn.execute("SELECT * FROM communication_endpoints WHERE id = ? AND status = 'active'", (endpoint_id,)).fetchone()
    template = conn.execute("SELECT * FROM communication_templates WHERE id = ?", (template_id,)).fetchone()
    work = repository.get_work_item(conn, work_item_id)
    if endpoint is None or template is None or work is None:
        raise ValueError("work, active endpoint, and template are required")
    if endpoint["person_id"] != work.owner_id:
        raise ValueError("work prompt endpoint must belong to the assigned work owner")
    if template["status"] != "published" or template["purpose"] != WORK_PROMPT_PURPOSE:
        raise ValueError("work prompt requires a published work_prompt template")
    if getattr(provider, "whatsapp_channel_enabled", False) and (
        not template["provider_template_id"] or template["provider_approval_state"] != "approved"
    ):
        raise ValueError("approved external WhatsApp template is required for configured WhatsApp delivery")
    if not persistence.has_active_consent(conn, endpoint_id, WORK_PROMPT_PURPOSE):
        raise ValueError("work prompt consent is not active")
    if conn.execute("SELECT 1 FROM people WHERE id = ?", (initiated_by_person_id,)).fetchone() is None:
        raise ValueError("prompt initiator does not exist")

    prompt, created = persistence.create_prompt(
        conn, work.id, work.allocation_id, endpoint_id, template_id, initiated_by_person_id, idempotency_key
    )
    if not created:
        return prompt
    persistence.create_delivery_attempt(conn, prompt["id"], "attempting")
    try:
        result = provider.send_message(
            endpoint["address"], template["body"], None, prompt["id"]
        )
    except ProviderRejectedError as error:
        if error.error_code == 500:
            _suppress_opted_out_endpoint(conn, endpoint_id, "LoopMessage synchronous error_code 500")
        persistence.create_delivery_attempt(
            conn, prompt["id"], "failed", error_summary="LoopMessage error_code {0}".format(error.error_code or "unknown"),
        )
        return persistence.update_prompt(conn, prompt["id"], "failed")
    except Exception as error:
        # The provider may have accepted a request before a transport timeout;
        # mark it unknown and reconcile, never blindly issue a second send.
        persistence.create_delivery_attempt(conn, prompt["id"], "unknown", error_summary="provider transport outcome unknown")
        return persistence.update_prompt(conn, prompt["id"], "unknown")
    persistence.create_delivery_attempt(conn, prompt["id"], "accepted", result.provider_message_id)
    return persistence.update_prompt(conn, prompt["id"], result.status, result.provider_message_id)


def receive_webhook(
    conn: sqlite3.Connection, provider: CommunicationsProvider, payload: Dict[str, Any], receipt_key: str
) -> Tuple[Dict[str, Any], bool]:
    if not receipt_key:
        raise ValueError("communications receipt key is not configured")
    event = provider.normalize_webhook(payload)
    ciphertext = private.seal(receipt_key, payload)
    endpoint = persistence.find_endpoint(conn, provider.name, event["contact"])
    stored, created = persistence.record_event_with_receipt(
        conn, provider.name, event["event_id"], event["message_id"], event["event_type"],
        event["contact"], endpoint["id"] if endpoint else None,
        {"api_version": event["raw"].get("api_version"), "message_type": event["message_type"]}, ciphertext,
    )
    return stored, created


def process_pending_communications(
    conn: sqlite3.Connection, provider: CommunicationsProvider, receipt_key: str,
    crash_after_receipt: bool = False, processing_lease_seconds: int = 300,
) -> int:
    """Recover private webhook receipts without putting their contents in the inbox.

    A receipt is claimed atomically and only marked processed after its candidate
    and media references are durable.  A provider replay requeues an unfinished
    receipt immediately; an abandoned claim is recovered after its short lease.
    """
    now = datetime.now(timezone.utc)
    persistence.release_expired_receipt_claims(conn, now.isoformat())
    processed = 0
    for receipt in persistence.pending_receipts(conn):
        lease_expires_at = (datetime.now(timezone.utc) + timedelta(seconds=processing_lease_seconds)).isoformat()
        claim_token = persistence.claim_receipt(conn, receipt["event_id"], lease_expires_at)
        if claim_token is None:
            continue
        try:
            if crash_after_receipt:
                raise RuntimeError("injected processing crash")
            try:
                payload = private.open_receipt(receipt_key, receipt["ciphertext"])
            except ValueError as error:
                persistence.quarantine_receipt(conn, receipt["event_id"], claim_token, receipt["ciphertext"], str(error))
                continue
            event = provider.normalize_webhook(payload)
            stored = conn.execute("SELECT * FROM communication_events WHERE id = ?", (receipt["event_id"],)).fetchone()
            if stored is None:
                raise ValueError("communication receipt event is missing")
            _process_event(conn, provider, event, dict(stored))
            if persistence.complete_receipt(conn, receipt["event_id"], claim_token):
                processed += 1
        except Exception as error:
            persistence.retry_receipt(conn, receipt["event_id"], claim_token, "communication processing failed")
    return processed


def process_pending_communication_media(
    conn: sqlite3.Connection, provider: CommunicationsProvider, receipt_key: str,
) -> Dict[str, int]:
    """Materialize authenticated inbound media as FFL evidence, or leave it unavailable.

    Attachment URLs remain only in the purpose-limited private receipt.  A failed
    fetch never leaks the URL and cannot make a candidate publishable; transient
    failures remain eligible for the next worker run.
    """
    retained = 0
    retryable = 0
    failed = 0
    for attachment in persistence.attachments_needing_retention(conn):
        try:
            payload = private.open_receipt(receipt_key, attachment["ciphertext"])
            event = provider.normalize_webhook(payload)
            source_url = next(
                (url for url in event["attachments"]
                 if persistence.attachment_reference(attachment["event_id"], url) == attachment["source_reference"]),
                None,
            )
            if source_url is None:
                raise ValueError("attachment source does not match its protected receipt")
            downloaded = provider.download_inbound_attachment(source_url)
            retain_inbound_attachment(conn, attachment["id"], downloaded.content, downloaded.media_type)
            retained += 1
        except ValueError:
            persistence.record_attachment_attempt(conn, attachment["id"], "attachment cannot be retained", failed=True)
            failed += 1
        except Exception:
            persistence.record_attachment_attempt(conn, attachment["id"], "attachment retrieval failed", failed=False)
            retryable += 1
    return {"retained": retained, "retryable": retryable, "failed": failed}


def reconcile_outbound_messages(conn: sqlite3.Connection, provider: CommunicationsProvider) -> int:
    """Resolve ambiguous sends without ever re-sending a logical work prompt."""
    reconciled = 0
    for prompt in persistence.prompts_requiring_reconciliation(conn):
        if prompt["status"] == "pending":
            # The process could have died after LoopMessage accepted the request
            # but before saving its message_id.  Only a passthrough-bearing
            # webhook can identify it; sending again would risk a duplicate.
            if not persistence.has_unknown_delivery_attempt(conn, prompt["id"]):
                persistence.create_delivery_attempt(conn, prompt["id"], "unknown", error_summary="send acceptance interrupted")
            persistence.update_prompt(conn, prompt["id"], "unknown")
            persistence.create_reconciliation(conn, prompt["id"], "awaiting_webhook")
            reconciled += 1
            continue
        if not prompt["provider_message_id"]:
            persistence.create_reconciliation(conn, prompt["id"], "awaiting_webhook")
            reconciled += 1
            continue
        try:
            status = provider.get_message_status(prompt["provider_message_id"])
        except ProviderRejectedError as error:
            if error.error_code == 500:
                _suppress_opted_out_endpoint(conn, prompt["endpoint_id"], "LoopMessage status error_code 500")
            persistence.create_reconciliation(
                conn, prompt["id"], "lookup_unavailable", prompt["provider_message_id"], provider_error_code=error.error_code,
            )
            continue
        except Exception:
            persistence.create_reconciliation(conn, prompt["id"], "lookup_unavailable", prompt["provider_message_id"])
            continue
        if status is None:
            persistence.create_reconciliation(conn, prompt["id"], "lookup_unavailable", prompt["provider_message_id"])
            continue
        persistence.create_reconciliation(
            conn, prompt["id"], "reconciled", status.provider_message_id, status.status, status.error_code,
        )
        if status.error_code == 500:
            _suppress_opted_out_endpoint(conn, prompt["endpoint_id"], "LoopMessage status error_code 500")
        desired = {"processing": "accepted", "failed": "failed", "delivered": "delivered", "unknown": "unknown"}[status.status]
        if desired != prompt["status"]:
            persistence.update_prompt(conn, prompt["id"], desired, status.provider_message_id)
            attempt_status = "accepted" if desired == "accepted" else "failed" if desired == "failed" else "unknown"
            persistence.create_delivery_attempt(conn, prompt["id"], attempt_status, status.provider_message_id)
        reconciled += 1
    return reconciled


def _process_event(conn: sqlite3.Connection, provider: CommunicationsProvider, event: Dict[str, Any], stored: Dict[str, Any]) -> None:
    if stored["status"] != "received":
        return

    if event["event_type"] in ("message_failed", "message_delivered", "message_scheduled", "unknown"):
        prompt = persistence.find_prompt_for_message(conn, event["message_id"])
        if prompt is None:
            prompt = persistence.find_prompt_for_passthrough(conn, event.get("passthrough"), provider.name, event["contact"])
        if prompt is not None:
            lifecycle = {"message_failed": "failed", "message_delivered": "delivered", "message_scheduled": "scheduled", "unknown": "unknown"}
            try:
                persistence.update_prompt(conn, prompt["id"], lifecycle[event["event_type"]], event["message_id"] or None)
            except ValueError:
                pass
            if event["event_type"] == "message_failed" and event["raw"].get("error_code") == 500:
                _suppress_opted_out_endpoint(conn, prompt["endpoint_id"], "LoopMessage error_code 500")
        persistence.update_event_status(conn, stored["id"], "processed")
        return
    if event["event_type"] != "message_inbound":
        persistence.update_event_status(conn, stored["id"], "processed")
        return

    endpoint = None
    if stored["endpoint_id"]:
        endpoint_row = conn.execute("SELECT * FROM communication_endpoints WHERE id = ? AND provider = ?", (stored["endpoint_id"], provider.name)).fetchone()
        endpoint = dict(endpoint_row) if endpoint_row is not None else None
    existing_candidate = persistence.get_candidate_for_event(conn, stored["id"])
    if existing_candidate is not None:
        # A crash may have happened after candidate persistence but before its
        # prompt/event status updates.  Do not create duplicate evidence rows.
        prompt = None
        if existing_candidate["prompt_id"]:
            prompt_row = conn.execute("SELECT * FROM communication_prompts WHERE id = ?", (existing_candidate["prompt_id"],)).fetchone()
            prompt = dict(prompt_row) if prompt_row is not None else None
        if prompt is not None and prompt["status"] in ("accepted", "scheduled", "delivered"):
            persistence.update_prompt(conn, prompt["id"], "responded")
        persistence.update_event_status(conn, stored["id"], "review_required")
        return

    attachments = [
        persistence.add_attachment(conn, stored["id"], url, event["message_type"])
        for url in event["attachments"]
    ]
    prompt = persistence.single_open_prompt(conn, endpoint["id"]) if endpoint else None
    intent = event["text"].strip().upper()
    kind = "exception" if intent == "REPORT_DEVIATION" else "signal"
    persistence.create_candidate(
        conn, stored["id"], prompt["id"] if prompt else None,
        prompt["allocation_id"] if prompt else None, prompt["work_item_id"] if prompt else None,
        endpoint["id"] if endpoint else None, kind,
        {
            "text": event["text"], "intent": intent, "message_type": event["message_type"],
            "attachment_ids": [attachment["id"] for attachment in attachments],
            "context_resolved": prompt is not None,
            "observed_at": event["raw"].get("observed_at"),
        },
    )
    if prompt is not None:
        persistence.update_prompt(conn, prompt["id"], "responded")
    persistence.update_event_status(conn, stored["id"], "review_required")
    return


def _candidate_draft(candidate: Dict[str, Any]) -> Dict[str, Any]:
    return json.loads(candidate["draft_json"])


def candidate_review_detail(conn: sqlite3.Connection, candidate_id: str) -> Dict[str, Any]:
    """Return one manager-review record, never a contact conversation archive."""
    detail = persistence.candidate_detail(conn, candidate_id)
    if detail is None or detail["candidate"]["status"] != "review":
        raise ValueError("reviewable communication candidate not found")
    candidate = detail["candidate"]
    draft = _candidate_draft(candidate)
    endpoint = detail["endpoint"]
    return {
        "id": candidate["id"],
        "kind": candidate["kind"],
        "status": candidate["status"],
        "allocation_id": candidate["allocation_id"],
        "work_item_id": candidate["work_item_id"],
        "created_at": candidate["created_at"],
        "context": {
            "reported_text": draft.get("text", ""),
            "intent": draft.get("intent"),
            "message_type": draft.get("message_type"),
            "observed_at": draft.get("observed_at"),
            "received_at": detail["event"]["received_at"],
            "context_resolved": bool(draft.get("context_resolved")),
        },
        "endpoint": None if endpoint is None else {
            "id": endpoint["id"], "provider": endpoint["provider"], "address_last4": endpoint["address"][-4:],
            "locale": endpoint["locale"], "status": endpoint["status"],
        },
        "evidence": [
            {
                "attachment_id": attachment["id"], "media_type": attachment["media_type"], "status": attachment["status"],
                "attempts": attachment["attempts"], "last_attempt_at": attachment["last_attempt_at"], "created_at": attachment["created_at"],
                "evidence_artifact": None if attachment["evidence_artifact_id"] is None else {
                    "id": attachment["evidence_artifact_id"], "media_type": attachment["evidence_media_type"],
                    "size_bytes": attachment["evidence_size_bytes"], "created_at": attachment["evidence_created_at"],
                },
            }
            for attachment in detail["attachments"]
        ],
    }


def retain_inbound_attachment(
    conn: sqlite3.Connection, attachment_id: str, content: bytes, media_type: str, directory: Optional[str] = None,
) -> str:
    """Private media-worker entry point; it never persists a provider URL.

    The worker obtains the bytes through an approved provider-specific media
    retrieval flow, passes them here, and this function creates the immutable
    FFL evidence artifact plus the attachment-to-artifact proof link.
    """
    row = conn.execute(
        "SELECT attachment.id, endpoint.person_id FROM communication_attachments attachment "
        "JOIN communication_events event ON event.id = attachment.event_id "
        "LEFT JOIN communication_endpoints endpoint ON endpoint.id = event.endpoint_id "
        "WHERE attachment.id = ?",
        (attachment_id,),
    ).fetchone()
    if row is None or row["person_id"] is None:
        raise ValueError("communication attachment has no resolved endpoint")
    artifact = evidence.retain_evidence(
        conn, content, media_type, original_filename=None, source_uri=None,
        created_by_person_id=row["person_id"], directory=directory,
    )
    persistence.link_retained_evidence(conn, attachment_id, artifact.id)
    return artifact.id


def accept_candidate(
    conn: sqlite3.Connection, candidate_id: str, reviewer_id: str, signal_template_id: Optional[str] = None,
    signal_template_version: Optional[int] = None, exception_owner_id: Optional[str] = None,
    exception_fallback_owner_id: Optional[str] = None, severity: str = "medium",
    signal_values: Optional[Dict[str, Any]] = None, evidence_artifact_id: Optional[str] = None,
) -> Dict[str, Any]:
    candidate = persistence.get_candidate(conn, candidate_id)
    if candidate is None or candidate["status"] != "review":
        raise ValueError("reviewable communication candidate not found")
    if not candidate["allocation_id"] or not candidate["endpoint_id"]:
        raise ValueError("candidate identity or farm context is ambiguous")
    endpoint = conn.execute("SELECT * FROM communication_endpoints WHERE id = ?", (candidate["endpoint_id"],)).fetchone()
    event = conn.execute("SELECT * FROM communication_events WHERE id = ?", (candidate["event_id"],)).fetchone()
    if endpoint is None or event is None:
        raise ValueError("candidate linkage is incomplete")
    draft = _candidate_draft(candidate)
    observed_at = draft.get("observed_at") or event["received_at"]
    if candidate["kind"] == "exception":
        if not exception_owner_id or not exception_fallback_owner_id:
            raise ValueError("exception acceptance requires owner and fallback owner")
        record = operations.report_exception(
            conn, candidate["allocation_id"], draft["text"] or "WhatsApp field deviation", severity,
            exception_owner_id, exception_fallback_owner_id, observed_at, "communication-candidate:" + candidate["id"],
        )
        return persistence.review_candidate(conn, candidate_id, "accepted", reviewer_id, "exception_record", record.id)
    if not signal_template_id or signal_template_version is None:
        raise ValueError("signal acceptance requires template id and version")
    if signal_values is None:
        raise ValueError("signal acceptance requires reviewed signal values")
    if draft.get("attachment_ids"):
        if evidence_artifact_id is None or not persistence.evidence_is_linked_to_event(conn, candidate["event_id"], evidence_artifact_id):
            raise ValueError("communication attachment requires retained evidence linked to this communication")
    record = season.record_field_signal(
        conn, candidate["allocation_id"], signal_template_id, signal_template_version, observed_at,
        endpoint["person_id"], signal_values, evidence_artifact_id=evidence_artifact_id, status="submitted",
    )
    return persistence.review_candidate(conn, candidate_id, "accepted", reviewer_id, "field_signal", record.id)


def reject_candidate(conn: sqlite3.Connection, candidate_id: str, reviewer_id: str) -> Dict[str, Any]:
    candidate = persistence.get_candidate(conn, candidate_id)
    if candidate is None or candidate["status"] != "review":
        raise ValueError("reviewable communication candidate not found")
    return persistence.review_candidate(conn, candidate_id, "rejected", reviewer_id)


def mark_no_response(conn: sqlite3.Connection, prompt_id: str, manager_id: str) -> Dict[str, Any]:
    if conn.execute("SELECT 1 FROM people WHERE id = ?", (manager_id,)).fetchone() is None:
        raise ValueError("manager does not exist")
    return persistence.update_prompt(conn, prompt_id, "no_response")
