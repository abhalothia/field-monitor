import sqlite3

from ffl.domain.models import AuditEvent, Decision, ExceptionRecord, WorkItem
from ffl.domain.transitions import EXCEPTION_TRANSITIONS, WORK_TRANSITIONS
from ffl.persistence import repository


def create_work_item(
    conn: sqlite3.Connection, allocation_id: str, title: str, owner_id: str, due_at: str,
    initial_status: str = "in_progress",
) -> WorkItem:
    if initial_status not in WORK_TRANSITIONS:
        raise ValueError("invalid work status")
    return repository.create_work_item(
        conn, allocation_id, title, owner_id, due_at, initial_status
    )


def transition_work_item(
    conn: sqlite3.Connection, work_item_id: str, target_status: str, actor_id: str, reason: str
) -> WorkItem:
    work_item = repository.get_work_item(conn, work_item_id)
    if work_item is None or target_status not in WORK_TRANSITIONS.get(work_item.status, set()):
        raise ValueError("invalid work transition")
    return repository.transition_work_item_with_audit(
        conn, work_item_id, work_item.status, target_status, actor_id, reason
    )


def report_exception(
    conn: sqlite3.Connection, allocation_id: str, title: str, severity: str, owner_id: str,
    fallback_owner_id: str, observed_at: str, idempotency_key: str,
) -> ExceptionRecord:
    existing = repository.get_exception_by_idempotency_key(conn, idempotency_key)
    if existing is not None:
        return existing
    return repository.create_exception_record(
        conn, allocation_id, title, severity, owner_id, fallback_owner_id, observed_at, idempotency_key
    )


def transition_exception(
    conn: sqlite3.Connection, exception_id: str, target_status: str, actor_id: str, reason: str
) -> ExceptionRecord:
    exception = repository.get_exception_record(conn, exception_id)
    if exception is None or target_status not in EXCEPTION_TRANSITIONS.get(exception.status, set()):
        raise ValueError("invalid exception transition")
    return repository.transition_exception_with_audit(
        conn, exception_id, exception.status, target_status, actor_id, reason
    )


def create_decision(
    conn: sqlite3.Connection, allocation_id: str, title: str, owner_id: str, review_due_at: str
) -> Decision:
    return repository.create_decision(conn, allocation_id, title, owner_id, review_due_at)


def list_audit_events(
    conn: sqlite3.Connection, entity_type: str, entity_id: str
) -> list[AuditEvent]:
    return repository.list_audit_events(conn, entity_type, entity_id)
