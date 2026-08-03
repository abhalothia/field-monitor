"""Read-only manager portfolio aggregation for the FFL operating record.

This module deliberately composes canonical records rather than creating a
second operational state.  It keeps evidence payloads, private storage
references, source endpoints, credentials, and provider payloads out of the
manager-facing summary.
"""

from collections import Counter
from datetime import date, datetime, timedelta, timezone
import sqlite3
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ffl.persistence import repository
from ffl.services import sources


CHECKPOINT_WINDOW_DAYS = 14
SUMMARY_ITEM_LIMIT = 25
LEDGER_ITEM_LIMIT = 50

_OPEN_WORK_STATUSES = {"planned", "in_progress", "blocked", "submitted", "rejected"}
_OPEN_EXCEPTION_STATUSES = {
    "reported", "triaged", "owned", "mitigated", "monitoring", "reopened", "accepted_risk",
}
_SOURCE_ATTENTION_HEALTH = {
    "failed", "unavailable", "quarantined", "pending", "stale", "no_effective_signals", "not_run",
}
_PRIORITY = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalise_now(value: Optional[datetime]) -> datetime:
    current = value or _utc_now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def parse_as_of(value: str) -> datetime:
    """Parse an API ``as_of`` parameter without accepting a local timezone guess."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("as_of must be an ISO-8601 date or timestamp")
    try:
        if len(value) == 10:
            parsed = datetime.combine(date.fromisoformat(value), datetime.min.time(), tzinfo=timezone.utc)
        else:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("as_of must be an ISO-8601 date or timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError("as_of timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


def _parse_schedule_time(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        if len(value) == 10:
            parsed = datetime.combine(date.fromisoformat(value), datetime.min.time(), tzinfo=timezone.utc)
        else:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    try:
        if getattr(conn, "dialect", "sqlite") == "postgres":
            return conn.execute(
                "SELECT to_regclass(?) AS relation_name", ("agro_" + table_name,)
            ).fetchone()["relation_name"] is not None
        return conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table_name,)
        ).fetchone() is not None
    except sqlite3.Error:
        return False


def _safe_rows(
    conn: sqlite3.Connection, table_name: str, query: str, params: Sequence[Any] = ()
) -> Tuple[str, List[Dict[str, Any]]]:
    """Return a manager-safe availability state instead of leaking DB failures."""
    if not _table_exists(conn, table_name):
        return "not_configured", []
    try:
        return "available", [dict(row) for row in conn.execute(query, tuple(params)).fetchall()]
    except (sqlite3.Error, TypeError, ValueError):
        return "unavailable", []


def _availability(*states: str) -> str:
    if "unavailable" in states:
        return "unavailable"
    if "not_configured" in states:
        return "not_configured"
    return "available"


def _counts(rows: Iterable[Dict[str, Any]], field_name: str) -> Dict[str, int]:
    return dict(sorted(Counter(str(row.get(field_name, "unknown")) for row in rows).items()))


def _limited(items: List[Dict[str, Any]], limit: int = SUMMARY_ITEM_LIMIT) -> Dict[str, Any]:
    return {
        "items": items[:limit],
        "displayed_count": min(len(items), limit),
        "total_count": len(items),
        "truncated": len(items) > limit,
    }


def _ledger_item(
    severity: str, action: str, entity_type: str, entity_id: str, status: str,
    title: str, owner_id: Optional[str] = None, allocation_id: Optional[str] = None,
    due_at: Optional[str] = None, observed_at: Optional[str] = None, reason_code: Optional[str] = None,
    proof_required: Optional[bool] = None,
) -> Dict[str, Any]:
    result = {
        "severity": severity,
        "action": action,
        "entity": {"type": entity_type, "id": entity_id},
        "status": status,
        "title": title,
    }
    if owner_id:
        result["owner_id"] = owner_id
    if allocation_id:
        result["allocation_id"] = allocation_id
    if due_at:
        result["due_at"] = due_at
    if observed_at:
        result["observed_at"] = observed_at
    if reason_code:
        result["reason_code"] = reason_code
    if proof_required is not None:
        result["proof_required"] = proof_required
    return result


def _sort_ledger(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (
            _PRIORITY.get(str(item["severity"]), _PRIORITY["medium"]),
            item.get("due_at") or item.get("observed_at") or "",
            item["entity"]["type"],
            item["entity"]["id"],
        ),
    )


def _scope(conn: sqlite3.Connection) -> Dict[str, Any]:
    unit_state, units = _safe_rows(
        conn,
        "operating_units",
        "SELECT id, name FROM operating_units ORDER BY name, id",
    )
    allocation_state, allocations = _safe_rows(
        conn,
        "crop_allocations",
        """SELECT id, operating_unit_id, operational_block_id, season_id, crop_name, cultivar, status
           FROM crop_allocations WHERE status = 'active' ORDER BY created_at, id""",
    )
    active_count_by_unit = Counter(row["operating_unit_id"] for row in allocations)
    active_farms = [
        {"id": unit["id"], "name": unit["name"], "active_allocation_count": active_count_by_unit[unit["id"]]}
        for unit in units if active_count_by_unit[unit["id"]]
    ]
    return {
        "availability": _availability(unit_state, allocation_state),
        "active_farms": {"count": len(active_farms), "items": active_farms},
        "active_allocations": {"count": len(allocations), "items": allocations},
    }


def _work_summary(conn: sqlite3.Connection, now: datetime) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    state, rows = _safe_rows(
        conn,
        "work_items",
        """SELECT id, allocation_id, title, owner_id, due_at, status
           FROM work_items ORDER BY due_at, created_at, id""",
    )
    overdue = []
    rejected = []
    ledger = []
    for row in rows:
        schedule = _parse_schedule_time(row.get("due_at"))
        if row.get("status") in _OPEN_WORK_STATUSES and schedule is not None and schedule < now:
            overdue.append(row)
            ledger.append(_ledger_item(
                "high", "resolve_or_replan_work", "work_item", row["id"], row["status"], row["title"],
                owner_id=row["owner_id"], allocation_id=row["allocation_id"], due_at=row["due_at"],
                reason_code="overdue_work",
            ))
        if row.get("status") == "rejected":
            rejected.append(row)
            ledger.append(_ledger_item(
                "medium", "rework_or_cancel_work", "work_item", row["id"], row["status"], row["title"],
                owner_id=row["owner_id"], allocation_id=row["allocation_id"], due_at=row["due_at"],
                reason_code="rejected_rework",
            ))
    return {
        "availability": state,
        "by_status": _counts(rows, "status"),
        "overdue": _limited(overdue),
        "rejected_rework": _limited(rejected),
    }, ledger


def _exception_summary(conn: sqlite3.Connection) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    state, rows = _safe_rows(
        conn,
        "exception_records",
        """SELECT id, allocation_id, title, severity, owner_id, fallback_owner_id, observed_at, status
           FROM exception_records ORDER BY observed_at, created_at, id""",
    )
    open_items = [row for row in rows if row.get("status") in _OPEN_EXCEPTION_STATUSES]
    ledger = []
    for row in open_items:
        severity = str(row.get("severity", "medium")).lower()
        if severity not in _PRIORITY:
            severity = "medium"
        ledger.append(_ledger_item(
            severity,
            "own_or_review_exception" if row["status"] != "accepted_risk" else "review_accepted_risk",
            "exception_record",
            row["id"],
            row["status"],
            row["title"],
            owner_id=row["owner_id"],
            allocation_id=row["allocation_id"],
            observed_at=row["observed_at"],
            reason_code="open_exception",
        ))
    return {
        "availability": state,
        "by_status": _counts(rows, "status"),
        "by_severity": _counts(rows, "severity"),
        "open": _limited(open_items),
    }, ledger


def _checkpoint_summary(conn: sqlite3.Connection, now: datetime) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    state, rows = _safe_rows(
        conn,
        "crop_stage_checkpoints",
        """SELECT id, allocation_id, stage_name, planned_for, status, template_id, template_version
           FROM crop_stage_checkpoints ORDER BY planned_for, created_at, id""",
    )
    upcoming = []
    overdue = []
    window_end = now + timedelta(days=CHECKPOINT_WINDOW_DAYS)
    ledger = []
    for row in rows:
        planned_for = _parse_schedule_time(row.get("planned_for"))
        if row.get("status") != "planned" or planned_for is None:
            continue
        if planned_for < now:
            overdue.append(row)
            ledger.append(_ledger_item(
                "high", "complete_or_reschedule_checkpoint", "crop_stage_checkpoint", row["id"],
                row["status"], row["stage_name"], allocation_id=row["allocation_id"],
                due_at=row["planned_for"], reason_code="overdue_checkpoint",
            ))
        elif planned_for <= window_end:
            upcoming.append(row)
            ledger.append(_ledger_item(
                "medium", "prepare_checkpoint", "crop_stage_checkpoint", row["id"], row["status"],
                row["stage_name"], allocation_id=row["allocation_id"], due_at=row["planned_for"],
                reason_code="upcoming_checkpoint",
            ))
    return {
        "availability": state,
        "window_days": CHECKPOINT_WINDOW_DAYS,
        "upcoming": _limited(upcoming),
        "overdue": _limited(overdue),
    }, ledger


def _import_summary(conn: sqlite3.Connection) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    batch_state, batches = _safe_rows(
        conn,
        "import_batches",
        """SELECT id, purpose, status, owner_id, reviewed_by_id, received_at, reviewed_at, published_at
           FROM import_batches ORDER BY received_at, created_at, id""",
    )
    row_state, rows = _safe_rows(
        conn,
        "import_rows",
        "SELECT import_batch_id, status FROM import_rows ORDER BY import_batch_id, row_number",
    )
    review_required = [batch for batch in batches if batch.get("status") == "profiled"]
    ready_to_publish = [batch for batch in batches if batch.get("status") == "review"]
    failures = [batch for batch in batches if batch.get("status") in {"quarantined", "failed"}]
    ledger = []
    for batch in review_required:
        ledger.append(_ledger_item(
            "medium", "review_import", "import_batch", batch["id"], batch["status"], batch["purpose"],
            owner_id=batch["owner_id"], due_at=batch["received_at"], reason_code="import_review_required",
        ))
    for batch in ready_to_publish:
        ledger.append(_ledger_item(
            "low", "approve_or_quarantine_import", "import_batch", batch["id"], batch["status"],
            batch["purpose"], owner_id=batch["owner_id"], due_at=batch.get("reviewed_at"),
            reason_code="import_ready_to_publish",
        ))
    for batch in failures:
        ledger.append(_ledger_item(
            "medium", "inspect_import_failure", "import_batch", batch["id"], batch["status"],
            batch["purpose"], owner_id=batch["owner_id"], due_at=batch["received_at"],
            reason_code="import_" + str(batch["status"]),
        ))
    return {
        "availability": _availability(batch_state, row_state),
        "batches_by_status": _counts(batches, "status"),
        "rows_by_status": _counts(rows, "status"),
        "review_required": _limited(review_required),
        "ready_to_publish": _limited(ready_to_publish),
        "failures": _limited(failures),
    }, ledger


def _source_summary(conn: sqlite3.Connection, now: datetime) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    registry_state, source_rows = _safe_rows(
        conn,
        "source_registry",
        "SELECT id, source_key, display_name, owner_id, enabled FROM source_registry ORDER BY source_key, id",
    )
    if registry_state != "available":
        return {
            "availability": registry_state,
            "configured_count": 0,
            "health_by_status": {},
            "attention": _limited([]),
        }, []
    if not source_rows:
        return {
            "availability": "not_configured",
            "configured_count": 0,
            "health_by_status": {},
            "attention": _limited([]),
        }, []

    rendered = []
    ledger = []
    for row in source_rows:
        try:
            source = repository.get_source_registry(conn, row["id"])
            if source is None:
                raise LookupError("source disappeared")
            manager_status = sources.source_status(conn, source, now=now)
            item = {
                "id": row["id"],
                "source_key": manager_status["source_key"],
                "display_name": manager_status["display_name"],
                "owner_id": row["owner_id"],
                "enabled": manager_status["enabled"],
                "health": manager_status["health"],
                "freshness": manager_status["freshness"],
                "latest_run": manager_status["latest_run"],
                "effective_regional_signal_count": manager_status["effective_regional_signal_count"],
            }
        except (LookupError, ValueError, sqlite3.Error, TypeError):
            item = {
                "id": row["id"],
                "source_key": row["source_key"],
                "display_name": row["display_name"],
                "owner_id": row["owner_id"],
                "enabled": bool(row["enabled"]),
                "health": "unavailable",
                "freshness": "unknown",
                "latest_run": None,
                "effective_regional_signal_count": 0,
                "reason_code": "source_record_unavailable",
            }
        rendered.append(item)
        if item["enabled"] and item["health"] in _SOURCE_ATTENTION_HEALTH:
            reason_code = item.get("reason_code")
            if not reason_code and item["latest_run"]:
                reason_code = item["latest_run"].get("reason_code")
            ledger.append(_ledger_item(
                "medium", "inspect_or_refresh_source", "source_registry", item["id"], item["health"],
                item["display_name"], owner_id=item["owner_id"], reason_code=reason_code or item["health"],
            ))
    attention = [item for item in rendered if item["enabled"] and item["health"] in _SOURCE_ATTENTION_HEALTH]
    return {
        "availability": "available",
        "configured_count": len(rendered),
        "health_by_status": _counts(rendered, "health"),
        "attention": _limited(attention),
    }, ledger


def _field_signal_summary(conn: sqlite3.Connection) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    state, rows = _safe_rows(
        conn,
        "field_signals",
        """SELECT id, allocation_id, template_id, template_version, observed_at, received_at, actor_id,
                  evidence_artifact_id, status
           FROM field_signals ORDER BY received_at, created_at, id""",
    )
    open_items = []
    ledger = []
    for row in rows:
        if row.get("status") not in {"draft", "submitted"}:
            continue
        item = {
            "id": row["id"],
            "allocation_id": row["allocation_id"],
            "template_id": row["template_id"],
            "template_version": row["template_version"],
            "observed_at": row["observed_at"],
            "received_at": row["received_at"],
            "actor_id": row["actor_id"],
            "status": row["status"],
            "evidence_attached": row["evidence_artifact_id"] is not None,
        }
        open_items.append(item)
        ledger.append(_ledger_item(
            "medium", "review_field_signal", "field_signal", row["id"], row["status"],
            "Field signal review", owner_id=row["actor_id"], allocation_id=row["allocation_id"],
            observed_at=row["observed_at"], reason_code="open_field_signal",
        ))
    return {
        "availability": state,
        "scope": "canonical_field_signals_only",
        "by_status": _counts(rows, "status"),
        "open": _limited(open_items),
    }, ledger


def _field_information_request_summary(
    conn: sqlite3.Connection, now: datetime
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Summarise field asks without exposing their message copy or reply content.

    The ledger makes the request's operational state legible: a draft still
    needs manager review, a ready request still needs an independently gated
    delivery decision, and a dispatched request still needs a reviewed field
    response.  None of these states completes linked work or proves a field
    condition.
    """

    state, rows = _safe_rows(
        conn,
        "field_information_requests",
        """SELECT id, allocation_id, target_person_id, request_kind, evidence_required, due_at, status
           FROM field_information_requests ORDER BY due_at, created_at, id""",
    )
    open_items = []
    ledger = []
    for row in rows:
        request_status = str(row.get("status", ""))
        if request_status not in {"draft", "ready", "dispatched"}:
            continue
        due_at = _parse_schedule_time(row.get("due_at"))
        overdue = due_at is not None and due_at <= now
        request_kind = str(row.get("request_kind", "field_check"))
        item = {
            "id": row["id"],
            "allocation_id": row["allocation_id"],
            "target_person_id": row["target_person_id"],
            "request_kind": request_kind,
            "evidence_required": bool(row["evidence_required"]),
            "due_at": row["due_at"],
            "status": request_status,
        }
        open_items.append(item)

        if request_status == "draft":
            severity, action, title, reason_code = (
                "medium", "review_field_request", "Field ask needs review", "field_request_draft",
            )
        elif request_status == "ready":
            severity, action, title, reason_code = (
                ("high" if overdue else "medium"),
                "review_delivery_eligibility",
                ("Field ask missed delivery window" if overdue else "Field ask awaits delivery decision"),
                ("field_request_not_dispatched" if overdue else "field_request_ready"),
            )
        else:
            severity, action, title, reason_code = (
                ("high" if overdue else "medium"),
                "review_field_response_or_recover",
                ("Field answer is overdue" if overdue else "Awaiting field answer"),
                ("field_request_response_overdue" if overdue else "field_request_dispatched"),
            )
        ledger.append(_ledger_item(
            severity, action, "field_information_request", row["id"], request_status, title,
            owner_id=row["target_person_id"], allocation_id=row["allocation_id"], due_at=row["due_at"],
            reason_code=reason_code, proof_required=bool(row["evidence_required"]),
        ))

    return {
        "availability": state,
        "scope": "request_metadata_only",
        "by_status": _counts(rows, "status"),
        "open": _limited(open_items),
    }, ledger


def _learning_summary(conn: sqlite3.Connection) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    trial_state, trials = _safe_rows(
        conn,
        "trials",
        "SELECT id, name, owner_id, protocol_version, status, starts_on, ends_on FROM trials ORDER BY created_at, id",
    )
    playbook_state, playbooks = _safe_rows(
        conn,
        "playbooks",
        "SELECT id, name, version, owner_id, status, effective_from FROM playbooks ORDER BY name, version, id",
    )
    trial_attention = [trial for trial in trials if trial.get("status") in {"paused", "stopped"}]
    playbook_attention = [playbook for playbook in playbooks if playbook.get("status") == "review"]
    ledger = []
    for trial in trial_attention:
        ledger.append(_ledger_item(
            "high" if trial["status"] == "paused" else "medium", "review_trial", "trial", trial["id"],
            trial["status"], trial["name"], owner_id=trial["owner_id"],
            due_at=trial.get("starts_on"), reason_code="trial_" + trial["status"],
        ))
    for playbook in playbook_attention:
        ledger.append(_ledger_item(
            "low", "review_playbook", "playbook", playbook["id"], playbook["status"], playbook["name"],
            owner_id=playbook["owner_id"], due_at=playbook.get("effective_from"),
            reason_code="playbook_review",
        ))
    return {
        "availability": _availability(trial_state, playbook_state),
        "trials": {
            "by_status": _counts(trials, "status"),
            "attention": _limited(trial_attention),
        },
        "playbooks": {
            "by_status": _counts(playbooks, "status"),
            "attention": _limited(playbook_attention),
        },
    }, ledger


def portfolio_snapshot(conn: sqlite3.Connection, as_of: Optional[datetime] = None) -> Dict[str, Any]:
    """Produce a bounded portfolio view without mutating the operating record."""
    now = _normalise_now(as_of)
    work, work_ledger = _work_summary(conn, now)
    exceptions, exception_ledger = _exception_summary(conn)
    checkpoints, checkpoint_ledger = _checkpoint_summary(conn, now)
    imports, import_ledger = _import_summary(conn)
    source_health, source_ledger = _source_summary(conn, now)
    field_signals, signal_ledger = _field_signal_summary(conn)
    field_information_requests, field_request_ledger = _field_information_request_summary(conn, now)
    learning, learning_ledger = _learning_summary(conn)
    ledger = _sort_ledger(
        work_ledger + exception_ledger + checkpoint_ledger + import_ledger + source_ledger + signal_ledger
        + field_request_ledger + learning_ledger
    )
    return {
        "as_of": now.isoformat(),
        "scope": _scope(conn),
        "work": work,
        "exceptions": exceptions,
        "crop_stage_checkpoints": checkpoints,
        "imports": imports,
        "sources": source_health,
        "field_signals": field_signals,
        "field_information_requests": field_information_requests,
        "learning": learning,
        "risk_action_ledger": _limited(ledger, LEDGER_ITEM_LIMIT),
    }
