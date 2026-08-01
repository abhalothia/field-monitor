import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from ffl.communications import persistence
from ffl.communications.ports import CommunicationsProvider
from ffl.persistence import repository
from ffl.services import operations


WORK_PROMPT_PURPOSE = "work_prompt"


def send_work_prompt(
    conn: sqlite3.Connection, provider: CommunicationsProvider, work_item_id: str, endpoint_id: str,
    template_id: str, initiated_by_person_id: str,
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
    if not persistence.has_active_consent(conn, endpoint_id, WORK_PROMPT_PURPOSE):
        raise ValueError("work prompt consent is not active")

    prompt = persistence.create_prompt(
        conn, work.id, work.allocation_id, endpoint_id, template_id, initiated_by_person_id
    )
    try:
        result = provider.send_message(
            endpoint["address"], template["body"], None, prompt["id"]
        )
    except Exception:
        return persistence.update_prompt(conn, prompt["id"], "failed")
    return persistence.update_prompt(conn, prompt["id"], result.status, result.provider_message_id)


def receive_webhook(
    conn: sqlite3.Connection, provider: CommunicationsProvider, payload: Dict[str, Any]
) -> Tuple[Dict[str, Any], bool]:
    event = provider.normalize_webhook(payload)
    endpoint = persistence.find_endpoint(conn, provider.name, event["contact"])
    stored, created = persistence.record_event(
        conn, provider.name, event["event_id"], event["message_id"], event["event_type"],
        event["contact"], endpoint["id"] if endpoint else None, event["raw"],
    )
    if not created:
        return stored, False

    if event["event_type"] == "message_failed":
        prompt = persistence.find_prompt_for_message(conn, event["message_id"])
        if prompt is not None:
            persistence.update_prompt(conn, prompt["id"], "failed")
        persistence.update_event_status(conn, stored["id"], "processed")
        return stored, True
    if event["event_type"] == "message_delivered":
        prompt = persistence.find_prompt_for_message(conn, event["message_id"])
        if prompt is not None:
            persistence.update_prompt(conn, prompt["id"], "delivered")
        persistence.update_event_status(conn, stored["id"], "processed")
        return stored, True
    if event["event_type"] != "message_inbound":
        persistence.update_event_status(conn, stored["id"], "processed")
        return stored, True

    attachments = [
        persistence.add_attachment(conn, stored["id"], url, event["message_type"])
        for url in event["attachments"]
    ]
    prompt = persistence.single_open_prompt(conn, endpoint["id"]) if endpoint else None
    intent = event.get("quick_reply") or event["text"].strip().upper()
    kind = "exception" if intent == "REPORT_DEVIATION" else "signal"
    candidate = persistence.create_candidate(
        conn, stored["id"], prompt["id"] if prompt else None,
        prompt["allocation_id"] if prompt else None, prompt["work_item_id"] if prompt else None,
        endpoint["id"] if endpoint else None, kind,
        {
            "text": event["text"], "intent": intent, "message_type": event["message_type"],
            "attachment_ids": [attachment["id"] for attachment in attachments],
            "context_resolved": prompt is not None,
        },
    )
    if prompt is not None:
        persistence.update_prompt(conn, prompt["id"], "responded")
        persistence.update_event_status(conn, stored["id"], "review_required")
    else:
        persistence.update_event_status(conn, stored["id"], "review_required")
    return {**stored, "candidate_id": candidate["id"]}, True


def _candidate_draft(candidate: Dict[str, Any]) -> Dict[str, Any]:
    return json.loads(candidate["draft_json"])


def accept_candidate(
    conn: sqlite3.Connection, candidate_id: str, reviewer_id: str, signal_template_id: Optional[str] = None,
    signal_template_version: Optional[int] = None, exception_owner_id: Optional[str] = None,
    exception_fallback_owner_id: Optional[str] = None, severity: str = "medium",
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
    observed_at = event["received_at"]
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
    template = conn.execute(
        "SELECT 1 FROM signal_templates WHERE id = ? AND version = ? AND status = 'published'",
        (signal_template_id, signal_template_version),
    ).fetchone()
    if template is None:
        raise ValueError("published signal template id and version are required")
    record = repository.create_field_signal(
        conn, candidate["allocation_id"], signal_template_id, signal_template_version, observed_at,
        endpoint["person_id"], {"communication_candidate_id": candidate["id"], "reported_text": draft["text"]},
        status="submitted", received_at=event["received_at"],
    )
    return persistence.review_candidate(conn, candidate_id, "accepted", reviewer_id, "field_signal", record.id)


def reject_candidate(conn: sqlite3.Connection, candidate_id: str, reviewer_id: str) -> Dict[str, Any]:
    candidate = persistence.get_candidate(conn, candidate_id)
    if candidate is None or candidate["status"] != "review":
        raise ValueError("reviewable communication candidate not found")
    return persistence.review_candidate(conn, candidate_id, "rejected", reviewer_id)
