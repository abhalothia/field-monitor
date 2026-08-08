"""Evidence-backed campaign audiences from reported field records.

These lists deliberately identify an audience, not a delivery endpoint.  They
never expose contacts or create/send messages.  A reported TrackWick farmer
only becomes messageable through the reviewed communications control plane.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
import re
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

from ffl.persistence import repository
from ffl.services.trackwick_board import source_relation_exists
from ffl.services.trackwick_ingest import SOURCE_KEY


_REPORTING_TIMEZONE = ZoneInfo("Asia/Kolkata")
_AUDIENCES = {
    "all_reported_farmers": {
        "label": "All reported farmers", "detail": "Every valid farmer record in the current source snapshot.",
    },
    "disease_reported": {
        "label": "Disease reported", "detail": "At least one reported disease finding in the source snapshot.",
    },
    "missing_transplant_date": {
        "label": "Missing transplant date", "detail": "No transplant date is recorded in any reported visit.",
    },
    "no_reported_visit": {
        "label": "No reported visit", "detail": "No valid reported field visit is linked to the farmer.",
    },
    "first_spray": {
        "label": "First spray timing", "detail": "40–50 days after one recorded transplant date.",
        "minimum_days": 40, "maximum_days": 50,
    },
    "second_spray": {
        "label": "Second spray timing", "detail": "55–60 days after one recorded transplant date.",
        "minimum_days": 55, "maximum_days": 60,
    },
    "second_spray_vayego": {
        "label": "Second spray · Vayego reported", "detail": "Second-spray timing with an applied Vayego record after transplanting.",
        "minimum_days": 55, "maximum_days": 60,
    },
}
_OPEN_TASK_STATUSES = {"pending", "in_progress"}
_VAYEGO = re.compile(r"(?<![a-z0-9])vayego(?![a-z0-9])", re.IGNORECASE)


def board_for_source(
    conn,
    *,
    source_key: str = SOURCE_KEY,
    cohort: str = "first_spray",
    offset: int = 0,
    limit: int = 40,
    evaluated_on: date | None = None,
) -> dict[str, Any]:
    """Return one paginated, manager-safe campaign audience."""
    if cohort not in _AUDIENCES:
        raise ValueError("unknown campaign audience")
    if offset < 0 or not 1 <= limit <= 100:
        raise ValueError("pagination is invalid")
    evaluated_on = evaluated_on or datetime.now(_REPORTING_TIMEZONE).date()
    source = repository.get_source_registry_by_key(conn, source_key)
    result = _empty_board(cohort, evaluated_on, offset, limit)
    if source is None:
        return result
    if not _relations_available(conn):
        result["source"]["state"] = "not_ready"
        return result

    latest_run = conn.execute(
        """SELECT status, fetched_at FROM source_runs
           WHERE source_id = ? ORDER BY created_at DESC LIMIT 1""",
        (source.id,),
    ).fetchone()
    farmers = conn.execute(
        """SELECT id, display_name FROM trackwick_parties
           WHERE source_id = ? AND party_kind = 'farmer'
             AND data_quality_status = 'valid'""",
        (source.id,),
    ).fetchall()
    visits = conn.execute(
        """SELECT task.farmer_party_id, visit.transplanted_on, visit.observed_at,
                  visit.crop_stage, visit.water_condition, visit.crop_condition_score,
                  visit.kit_status
           FROM trackwick_visits AS visit
           JOIN trackwick_tasks AS task ON task.id = visit.task_id
           WHERE visit.source_id = ? AND visit.data_quality_status = 'valid'
             AND task.data_quality_status = 'valid'
             AND task.farmer_party_id IS NOT NULL""",
        (source.id,),
    ).fetchall()
    inputs = conn.execute(
        """SELECT task.farmer_party_id, input.reported_product, input.occurred_at
           FROM trackwick_crop_inputs AS input
           JOIN trackwick_tasks AS task ON task.id = input.visit_task_id
           WHERE input.source_id = ? AND input.data_quality_status = 'valid'
             AND task.data_quality_status = 'valid' AND task.farmer_party_id IS NOT NULL
             AND input.input_kind = 'pesticide' AND input.event_kind = 'applied'""",
        (source.id,),
    ).fetchall()
    findings = conn.execute(
        """SELECT task.farmer_party_id, finding.observed_at, finding.finding_kind
           FROM trackwick_visit_findings AS finding
           JOIN trackwick_tasks AS task ON task.id = finding.visit_task_id
           WHERE finding.source_id = ? AND finding.data_quality_status = 'valid'
             AND task.data_quality_status = 'valid' AND task.farmer_party_id IS NOT NULL""",
        (source.id,),
    ).fetchall()
    tasks = conn.execute(
        """SELECT farmer_party_id, task_status FROM trackwick_tasks
           WHERE source_id = ? AND data_quality_status = 'valid'
             AND farmer_party_id IS NOT NULL""",
        (source.id,),
    ).fetchall()
    places = conn.execute(
        """SELECT farmer_party_id, village_name, block_name, district_name
           FROM trackwick_registrations
           WHERE source_id = ? AND data_quality_status = 'valid'
             AND farmer_party_id IS NOT NULL""",
        (source.id,),
    ).fetchall()

    records = _timing_records(
        farmers, visits, inputs, findings, tasks, places, evaluated_on,
    )
    cohort_records = _audience_records(records)
    selected = cohort_records[cohort]
    result["source"] = {
        "state": latest_run["status"] if latest_run is not None else "registered",
        "last_synced_at": latest_run["fetched_at"] if latest_run is not None else None,
        "data_through": _latest_observed_at(visits),
    }
    result["summary"] = _summary(farmers, records, cohort_records)
    result["cohorts"] = [
        {"key": key, **values, "count": len(cohort_records[key])}
        for key, values in _AUDIENCES.items()
    ]
    result["records"] = selected[offset:offset + limit]
    result["page"] = {"offset": offset, "limit": limit, "total": len(selected), "has_more": offset + limit < len(selected)}
    return result


def _relations_available(conn) -> bool:
    return all(source_relation_exists(conn, relation) for relation in (
        "trackwick_parties", "trackwick_tasks", "trackwick_visits",
        "trackwick_crop_inputs", "trackwick_visit_findings", "trackwick_registrations",
    ))


def _timing_records(
    farmers: Iterable[Mapping[str, Any]],
    visits: Iterable[Mapping[str, Any]],
    inputs: Iterable[Mapping[str, Any]],
    findings: Iterable[Mapping[str, Any]],
    tasks: Iterable[Mapping[str, Any]],
    places: Iterable[Mapping[str, Any]],
    evaluated_on: date,
) -> dict[str, dict[str, Any]]:
    visits_by_farmer: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in visits:
        visits_by_farmer[str(row["farmer_party_id"])].append(row)
    inputs_by_farmer: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in inputs:
        inputs_by_farmer[str(row["farmer_party_id"])].append(row)
    finding_dates: dict[str, list[date]] = defaultdict(list)
    disease_dates: dict[str, list[date]] = defaultdict(list)
    for row in findings:
        observed = _as_date(row["observed_at"])
        if observed is not None:
            finding_dates[str(row["farmer_party_id"])].append(observed)
            if str(row["finding_kind"]).casefold() == "disease":
                disease_dates[str(row["farmer_party_id"])].append(observed)
    open_work: dict[str, int] = defaultdict(int)
    for row in tasks:
        if str(row["task_status"]) in _OPEN_TASK_STATUSES:
            open_work[str(row["farmer_party_id"])] += 1
    places_by_farmer: dict[str, set[str]] = defaultdict(set)
    for row in places:
        place = " · ".join(str(value).strip() for value in (
            row["village_name"], row["block_name"], row["district_name"],
        ) if value and str(value).strip())
        if place:
            places_by_farmer[str(row["farmer_party_id"])].add(place)

    result: dict[str, dict[str, Any]] = {}
    for farmer in farmers:
        farmer_id = str(farmer["id"])
        rows = visits_by_farmer.get(farmer_id, [])
        transplant_dates = {parsed for row in rows if (parsed := _as_date(row["transplanted_on"])) is not None}
        latest_visit = max(rows, key=lambda row: str(row["observed_at"] or "")) if rows else None
        latest_visit_on = _as_date(latest_visit["observed_at"]) if latest_visit else None
        places_for_farmer = places_by_farmer.get(farmer_id, set())
        disease_for_farmer = disease_dates.get(farmer_id, [])
        base = {
            "id": farmer_id,
            "name": str(farmer["display_name"]),
            "state": "excluded",
            "latest_field_record_at": latest_visit["observed_at"] if latest_visit else None,
            "latest_field_record_on": latest_visit_on.isoformat() if latest_visit_on else None,
            "reported_disease": bool(disease_for_farmer),
            "latest_disease_reported_on": max(disease_for_farmer).isoformat() if disease_for_farmer else None,
            "open_work": open_work.get(farmer_id, 0),
            "place": next(iter(places_for_farmer)) if len(places_for_farmer) == 1 else None,
            "place_status": "multiple_reported_places" if len(places_for_farmer) > 1 else "reported" if places_for_farmer else "not_reported",
        }
        if not transplant_dates:
            result[farmer_id] = {**base, "exclusion": "No recorded transplant date"}
            continue
        if len(transplant_dates) != 1:
            result[farmer_id] = {**base, "exclusion": "More than one recorded transplant date"}
            continue
        transplanted_on = next(iter(transplant_dates))
        matching_visits = [row for row in rows if _as_date(row["transplanted_on"]) == transplanted_on]
        latest_visit = max(matching_visits, key=lambda row: str(row["observed_at"] or ""))
        applied_inputs = [
            row for row in inputs_by_farmer.get(farmer_id, [])
            if (occurred := _as_date(row["occurred_at"])) is not None and occurred >= transplanted_on
        ]
        reported_vayego = any(_is_vayego(row["reported_product"]) for row in applied_inputs)
        has_reported_issue = any(item >= transplanted_on for item in finding_dates.get(farmer_id, []))
        result[farmer_id] = {
            **base,
            "state": "timed",
            "transplanted_on": transplanted_on.isoformat(),
            "days_since_transplant": (evaluated_on - transplanted_on).days,
            "latest_field_record_at": latest_visit["observed_at"],
            "latest_field_record_on": latest_visit_on.isoformat() if latest_visit_on else None,
            "crop_stage": latest_visit["crop_stage"],
            "kit_status": latest_visit["kit_status"],
            "reported_vayego_applied": reported_vayego,
            "reported_issue_since_transplant": has_reported_issue,
        }
    return result


def _for_window(records: Mapping[str, Mapping[str, Any]], minimum_days: int, maximum_days: int, *, vayego_only: bool) -> list[dict[str, Any]]:
    selected = [
        dict(record) for record in records.values()
        if record.get("state") == "timed"
        and minimum_days <= int(record["days_since_transplant"]) <= maximum_days
        and (not vayego_only or bool(record["reported_vayego_applied"]))
    ]
    return sorted(selected, key=lambda record: (-int(record["days_since_transplant"]), str(record["name"]).casefold()))


def _audience_records(records: Mapping[str, Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Keep the campaign criteria narrow, explicit, and independently auditable."""
    audiences = {
        "all_reported_farmers": sorted(
            (dict(record) for record in records.values()), key=lambda record: str(record["name"]).casefold(),
        ),
        "disease_reported": sorted(
            (dict(record) for record in records.values() if record.get("reported_disease")),
            key=lambda record: (str(record.get("latest_disease_reported_on") or ""), str(record["name"]).casefold()),
            reverse=True,
        ),
        "missing_transplant_date": sorted(
            (dict(record) for record in records.values() if record.get("exclusion") == "No recorded transplant date"),
            key=lambda record: str(record["name"]).casefold(),
        ),
        "no_reported_visit": sorted(
            (dict(record) for record in records.values() if record.get("latest_field_record_at") is None),
            key=lambda record: str(record["name"]).casefold(),
        ),
    }
    audiences.update({
        key: _for_window(records, values["minimum_days"], values["maximum_days"], vayego_only=key == "second_spray_vayego")
        for key, values in _AUDIENCES.items()
        if "minimum_days" in values
    })
    return audiences


def _summary(
    farmers: Iterable[Mapping[str, Any]],
    records: Mapping[str, Mapping[str, Any]],
    cohorts: Mapping[str, list[Mapping[str, Any]]],
) -> dict[str, int]:
    values = list(records.values())
    return {
        "reported_farmers": len(list(farmers)),
        "all_reported_farmers": len(cohorts["all_reported_farmers"]),
        "timing_available": sum(record.get("state") == "timed" for record in values),
        "missing_transplant_date": sum(record.get("exclusion") == "No recorded transplant date" for record in values),
        "ambiguous_transplant_dates": sum(record.get("exclusion") == "More than one recorded transplant date" for record in values),
        "first_timing": len(cohorts["first_spray"]),
        "second_timing": len(cohorts["second_spray"]),
        "second_timing_vayego": len(cohorts["second_spray_vayego"]),
        "disease_reported": len(cohorts["disease_reported"]),
        "no_reported_visit": len(cohorts["no_reported_visit"]),
    }


def _latest_observed_at(rows: Iterable[Mapping[str, Any]]) -> str | None:
    values = [str(row["observed_at"]) for row in rows if row["observed_at"]]
    return max(values, default=None)


def _is_vayego(value: Any) -> bool:
    return isinstance(value, str) and bool(_VAYEGO.search(value.strip()))


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _empty_board(cohort: str, evaluated_on: date, offset: int, limit: int) -> dict[str, Any]:
    return {
        "selected_cohort": cohort,
        "evaluated_on": evaluated_on.isoformat(),
        "source": {"state": "not_configured", "last_synced_at": None, "data_through": None},
        "summary": {
            "reported_farmers": 0, "all_reported_farmers": 0, "timing_available": 0, "missing_transplant_date": 0,
            "ambiguous_transplant_dates": 0, "first_timing": 0, "second_timing": 0,
            "second_timing_vayego": 0, "disease_reported": 0, "no_reported_visit": 0,
        },
        "cohorts": [{"key": key, **values, "count": 0} for key, values in _AUDIENCES.items()],
        "records": [],
        "page": {"offset": offset, "limit": limit, "total": 0, "has_more": False},
        "delivery": {
            "state": "audience_ready",
            "detail": "Audience only. Delivery starts after a verified recipient, consent, approved template, and sender are selected.",
        },
    }
