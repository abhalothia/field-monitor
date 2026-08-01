"""Season execution and learning service boundary.

This module turns the append-only V1 repository records into the small set of
season workflows used by the API.  It deliberately records observations and
timing only; it does not infer field conditions or prescribe agronomic work.
"""

from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
import json
import math
import sqlite3
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ffl.domain.models import CropAllocation, SignalTemplate
from ffl.persistence import repository
from ffl.services import templates


CALENDAR_WINDOW_DAYS = 14
_SIGNAL_STATUSES = {"draft", "submitted"}
_HARVEST_STATUSES = {"preliminary", "final"}
_REVIEW_STATUSES = {"draft", "reviewed", "published"}
_TERMINAL_WORK_STATUSES = {"accepted", "cancelled", "rejected"}
_LINKED_ENTITY_TABLES = {
    "evidence_artifact": "evidence_artifacts",
    "field_signal": "field_signals",
    "work_item": "work_items",
    "decision": "decisions",
    "harvest_record": "harvest_records",
    "crop_stage_checkpoint": "crop_stage_checkpoints",
}


def _parse_datetime(value: str, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("{0} is required".format(field_name))
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError("{0} must be an ISO-8601 date or timestamp".format(field_name)) from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_schedule_time(value: str, field_name: str) -> datetime:
    """Accept repository schedule dates as well as ISO-8601 timestamps."""
    if isinstance(value, str) and len(value) == 10:
        try:
            return datetime.combine(date.fromisoformat(value), datetime.min.time(), tzinfo=timezone.utc)
        except ValueError:
            pass
    return _parse_datetime(value, field_name)


def _nonempty_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("{0} is required".format(field_name))
    return value.strip()


def _get_allocation(conn: sqlite3.Connection, allocation_id: str) -> CropAllocation:
    row = conn.execute("SELECT * FROM crop_allocations WHERE id = ?", (allocation_id,)).fetchone()
    if row is None:
        raise ValueError("crop allocation does not exist")
    return CropAllocation(
        row["id"], row["operating_unit_id"], row["operational_block_id"], row["season_id"],
        row["crop_name"], row["cultivar"], row["area_hectares"], row["status"], row["created_at"],
    )


def _require_person(conn: sqlite3.Connection, person_id: str, field_name: str) -> None:
    _nonempty_text(person_id, field_name)
    if conn.execute("SELECT 1 FROM people WHERE id = ?", (person_id,)).fetchone() is None:
        raise ValueError("{0} does not exist".format(field_name))


def _require_evidence(conn: sqlite3.Connection, artifact_id: Optional[str]) -> None:
    if artifact_id is None:
        return
    _nonempty_text(artifact_id, "evidence_artifact_id")
    if repository.get_evidence_artifact(conn, artifact_id) is None:
        raise ValueError("evidence_artifact_id does not exist")


def _get_template(conn: sqlite3.Connection, template_id: str, template_version: int) -> SignalTemplate:
    if not isinstance(template_version, int) or isinstance(template_version, bool) or template_version < 1:
        raise ValueError("template_version must be a positive integer")
    row = conn.execute(
        "SELECT * FROM signal_templates WHERE id = ? AND version = ?", (template_id, template_version)
    ).fetchone()
    if row is None:
        raise ValueError("signal template ID and version do not match")
    if row["status"] != "published":
        raise ValueError("signal template must be published")
    return SignalTemplate(
        row["id"], row["name"], row["version"], row["status"], json.loads(row["fields_json"]),
        row["owner_id"], row["published_at"],
    )


def _calendar_timing_state(
    due_at: str, item_status: str, now: datetime, terminal_statuses: Iterable[str]
) -> str:
    if item_status == "cancelled":
        return "cancelled"
    if item_status in {"skipped", "superseded", "rejected"}:
        return "stale"
    if item_status in set(terminal_statuses):
        return "complete"
    due = _parse_schedule_time(due_at, "planned_for")
    if due < now:
        return "overdue"
    if due <= now + timedelta(days=CALENDAR_WINDOW_DAYS):
        return "within_window"
    return "scheduled"


def allocation_calendar(
    conn: sqlite3.Connection, allocation_id: str, as_of: Optional[datetime] = None
) -> Dict[str, Any]:
    """Return ordered checkpoint and work context with explicit timing state."""
    allocation = _get_allocation(conn, allocation_id)
    now = as_of or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    checkpoints = sorted(
        repository.list_crop_stage_checkpoints(conn, allocation_id),
        key=lambda item: _parse_schedule_time(item.planned_for, "planned_for"),
    )
    work_items = sorted(
        repository.list_work_items(conn, allocation_id),
        key=lambda item: _parse_schedule_time(item.due_at, "due_at"),
    )

    checkpoint_context = []
    for checkpoint in checkpoints:
        checkpoint_context.append({
            **asdict(checkpoint),
            "timing_state": _calendar_timing_state(
                checkpoint.planned_for, checkpoint.status, now, {"completed"}
            ),
        })
    work_context = []
    for work_item in work_items:
        work_context.append({
            **asdict(work_item),
            "timing_state": _calendar_timing_state(
                work_item.due_at, work_item.status, now, _TERMINAL_WORK_STATUSES
            ),
        })

    completed = [item for item in checkpoint_context if item["status"] == "completed"]
    current_stage = completed[-1] if completed else None
    pending = [
        item for item in checkpoint_context
        if item["status"] == "planned"
    ]
    next_checkpoint = pending[0] if pending else None
    return {
        "allocation": asdict(allocation),
        "as_of": now.isoformat(),
        "window_ends_at": (now + timedelta(days=CALENDAR_WINDOW_DAYS)).isoformat(),
        "current_stage": current_stage,
        "next_checkpoint": next_checkpoint,
        "checkpoints": checkpoint_context,
        "work_items": work_context,
    }


def schedule_crop_stage_checkpoint(
    conn: sqlite3.Connection, allocation_id: str, stage_name: str, planned_for: str,
    expected_evidence: Any, template_id: Optional[str] = None, template_version: Optional[int] = None,
):
    """Append a planned crop-stage checkpoint with an optional published evidence template."""
    _get_allocation(conn, allocation_id)
    _nonempty_text(stage_name, "stage_name")
    _parse_schedule_time(planned_for, "planned_for")
    if (template_id is None) != (template_version is None):
        raise ValueError("template_id and template_version must be supplied together")
    if template_id is not None and template_version is not None:
        _get_template(conn, template_id, template_version)
    return repository.create_crop_stage_checkpoint(
        conn, allocation_id, stage_name, planned_for, expected_evidence, template_id, template_version
    )


def record_field_signal(
    conn: sqlite3.Connection, allocation_id: str, template_id: str, template_version: int,
    observed_at: str, actor_id: str, values: Dict[str, Any], evidence_artifact_id: Optional[str] = None,
    status: str = "submitted",
):
    """Record a structured field observation against an immutable published template."""
    _get_allocation(conn, allocation_id)
    _require_person(conn, actor_id, "actor_id")
    _require_evidence(conn, evidence_artifact_id)
    if status not in _SIGNAL_STATUSES:
        raise ValueError("field signal status must be draft or submitted")
    _parse_datetime(observed_at, "observed_at")
    if not isinstance(values, dict):
        raise ValueError("values must be an object")
    template = _get_template(conn, template_id, template_version)
    validated_values = templates.validate_signal_payload(template, values)
    return repository.create_field_signal(
        conn, allocation_id, template_id, template_version, observed_at, actor_id, validated_values,
        evidence_artifact_id=evidence_artifact_id, status=status,
    )


def record_harvest(
    conn: sqlite3.Connection, allocation_id: str, harvest_starts_on: str, quantity: float,
    canonical_unit: str, measurement_method: str, quality_metrics: Any,
    harvest_ends_on: Optional[str] = None, evidence_artifact_id: Optional[str] = None,
    status: Optional[str] = None, correction_of_id: Optional[str] = None,
    corrected_by_person_id: Optional[str] = None, correction_reason: Optional[str] = None,
):
    """Append an output record or an accountable linked correction."""
    _get_allocation(conn, allocation_id)
    _parse_schedule_time(harvest_starts_on, "harvest_starts_on")
    if harvest_ends_on is not None:
        if _parse_schedule_time(harvest_ends_on, "harvest_ends_on") < _parse_schedule_time(
            harvest_starts_on, "harvest_starts_on"
        ):
            raise ValueError("harvest_ends_on cannot be before harvest_starts_on")
    if (
        not isinstance(quantity, (int, float))
        or isinstance(quantity, bool)
        or not math.isfinite(quantity)
        or quantity < 0
    ):
        raise ValueError("quantity must be a non-negative number")
    _nonempty_text(canonical_unit, "canonical_unit")
    _nonempty_text(measurement_method, "measurement_method")
    _require_evidence(conn, evidence_artifact_id)

    if correction_of_id is not None:
        if status not in (None, "corrected"):
            raise ValueError("harvest correction status must be corrected")
        _nonempty_text(correction_of_id, "correction_of_id")
        _require_person(conn, corrected_by_person_id or "", "corrected_by_person_id")
        _nonempty_text(correction_reason or "", "correction_reason")
        prior = repository.get_harvest_record(conn, correction_of_id)
        if prior is None:
            raise ValueError("prior harvest record does not exist")
        if prior.allocation_id != allocation_id:
            raise ValueError("harvest correction must use the predecessor allocation")
        if prior.status != "final":
            raise ValueError("harvest corrections require a final predecessor record")
        return repository.create_harvest_correction(
            conn, correction_of_id, corrected_by_person_id or "", correction_reason or "", float(quantity),
            quality_metrics, harvest_starts_on=harvest_starts_on, harvest_ends_on=harvest_ends_on,
            canonical_unit=canonical_unit, measurement_method=measurement_method,
            evidence_artifact_id=evidence_artifact_id,
        )

    if corrected_by_person_id is not None or correction_reason is not None:
        raise ValueError("correction actor and reason require correction_of_id")
    if status is None:
        status = "preliminary"
    if status not in _HARVEST_STATUSES:
        raise ValueError("harvest record status must be preliminary or final")
    return repository.create_harvest_record(
        conn, allocation_id, harvest_starts_on, float(quantity), canonical_unit, measurement_method,
        quality_metrics, harvest_ends_on=harvest_ends_on, evidence_artifact_id=evidence_artifact_id,
        status=status,
    )


def _link_reference(link: Any) -> Tuple[str, str]:
    if not isinstance(link, dict):
        raise ValueError("evidence_links entries must be objects")
    entity_type = link.get("entity_type", link.get("type"))
    entity_id = link.get("entity_id", link.get("id"))
    if entity_type not in _LINKED_ENTITY_TABLES or not isinstance(entity_id, str) or not entity_id.strip():
        raise ValueError("evidence_links entries require a supported entity_type and entity_id")
    return entity_type, entity_id


def _require_link_belongs_to_allocation(
    conn: sqlite3.Connection, allocation_id: str, entity_type: str, entity_id: str
) -> None:
    table = _LINKED_ENTITY_TABLES[entity_type]
    row = conn.execute("SELECT * FROM {0} WHERE id = ?".format(table), (entity_id,)).fetchone()
    if row is None:
        raise ValueError("evidence link does not exist")
    if entity_type != "evidence_artifact" and row["allocation_id"] != allocation_id:
        raise ValueError("evidence link must belong to the season allocation")


def _validate_review_entries(
    conn: sqlite3.Connection, allocation_id: str, category: str, entries: Any
) -> List[Dict[str, Any]]:
    if not isinstance(entries, list):
        raise ValueError("{0} must be a list of structured entries".format(category))
    if not entries:
        raise ValueError("{0} must contain at least one structured entry".format(category))
    validated = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("{0} entries must be objects".format(category))
        statement = entry.get("statement")
        if not isinstance(statement, str) or not statement.strip():
            raise ValueError("{0} entries require a non-empty statement".format(category))
        links = entry.get("evidence_links")
        if not isinstance(links, list) or not links:
            raise ValueError("{0} entries require non-empty evidence_links".format(category))
        for link in links:
            entity_type, entity_id = _link_reference(link)
            _require_link_belongs_to_allocation(conn, allocation_id, entity_type, entity_id)
        validated.append(entry)
    return validated


def record_season_review(
    conn: sqlite3.Connection, allocation_id: str, owner_id: str, confirmed_practices: Any,
    invalidated_assumptions: Any, unresolved_questions: Any, proposed_playbook_changes: Any,
    status: str = "draft", reviewed_at: Optional[str] = None,
):
    """Append an evidence-linked season learning review for one crop allocation."""
    _get_allocation(conn, allocation_id)
    _require_person(conn, owner_id, "owner_id")
    if status not in _REVIEW_STATUSES:
        raise ValueError("season review status must be draft, reviewed, or published")
    if status == "draft" and reviewed_at is not None:
        raise ValueError("draft season reviews cannot have reviewed_at")
    if status in {"reviewed", "published"}:
        if reviewed_at is None:
            raise ValueError("reviewed and published season reviews require reviewed_at")
        _parse_datetime(reviewed_at, "reviewed_at")
    return repository.create_season_review(
        conn,
        allocation_id,
        owner_id,
        _validate_review_entries(conn, allocation_id, "confirmed_practices", confirmed_practices),
        _validate_review_entries(conn, allocation_id, "invalidated_assumptions", invalidated_assumptions),
        _validate_review_entries(conn, allocation_id, "unresolved_questions", unresolved_questions),
        _validate_review_entries(conn, allocation_id, "proposed_playbook_changes", proposed_playbook_changes),
        status=status,
        reviewed_at=reviewed_at,
    )
