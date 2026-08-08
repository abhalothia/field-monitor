"""Immutable communications interaction snapshots and exact reply correlation.

An interaction run binds one verified endpoint to the canonical context chosen
before dispatch.  Its raw random context token is returned only by creation so
the outbound provider can echo it as passthrough; persistence retains only the
SHA-256 digest.  Inbound correlation never falls back to endpoint history or an
"open" prompt heuristic.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
import secrets
import sqlite3
import uuid
from typing import Optional, Sequence, Tuple, Union


_INTENTS = frozenset({
    "confirm",
    "decline",
    "report_deviation",
    "submit_evidence",
    "request_callback",
    "help",
    "opt_out",
})
_RUN_STATUSES = frozenset({
    "ready", "dispatching", "dispatched", "responded", "expired", "cancelled",
})
_DISPATCH_STATUSES = frozenset({"accepted", "scheduled", "delivered", "failed", "unknown"})


@dataclass(frozen=True)
class InteractionRun:
    id: str
    profile_id: Optional[str]
    endpoint_id: str
    allocation_id: Optional[str]
    work_item_id: Optional[str]
    field_information_request_id: Optional[str]
    workflow_version_id: Optional[str]
    campaign_snapshot_id: Optional[str]
    legacy_prompt_id: Optional[str]
    context_token: Optional[str]
    expected_intents: Tuple[str, ...]
    status: str
    created_at: str
    expires_at: str


def create_interaction_run(
    conn,
    profile_id: Optional[str],
    endpoint_id: str,
    *,
    allocation_id: Optional[str] = None,
    work_item_id: Optional[str] = None,
    field_information_request_id: Optional[str] = None,
    workflow_version_id: Optional[str] = None,
    campaign_snapshot_id: Optional[str] = None,
    legacy_prompt_id: Optional[str] = None,
    expected_intents: Sequence[str],
    expires_at: Union[datetime, str],
    created_at: Optional[Union[datetime, str]] = None,
    commit: bool = True,
) -> InteractionRun:
    """Create one immutable context capture and issue its raw token once.

    A profile is mandatory for new workflows.  The only profile-less path is
    an explicit legacy prompt adapter, because historical prompts predate
    portal-scoped communications profiles and must not invent that authority.
    """
    endpoint_id = _required_identifier(endpoint_id, "endpoint_id")
    profile_id = _optional_identifier(profile_id, "profile_id")
    allocation_id = _optional_identifier(allocation_id, "allocation_id")
    work_item_id = _optional_identifier(work_item_id, "work_item_id")
    field_information_request_id = _optional_identifier(
        field_information_request_id, "field_information_request_id",
    )
    workflow_version_id = _optional_identifier(workflow_version_id, "workflow_version_id")
    campaign_snapshot_id = _optional_identifier(campaign_snapshot_id, "campaign_snapshot_id")
    legacy_prompt_id = _optional_identifier(legacy_prompt_id, "legacy_prompt_id")
    intents = _expected_intents(expected_intents)
    if not isinstance(commit, bool):
        raise ValueError("interaction commit mode is invalid")
    created = (
        _utc_instant(created_at, "created_at")
        if created_at is not None
        else datetime.now(timezone.utc)
    )
    expiry = _utc_instant(expires_at, "expires_at")
    if expiry <= created:
        raise ValueError("interaction expiry must be after creation")

    endpoint = conn.execute(
        "SELECT id, person_id, provider, status FROM communication_endpoints WHERE id = ?",
        (endpoint_id,),
    ).fetchone()
    if endpoint is None or endpoint["status"] != "active":
        raise ValueError("active communication endpoint is required")
    if profile_id is None:
        if legacy_prompt_id is None:
            raise ValueError("communication profile is required")
    else:
        authority = conn.execute(
            """SELECT 1
               FROM communication_profiles profile
               JOIN communication_endpoint_verifications verification
                 ON verification.profile_id = profile.id
                AND verification.endpoint_id = ?
                AND verification.status = 'active'
               WHERE profile.id = ? AND profile.person_id = ? AND profile.status = 'active'""",
            (endpoint_id, profile_id, endpoint["person_id"]),
        ).fetchone()
        if authority is None:
            raise ValueError("active profile and endpoint verification are required")

    _validate_context_links(
        conn,
        endpoint_id,
        endpoint["person_id"],
        allocation_id,
        work_item_id,
        field_information_request_id,
        legacy_prompt_id,
    )

    identifier = str(uuid.uuid4())
    raw_token = secrets.token_urlsafe(32)
    token_hash = _token_hash(raw_token)
    created_at = created.isoformat()
    expires_at_utc = expiry.isoformat()
    conn.execute(
        """INSERT INTO communication_interaction_runs
           (id, profile_id, endpoint_id, allocation_id, work_item_id,
            field_information_request_id, workflow_version_id, campaign_snapshot_id,
            legacy_prompt_id, context_token_hash, expected_intents_json, status,
            created_at, expires_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ready', ?, ?)""",
        (
            identifier,
            profile_id,
            endpoint_id,
            allocation_id,
            work_item_id,
            field_information_request_id,
            workflow_version_id,
            campaign_snapshot_id,
            legacy_prompt_id,
            token_hash,
            json.dumps(list(intents), separators=(",", ":")),
            created_at,
            expires_at_utc,
        ),
    )
    if commit:
        conn.commit()
    row = conn.execute(
        "SELECT * FROM communication_interaction_runs WHERE id = ?", (identifier,),
    ).fetchone()
    return replace(_run(row), context_token=raw_token)


def record_interaction_dispatch(
    conn,
    interaction_run_id: str,
    provider_message_id: str,
    *,
    status: str = "accepted",
) -> InteractionRun:
    """Bind one provider message ID to one logical interaction exactly once."""
    interaction_run_id = _required_identifier(interaction_run_id, "interaction_run_id")
    provider_message_id = _required_identifier(provider_message_id, "provider_message_id")
    if status not in _DISPATCH_STATUSES:
        raise ValueError("invalid interaction dispatch status")
    run_row = conn.execute(
        """SELECT run.*, endpoint.provider
           FROM communication_interaction_runs run
           JOIN communication_endpoints endpoint ON endpoint.id = run.endpoint_id
           WHERE run.id = ?""",
        (interaction_run_id,),
    ).fetchone()
    if run_row is None:
        raise ValueError("interaction run does not exist")
    existing = conn.execute(
        "SELECT * FROM communication_interaction_dispatches WHERE interaction_run_id = ?",
        (interaction_run_id,),
    ).fetchone()
    if existing is not None:
        if existing["provider_message_id"] != provider_message_id:
            raise ValueError("interaction run is already bound to another provider message")
        return _run(run_row)
    if run_row["status"] not in ("ready", "dispatching"):
        raise ValueError("interaction run is not dispatchable")

    dispatch_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            """INSERT INTO communication_interaction_dispatches
               (id, interaction_run_id, provider, provider_message_id, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                dispatch_id,
                interaction_run_id,
                run_row["provider"],
                provider_message_id,
                status,
                created_at,
            ),
        )
        conn.execute(
            "UPDATE communication_interaction_runs SET status = 'dispatched' WHERE id = ?",
            (interaction_run_id,),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        existing = conn.execute(
            "SELECT * FROM communication_interaction_dispatches WHERE interaction_run_id = ?",
            (interaction_run_id,),
        ).fetchone()
        if existing is None or existing["provider_message_id"] != provider_message_id:
            raise
    except Exception:
        conn.rollback()
        raise
    return interaction_run(conn, interaction_run_id)


def find_interaction_for_inbound(
    conn,
    provider: str,
    endpoint_id: str,
    reply_to_message_id: Optional[str],
    context_token: Optional[str],
    *,
    now: Optional[Union[datetime, str]] = None,
    context_token_hash: Optional[str] = None,
) -> Optional[InteractionRun]:
    """Resolve an inbound reply exactly: provider message ID, then token hash."""
    provider = _required_identifier(provider, "provider")
    endpoint_id = _required_identifier(endpoint_id, "endpoint_id")
    instant = _utc_instant(now, "now") if now is not None else datetime.now(timezone.utc)
    at = instant.isoformat()
    if isinstance(reply_to_message_id, str) and reply_to_message_id:
        row = conn.execute(
            """SELECT run.*
               FROM communication_interaction_dispatches dispatch
               JOIN communication_interaction_runs run ON run.id = dispatch.interaction_run_id
               WHERE dispatch.provider = ? AND dispatch.provider_message_id = ?
                 AND run.endpoint_id = ?
                 AND run.status IN ('dispatched', 'responded')
                 AND run.expires_at > ?""",
            (provider, reply_to_message_id, endpoint_id, at),
        ).fetchone()
        if row is not None:
            return _run(row)
    token_hash = _correlation_token_hash(context_token, context_token_hash)
    if token_hash is None:
        return None
    row = conn.execute(
        """SELECT run.*
           FROM communication_interaction_runs run
           JOIN communication_endpoints endpoint ON endpoint.id = run.endpoint_id
           WHERE endpoint.provider = ? AND run.endpoint_id = ?
             AND run.context_token_hash = ?
             AND run.status IN ('dispatched', 'responded')
             AND run.expires_at > ?""",
        (provider, endpoint_id, token_hash, at),
    ).fetchone()
    return _run(row) if row is not None else None


def update_interaction_dispatch_status(conn, interaction_run_id: str, status: str) -> None:
    """Advance the mutable provider lifecycle without changing its binding."""
    if status not in _DISPATCH_STATUSES:
        raise ValueError("invalid interaction dispatch status")
    dispatch = conn.execute(
        """SELECT status FROM communication_interaction_dispatches
           WHERE interaction_run_id = ?""",
        (interaction_run_id,),
    ).fetchone()
    if dispatch is None:
        raise ValueError("interaction dispatch does not exist")
    allowed = {
        "accepted": {"scheduled", "delivered", "failed", "unknown"},
        "scheduled": {"delivered", "failed", "unknown"},
        "unknown": {"accepted", "scheduled", "delivered", "failed"},
    }
    if dispatch["status"] == status:
        return
    if status not in allowed.get(dispatch["status"], set()):
        raise ValueError("invalid interaction dispatch transition")
    conn.execute(
        "UPDATE communication_interaction_dispatches SET status = ? WHERE interaction_run_id = ?",
        (status, interaction_run_id),
    )
    conn.commit()


def route_inbound_interaction(
    conn,
    provider: str,
    endpoint_id: str,
    reply_to_message_id: Optional[str],
    context_token: Optional[str],
    intent: str,
    *,
    now: Optional[Union[datetime, str]] = None,
    context_token_hash: Optional[str] = None,
) -> Optional[InteractionRun]:
    """Return a correlated run only when the constrained intent was expected."""
    if intent not in _INTENTS:
        return None
    run = find_interaction_for_inbound(
        conn,
        provider,
        endpoint_id,
        reply_to_message_id,
        context_token,
        now=now,
        context_token_hash=context_token_hash,
    )
    if run is None or intent not in run.expected_intents:
        return None
    return run


def find_interaction_for_dispatch_callback(
    conn,
    provider: str,
    endpoint_id: str,
    provider_message_id: Optional[str],
    context_token: Optional[str],
    *,
    context_token_hash: Optional[str] = None,
) -> Optional[InteractionRun]:
    """Resolve an outbound lifecycle callback, including an ambiguous send.

    Unlike an inbound reply, a callback may recover a still-``ready`` run: the
    echoed token is proof that the provider accepted the send before the local
    process persisted its message ID.
    """
    provider = _required_identifier(provider, "provider")
    endpoint_id = _required_identifier(endpoint_id, "endpoint_id")
    if isinstance(provider_message_id, str) and provider_message_id:
        row = conn.execute(
            """SELECT run.*
               FROM communication_interaction_dispatches dispatch
               JOIN communication_interaction_runs run ON run.id = dispatch.interaction_run_id
               WHERE dispatch.provider = ? AND dispatch.provider_message_id = ?
                 AND run.endpoint_id = ?""",
            (provider, provider_message_id, endpoint_id),
        ).fetchone()
        if row is not None:
            return _run(row)
    token_hash = _correlation_token_hash(context_token, context_token_hash)
    if token_hash is None:
        return None
    row = conn.execute(
        """SELECT run.*
           FROM communication_interaction_runs run
           JOIN communication_endpoints endpoint ON endpoint.id = run.endpoint_id
           WHERE endpoint.provider = ? AND run.endpoint_id = ?
             AND run.context_token_hash = ?
             AND run.status IN ('ready', 'dispatching', 'dispatched', 'responded')""",
        (provider, endpoint_id, token_hash),
    ).fetchone()
    return _run(row) if row is not None else None


def mark_interaction_responded(conn, interaction_run_id: str) -> InteractionRun:
    """Close a dispatched run after its review candidate is durable."""
    return transition_interaction_run(conn, interaction_run_id, "responded")


def transition_interaction_run(conn, interaction_run_id: str, status: str) -> InteractionRun:
    """Advance run lifecycle while leaving every captured binding unchanged."""
    if status not in _RUN_STATUSES:
        raise ValueError("invalid interaction run status")
    run = interaction_run(conn, interaction_run_id)
    if run.status == status:
        return run
    allowed = {
        "ready": {"dispatching", "expired", "cancelled"},
        "dispatching": {"dispatched", "expired", "cancelled"},
        "dispatched": {"responded", "expired", "cancelled"},
    }
    if status not in allowed.get(run.status, set()):
        raise ValueError("invalid interaction run transition")
    conn.execute(
        "UPDATE communication_interaction_runs SET status = ? WHERE id = ?",
        (status, interaction_run_id),
    )
    conn.commit()
    return interaction_run(conn, interaction_run_id)


def interaction_run(conn, interaction_run_id: str) -> InteractionRun:
    row = conn.execute(
        "SELECT * FROM communication_interaction_runs WHERE id = ?", (interaction_run_id,),
    ).fetchone()
    if row is None:
        raise ValueError("interaction run does not exist")
    return _run(row)


def interaction_for_legacy_prompt(conn, prompt_id: str) -> Optional[InteractionRun]:
    row = conn.execute(
        "SELECT * FROM communication_interaction_runs WHERE legacy_prompt_id = ?", (prompt_id,),
    ).fetchone()
    return _run(row) if row is not None else None


def _validate_context_links(
    conn,
    endpoint_id: str,
    endpoint_person_id: str,
    allocation_id: Optional[str],
    work_item_id: Optional[str],
    field_information_request_id: Optional[str],
    legacy_prompt_id: Optional[str],
) -> None:
    if allocation_id is not None and conn.execute(
        "SELECT 1 FROM crop_allocations WHERE id = ?", (allocation_id,),
    ).fetchone() is None:
        raise ValueError("interaction allocation does not exist")
    if work_item_id is not None:
        work = conn.execute(
            "SELECT allocation_id FROM work_items WHERE id = ?", (work_item_id,),
        ).fetchone()
        if work is None:
            raise ValueError("interaction work item does not exist")
        if allocation_id is not None and work["allocation_id"] != allocation_id:
            raise ValueError("interaction work item must match its allocation")
    if field_information_request_id is not None:
        request = conn.execute(
            """SELECT allocation_id, work_item_id, target_person_id
               FROM field_information_requests WHERE id = ?""",
            (field_information_request_id,),
        ).fetchone()
        if request is None:
            raise ValueError("interaction field request does not exist")
        if allocation_id is not None and request["allocation_id"] != allocation_id:
            raise ValueError("interaction field request must match its allocation")
        if work_item_id is not None and request["work_item_id"] != work_item_id:
            raise ValueError("interaction field request must match its work item")
        if request["target_person_id"] != endpoint_person_id:
            raise ValueError("interaction field request must target its endpoint person")
    if legacy_prompt_id is not None:
        prompt = conn.execute(
            """SELECT endpoint_id, allocation_id, work_item_id
               FROM communication_prompts WHERE id = ?""",
            (legacy_prompt_id,),
        ).fetchone()
        if prompt is None:
            raise ValueError("legacy communication prompt does not exist")
        if prompt["endpoint_id"] != endpoint_id:
            raise ValueError("legacy prompt must match its interaction endpoint")
        if allocation_id != prompt["allocation_id"] or work_item_id != prompt["work_item_id"]:
            raise ValueError("legacy prompt context must match its interaction run")


def _run(row) -> InteractionRun:
    expected = json.loads(row["expected_intents_json"])
    if not isinstance(expected, list) or not all(isinstance(item, str) for item in expected):
        raise ValueError("stored interaction expected intents are invalid")
    status = row["status"]
    if status not in _RUN_STATUSES:
        raise ValueError("stored interaction status is invalid")
    return InteractionRun(
        id=row["id"],
        profile_id=row["profile_id"],
        endpoint_id=row["endpoint_id"],
        allocation_id=row["allocation_id"],
        work_item_id=row["work_item_id"],
        field_information_request_id=row["field_information_request_id"],
        workflow_version_id=row["workflow_version_id"],
        campaign_snapshot_id=row["campaign_snapshot_id"],
        legacy_prompt_id=row["legacy_prompt_id"],
        context_token=None,
        expected_intents=tuple(expected),
        status=status,
        created_at=row["created_at"],
        expires_at=row["expires_at"],
    )


def _expected_intents(values: Sequence[str]) -> Tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError("expected_intents must be a sequence of constrained intents")
    intents = tuple(values)
    if not intents or len(set(intents)) != len(intents) or any(intent not in _INTENTS for intent in intents):
        raise ValueError("expected_intents must be unique constrained intents")
    return intents


def _required_identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 512:
        raise ValueError("{0} is required".format(label))
    return value


def _optional_identifier(value: object, label: str) -> Optional[str]:
    if value is None:
        return None
    return _required_identifier(value, label)


def _utc_instant(value: Union[datetime, str], label: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("{0} must be an ISO-8601 timestamp".format(label)) from error
    else:
        raise ValueError("{0} must be an ISO-8601 timestamp".format(label))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("{0} must include a timezone".format(label))
    return parsed.astimezone(timezone.utc)


def _token_hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def context_token_digest(raw_token: str) -> str:
    """Return the persistence-safe digest for one bounded opaque token."""
    if not isinstance(raw_token, str) or not raw_token or len(raw_token) > 1024:
        raise ValueError("context token is invalid")
    return _token_hash(raw_token)


def _correlation_token_hash(
    raw_token: Optional[str], persisted_hash: Optional[str],
) -> Optional[str]:
    if isinstance(raw_token, str) and raw_token and len(raw_token) <= 1024:
        return _token_hash(raw_token)
    if not isinstance(persisted_hash, str) or len(persisted_hash) != 64:
        return None
    if persisted_hash != persisted_hash.lower() or any(
        character not in "0123456789abcdef" for character in persisted_hash
    ):
        return None
    return persisted_hash
