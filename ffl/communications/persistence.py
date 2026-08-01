import json
import hashlib
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


def _identity() -> Tuple[str, str]:
    return str(uuid.uuid4()), datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def create_communications_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS communication_endpoints (
            id TEXT PRIMARY KEY,
            person_id TEXT NOT NULL REFERENCES people(id),
            provider TEXT NOT NULL,
            address TEXT NOT NULL,
            locale TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('active', 'disabled')),
            created_at TEXT NOT NULL,
            UNIQUE(provider, address)
        );
        CREATE TABLE IF NOT EXISTS communication_consents (
            id TEXT PRIMARY KEY,
            endpoint_id TEXT NOT NULL REFERENCES communication_endpoints(id),
            purpose TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('active', 'revoked')),
            granted_at TEXT NOT NULL,
            revoked_at TEXT,
            evidence TEXT NOT NULL,
            UNIQUE(endpoint_id, purpose)
        );
        CREATE TABLE IF NOT EXISTS communication_templates (
            id TEXT PRIMARY KEY,
            template_key TEXT NOT NULL,
            version INTEGER NOT NULL CHECK (version > 0),
            locale TEXT NOT NULL,
            purpose TEXT NOT NULL,
            body TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('draft', 'published', 'retired')),
            owner_id TEXT NOT NULL REFERENCES people(id),
            created_at TEXT NOT NULL,
            UNIQUE(template_key, version, locale)
        );
        CREATE TABLE IF NOT EXISTS communication_prompts (
            id TEXT PRIMARY KEY,
            work_item_id TEXT NOT NULL REFERENCES work_items(id),
            allocation_id TEXT NOT NULL REFERENCES crop_allocations(id),
            endpoint_id TEXT NOT NULL REFERENCES communication_endpoints(id),
            template_id TEXT NOT NULL REFERENCES communication_templates(id),
            initiated_by_person_id TEXT NOT NULL REFERENCES people(id),
            idempotency_key TEXT NOT NULL UNIQUE,
            provider_message_id TEXT UNIQUE,
            status TEXT NOT NULL CHECK (status IN ('pending', 'accepted', 'scheduled', 'delivered', 'failed', 'unknown', 'responded', 'no_response')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS communication_events (
            id TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            provider_event_id TEXT NOT NULL,
            provider_message_id TEXT,
            event_type TEXT NOT NULL,
            contact_fingerprint TEXT NOT NULL,
            endpoint_id TEXT REFERENCES communication_endpoints(id),
            envelope_json TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('received', 'processed', 'review_required', 'quarantined')),
            received_at TEXT NOT NULL,
            UNIQUE(provider, provider_event_id)
        );
        CREATE TABLE IF NOT EXISTS communication_attachments (
            id TEXT PRIMARY KEY,
            event_id TEXT NOT NULL REFERENCES communication_events(id),
            source_reference TEXT NOT NULL,
            media_type TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('unavailable', 'retained', 'failed')),
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS communication_candidates (
            id TEXT PRIMARY KEY,
            event_id TEXT NOT NULL UNIQUE REFERENCES communication_events(id),
            prompt_id TEXT REFERENCES communication_prompts(id),
            allocation_id TEXT REFERENCES crop_allocations(id),
            work_item_id TEXT REFERENCES work_items(id),
            endpoint_id TEXT REFERENCES communication_endpoints(id),
            kind TEXT NOT NULL CHECK (kind IN ('signal', 'exception')),
            status TEXT NOT NULL CHECK (status IN ('review', 'accepted', 'rejected')),
            draft_json TEXT NOT NULL,
            accepted_record_type TEXT,
            accepted_record_id TEXT,
            reviewed_by_person_id TEXT REFERENCES people(id),
            reviewed_at TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_communication_prompts_endpoint_status
            ON communication_prompts(endpoint_id, status);
        CREATE INDEX IF NOT EXISTS idx_communication_events_contact ON communication_events(provider, contact_fingerprint);
        """
    )
    conn.commit()


def create_endpoint(conn: sqlite3.Connection, person_id: str, provider: str, address: str, locale: str) -> Dict[str, Any]:
    if conn.execute("SELECT 1 FROM people WHERE id = ?", (person_id,)).fetchone() is None:
        raise ValueError("endpoint person does not exist")
    existing = conn.execute("SELECT * FROM communication_endpoints WHERE provider = ? AND address = ?", (provider, address)).fetchone()
    if existing is not None:
        return dict(existing)
    identifier, created_at = _identity()
    conn.execute("INSERT INTO communication_endpoints VALUES (?, ?, ?, ?, ?, 'active', ?)", (identifier, person_id, provider, address, locale, created_at))
    conn.commit()
    return dict(conn.execute("SELECT * FROM communication_endpoints WHERE id = ?", (identifier,)).fetchone())


def set_consent(conn: sqlite3.Connection, endpoint_id: str, purpose: str, active: bool, evidence: str) -> Dict[str, Any]:
    if conn.execute("SELECT 1 FROM communication_endpoints WHERE id = ?", (endpoint_id,)).fetchone() is None:
        raise ValueError("communication endpoint does not exist")
    row = conn.execute("SELECT * FROM communication_consents WHERE endpoint_id = ? AND purpose = ?", (endpoint_id, purpose)).fetchone()
    now = datetime.now(timezone.utc).isoformat()
    if row is None:
        identifier, _ = _identity()
        conn.execute("INSERT INTO communication_consents VALUES (?, ?, ?, ?, ?, ?, ?)", (identifier, endpoint_id, purpose, 'active' if active else 'revoked', now, None if active else now, evidence))
    else:
        conn.execute("UPDATE communication_consents SET status = ?, granted_at = ?, revoked_at = ?, evidence = ? WHERE id = ?", ('active' if active else 'revoked', now if active else row['granted_at'], None if active else now, evidence, row['id']))
    conn.commit()
    return dict(conn.execute("SELECT * FROM communication_consents WHERE endpoint_id = ? AND purpose = ?", (endpoint_id, purpose)).fetchone())


def has_active_consent(conn: sqlite3.Connection, endpoint_id: str, purpose: str) -> bool:
    return conn.execute("SELECT 1 FROM communication_consents WHERE endpoint_id = ? AND purpose = ? AND status = 'active'", (endpoint_id, purpose)).fetchone() is not None


def create_template(conn: sqlite3.Connection, template_key: str, version: int, locale: str, purpose: str, body: str, owner_id: str, status: str = 'draft') -> Dict[str, Any]:
    if conn.execute("SELECT 1 FROM people WHERE id = ?", (owner_id,)).fetchone() is None:
        raise ValueError("template owner does not exist")
    identifier, created_at = _identity()
    conn.execute("INSERT INTO communication_templates VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (identifier, template_key, version, locale, purpose, body, status, owner_id, created_at))
    conn.commit()
    return dict(conn.execute("SELECT * FROM communication_templates WHERE id = ?", (identifier,)).fetchone())


def publish_template(conn: sqlite3.Connection, template_id: str, publisher_id: str) -> Dict[str, Any]:
    if conn.execute("SELECT 1 FROM people WHERE id = ?", (publisher_id,)).fetchone() is None:
        raise ValueError("template publisher does not exist")
    row = conn.execute("SELECT * FROM communication_templates WHERE id = ?", (template_id,)).fetchone()
    if row is None or row["status"] != "draft":
        raise ValueError("draft communication template not found")
    conn.execute("UPDATE communication_templates SET status = 'published' WHERE id = ?", (template_id,))
    conn.commit()
    return dict(conn.execute("SELECT * FROM communication_templates WHERE id = ?", (template_id,)).fetchone())


def create_prompt(conn: sqlite3.Connection, work_item_id: str, allocation_id: str, endpoint_id: str, template_id: str, initiated_by: str, idempotency_key: str) -> Tuple[Dict[str, Any], bool]:
    existing = conn.execute("SELECT * FROM communication_prompts WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
    if existing is not None:
        return dict(existing), False
    identifier, now = _identity()
    conn.execute("INSERT INTO communication_prompts VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 'pending', ?, ?)", (identifier, work_item_id, allocation_id, endpoint_id, template_id, initiated_by, idempotency_key, now, now))
    conn.commit()
    return dict(conn.execute("SELECT * FROM communication_prompts WHERE id = ?", (identifier,)).fetchone()), True


def update_prompt(conn: sqlite3.Connection, prompt_id: str, status: str, provider_message_id: Optional[str] = None) -> Dict[str, Any]:
    row = conn.execute("SELECT status FROM communication_prompts WHERE id = ?", (prompt_id,)).fetchone()
    allowed = {"pending": {"accepted", "failed"}, "accepted": {"scheduled", "delivered", "failed", "unknown", "responded", "no_response"}, "scheduled": {"delivered", "failed", "unknown", "responded", "no_response"}, "delivered": {"failed", "unknown", "responded", "no_response"}}
    if row is None or status not in allowed.get(row["status"], set()):
        raise ValueError("invalid communication prompt transition")
    now = datetime.now(timezone.utc).isoformat()
    if provider_message_id is None:
        conn.execute("UPDATE communication_prompts SET status = ?, updated_at = ? WHERE id = ?", (status, now, prompt_id))
    else:
        conn.execute("UPDATE communication_prompts SET status = ?, provider_message_id = ?, updated_at = ? WHERE id = ?", (status, provider_message_id, now, prompt_id))
    conn.commit()
    return dict(conn.execute("SELECT * FROM communication_prompts WHERE id = ?", (prompt_id,)).fetchone())


def find_endpoint(conn: sqlite3.Connection, provider: str, address: str) -> Optional[Dict[str, Any]]:
    row = conn.execute("SELECT * FROM communication_endpoints WHERE provider = ? AND address = ? AND status = 'active'", (provider, address)).fetchone()
    return dict(row) if row is not None else None


def record_event(conn: sqlite3.Connection, provider: str, event_id: str, message_id: str, event_type: str, contact: str, endpoint_id: Optional[str], envelope: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    identifier, received_at = _identity()
    fingerprint = hashlib.sha256((provider + ":" + contact).encode("utf-8")).hexdigest()
    try:
        conn.execute("INSERT INTO communication_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'received', ?)", (identifier, provider, event_id, message_id or None, event_type, fingerprint, endpoint_id, _json(envelope), received_at))
        conn.commit()
        return dict(conn.execute("SELECT * FROM communication_events WHERE id = ?", (identifier,)).fetchone()), True
    except sqlite3.IntegrityError:
        conn.rollback()
        existing = conn.execute("SELECT * FROM communication_events WHERE provider = ? AND provider_event_id = ?", (provider, event_id)).fetchone()
        if existing is None:
            raise
        return dict(existing), False


def update_event_status(conn: sqlite3.Connection, event_id: str, status: str) -> None:
    conn.execute("UPDATE communication_events SET status = ? WHERE id = ?", (status, event_id))
    conn.commit()


def find_prompt_for_message(conn: sqlite3.Connection, provider_message_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute("SELECT * FROM communication_prompts WHERE provider_message_id = ?", (provider_message_id,)).fetchone()
    return dict(row) if row is not None else None


def single_open_prompt(conn: sqlite3.Connection, endpoint_id: str) -> Optional[Dict[str, Any]]:
    rows = conn.execute("SELECT * FROM communication_prompts WHERE endpoint_id = ? AND status IN ('accepted', 'delivered') ORDER BY created_at", (endpoint_id,)).fetchall()
    return dict(rows[0]) if len(rows) == 1 else None


def add_attachment(conn: sqlite3.Connection, event_id: str, source_url: str, media_type: str) -> Dict[str, Any]:
    identifier, created_at = _identity()
    reference = hashlib.sha256((event_id + ":" + source_url).encode("utf-8")).hexdigest()
    conn.execute("INSERT INTO communication_attachments VALUES (?, ?, ?, ?, 'unavailable', ?)", (identifier, event_id, reference, media_type, created_at))
    conn.commit()
    return dict(conn.execute("SELECT * FROM communication_attachments WHERE id = ?", (identifier,)).fetchone())


def create_candidate(conn: sqlite3.Connection, event_id: str, prompt_id: Optional[str], allocation_id: Optional[str], work_item_id: Optional[str], endpoint_id: Optional[str], kind: str, draft: Dict[str, Any]) -> Dict[str, Any]:
    identifier, created_at = _identity()
    conn.execute("INSERT INTO communication_candidates VALUES (?, ?, ?, ?, ?, ?, ?, 'review', ?, NULL, NULL, NULL, NULL, ?)", (identifier, event_id, prompt_id, allocation_id, work_item_id, endpoint_id, kind, _json(draft), created_at))
    conn.commit()
    return dict(conn.execute("SELECT * FROM communication_candidates WHERE id = ?", (identifier,)).fetchone())


def get_candidate(conn: sqlite3.Connection, candidate_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute("SELECT * FROM communication_candidates WHERE id = ?", (candidate_id,)).fetchone()
    return dict(row) if row is not None else None


def review_candidate(conn: sqlite3.Connection, candidate_id: str, status: str, reviewer_id: str, record_type: Optional[str] = None, record_id: Optional[str] = None) -> Dict[str, Any]:
    if status not in ("accepted", "rejected") or conn.execute("SELECT 1 FROM people WHERE id = ?", (reviewer_id,)).fetchone() is None:
        raise ValueError("invalid communication candidate review")
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("UPDATE communication_candidates SET status = ?, accepted_record_type = ?, accepted_record_id = ?, reviewed_by_person_id = ?, reviewed_at = ? WHERE id = ?", (status, record_type, record_id, reviewer_id, now, candidate_id))
    conn.commit()
    return get_candidate(conn, candidate_id)  # type: ignore[return-value]


def inbox(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    rows = conn.execute("SELECT id, kind, status, allocation_id, work_item_id, created_at FROM communication_candidates WHERE status = 'review' ORDER BY created_at").fetchall()
    return [dict(row) for row in rows]


def health(conn: sqlite3.Connection) -> Dict[str, int]:
    failed = conn.execute("SELECT count(*) FROM communication_prompts WHERE status = 'failed'").fetchone()[0]
    awaiting = conn.execute("SELECT count(*) FROM communication_prompts WHERE status IN ('accepted', 'delivered')").fetchone()[0]
    review = conn.execute("SELECT count(*) FROM communication_candidates WHERE status = 'review'").fetchone()[0]
    unknown = conn.execute("SELECT count(*) FROM communication_prompts WHERE status = 'unknown'").fetchone()[0]
    return {"failed_delivery_count": failed, "unknown_delivery_count": unknown, "awaiting_response_count": awaiting, "review_required_count": review}
