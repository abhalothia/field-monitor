"""A deterministic, evidence-aware daily operating brief.

This is intentionally a composition layer, not an agronomy engine.  It makes
missing foundations, open field work, and approved regional context visible in
one stable response.  It never writes farm records, calls a model, fetches a
provider, recommends an intervention, or treats external context as proof of
field conditions.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ffl.persistence import repository
from ffl.services import sources


_OPEN_WORK_STATUSES = {"planned", "in_progress", "blocked", "submitted", "rejected"}
_OPEN_EXCEPTION_STATUSES = {
    "reported", "triaged", "owned", "mitigated", "monitoring", "reopened", "accepted_risk",
}
_PRIORITY = {"critical": 0, "high": 1, "medium": 2, "info": 3}
_SOIL_REVIEW_AGE_DAYS = 365


def _normalise_now(value: Optional[datetime]) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _parse_time(value: str) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _item(
    priority: str, code: str, title: str, detail: str, entity_type: str,
    entity_id: str, action: str, provenance: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "priority": priority,
        "code": code,
        "title": title,
        "detail": detail,
        "entity": {"type": entity_type, "id": entity_id},
        "action": action,
    }
    if provenance:
        result["provenance"] = provenance
    return result


def _sort(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (_PRIORITY[item["priority"]], item["code"], item["entity"]["id"]),
    )


def morning_brief(conn, operating_unit_id: str, as_of: Optional[datetime] = None) -> Dict[str, Any]:
    """Return a source-cited, deterministic brief for one operating unit.

    ``district_context_key`` is FFL's internal regional join.  An eventual IMD
    mapping may translate it to an official provider identifier; this function
    only renders already-normalised approved regional signals.
    """
    unit = repository.get_operating_unit(conn, operating_unit_id)
    if unit is None:
        raise LookupError("operating unit not found")
    now = _normalise_now(as_of)
    attention: List[Dict[str, Any]] = []
    context: Dict[str, Any] = {}

    location = repository.get_active_operating_unit_location(conn, operating_unit_id)
    if location is None:
        context["location"] = {"status": "missing"}
        attention.append(_item(
            "high", "location_unverified", "Verify farm district",
            "District context cannot be safely joined until a manager verifies the operating location.",
            "operating_unit", unit.id, "verify_location",
        ))
    else:
        context["location"] = {
            "status": "verified",
            "country_code": location.country_code,
            "state_name": location.state_name,
            "district_name": location.district_name,
            "district_context_key": location.district_context_key,
            "subdistrict_name": location.subdistrict_name,
            "village_name": location.village_name,
            "pincode": location.pincode,
            "verification_method": location.verification_method,
            "verified_at": location.verified_at,
        }

    baselines = repository.list_soil_baselines(conn, operating_unit_id)
    if not baselines:
        context["soil"] = {"status": "missing"}
        attention.append(_item(
            "high", "soil_baseline_missing", "Add a soil baseline",
            "Upload and review the first lab report before treating soil as a managed constraint.",
            "operating_unit", unit.id, "add_soil_baseline",
        ))
    else:
        latest = baselines[0]
        sampled = _parse_time(latest.sampled_on)
        age_days = (now.date() - sampled.date()).days if sampled else None
        context["soil"] = {
            "status": "reviewed",
            "baseline_id": latest.id,
            "sampled_on": latest.sampled_on,
            "lab_name": latest.lab_name,
            "measurement_count": len(latest.measurements),
            "age_days": age_days,
            "evidence_artifact_id": latest.evidence_artifact_id,
        }
        if age_days is None or age_days > _SOIL_REVIEW_AGE_DAYS:
            attention.append(_item(
                "medium", "soil_baseline_age", "Review soil baseline freshness",
                "The latest reviewed lab sample is over a year old or has an invalid sample date.",
                "soil_baseline", latest.id, "review_soil_baseline",
                [{"kind": "evidence_artifact", "id": latest.evidence_artifact_id}],
            ))

    if location is not None:
        imd_source = repository.get_source_registry_by_key(conn, "imd-weather")
        if imd_source is None:
            context["district_weather"] = {"status": "not_configured"}
            attention.append(_item(
                "medium", "imd_not_configured", "Set up district weather context",
                "No approved IMD source is registered for this pilot yet.",
                "operating_unit", unit.id, "configure_imd",
            ))
        elif not imd_source.enabled:
            context["district_weather"] = {"status": "access_pending", "source_key": imd_source.source_key}
            attention.append(_item(
                "info", "imd_access_pending", "IMD context awaits access review",
                "The source exists but is disabled until official access, mapping, and worker approval are complete.",
                "source_registry", imd_source.id, "complete_source_admission",
            ))
        else:
            source_status = sources.get_source_status(conn, "imd-weather", now=now)
            regional = sources.regional_context(conn, location.district_context_key, now=now)
            signals = [signal for signal in regional["signals"] if signal["effective"]]
            context["district_weather"] = {
                "status": source_status["health"],
                "source_key": "imd-weather",
                "district_context_key": location.district_context_key,
                "effective_signal_count": len(signals),
                "signals": signals,
            }
            for signal in signals:
                signal_type = str(signal["signal_type"]).lower()
                priority = "high" if "warning" in signal_type or "alert" in signal_type else "info"
                attention.append(_item(
                    priority, "regional_" + signal_type, "Regional context needs review",
                    "A current regional source signal is available for manager review; it is not proof of field conditions.",
                    "regional_signal", signal["id"], "review_regional_context", [signal["provenance"]],
                ))
            if source_status["health"] not in {"healthy", "no_effective_signals"}:
                attention.append(_item(
                    "medium", "imd_source_" + source_status["health"], "Check district context source",
                    "The approved source has no current healthy operating state.",
                    "source_registry", imd_source.id, "inspect_source_health",
                ))

    work_due = []
    open_exceptions = []
    checkpoints_due = []
    for allocation in repository.list_active_crop_allocations(conn, operating_unit_id):
        for work in repository.list_work_items(conn, allocation.id):
            due = _parse_time(work.due_at)
            if work.status in _OPEN_WORK_STATUSES and due is not None and due <= now:
                work_due.append({"id": work.id, "allocation_id": allocation.id, "title": work.title, "due_at": work.due_at})
                attention.append(_item(
                    "high", "work_due", work.title, "Assigned field work is still open and due.",
                    "work_item", work.id, "complete_or_escalate",
                ))
        for checkpoint in repository.list_crop_stage_checkpoints(conn, allocation.id):
            planned = _parse_time(checkpoint.planned_for)
            if checkpoint.status == "planned" and planned is not None and planned <= now:
                checkpoints_due.append({"id": checkpoint.id, "allocation_id": allocation.id, "stage_name": checkpoint.stage_name, "planned_for": checkpoint.planned_for})
                attention.append(_item(
                    "medium", "checkpoint_due", checkpoint.stage_name, "A crop-stage checkpoint is due for field confirmation.",
                    "crop_stage_checkpoint", checkpoint.id, "complete_or_reschedule_checkpoint",
                ))
        rows = conn.execute(
            "SELECT * FROM exception_records WHERE allocation_id = ? ORDER BY observed_at, created_at", (allocation.id,)
        ).fetchall()
        for row in rows:
            if row["status"] not in _OPEN_EXCEPTION_STATUSES:
                continue
            open_exceptions.append({"id": row["id"], "allocation_id": allocation.id, "title": row["title"], "severity": row["severity"], "status": row["status"]})
            attention.append(_item(
                "critical" if row["severity"] == "critical" else "high", "exception_open", row["title"],
                "A field exception remains open and owned.", "exception_record", row["id"], "review_exception",
            ))

    attention = _sort(attention)
    return {
        "operating_unit": {"id": unit.id, "name": unit.name},
        "as_of": now.isoformat(),
        "brief_kind": "deterministic_operating_brief",
        "model_generated": False,
        "context": context,
        "attention": attention,
        "counts": {
            "attention": len(attention),
            "open_work_due": len(work_due),
            "open_exceptions": len(open_exceptions),
            "checkpoints_due": len(checkpoints_due),
        },
        "guardrails": [
            "External context is never field proof.",
            "This brief does not prescribe an intervention or change farm records.",
            "A manager must review context before assigning or closing work.",
        ],
    }
