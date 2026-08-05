"""Deterministic, browser-safe Farm Truth candidate discovery.

TrackWick remains a read-only evidence source.  This service reads only its
typed private tables and reviewed source links, persists an allowlisted review
summary, and never returns source identifiers or sensitive source material.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any, Iterable, Mapping, Optional

from ffl.persistence import repository


_QUEUE_LIMIT = 50
_INBOX_REASON_LABELS = {
    "plot_area": "Confirm plot area",
    "crop_season": "Confirm crop and season",
    "right_to_operate": "Confirm right to operate",
    "farmer_identity": "Confirm farmer identity",
    "field_worker_assignment": "Confirm field worker assignment",
}


def refresh_farm_truth_cases(
    conn,
    operating_unit_id: str,
    season_id: str,
    actor_id: str,
) -> list[dict[str, Any]]:
    """Persist all currently eligible cases and return the top safe 50.

    A candidate is exactly one registration and one plot.  Visits and open
    work are linked only by the registration's source/farmer pair; no spatial,
    contact, media, provider, or heuristic identity join is permitted.
    """
    season = repository.get_season(conn, season_id)
    if season is None or season.operating_unit_id != operating_unit_id:
        raise ValueError("season does not belong to operating unit")
    if conn.execute("SELECT 1 FROM people WHERE id = ?", (actor_id,)).fetchone() is None:
        raise ValueError("actor does not exist")

    source_ids = _trackwick_source_ids(conn)
    queue_context_keys = [
        _queue_context_key(source_id, operating_unit_id, season_id)
        for source_id in source_ids
    ]
    repository.clear_current_farm_truth_open_cases(conn, queue_context_keys)
    candidates = _candidate_rows(conn)
    tasks_by_farmer = _supporting_tasks(conn)
    current_cases = []
    for candidate in candidates:
        key = (str(candidate["source_id"]), str(candidate["farmer_party_id"]))
        support = tasks_by_farmer.get(key, ())
        visits = [
            task for task in support
            if task["support_kind"] == "visit"
            and _date_in_window(task["observed_at"], season.starts_on, season.ends_on)
        ]
        if not visits:
            continue
        open_work = [task for task in support if task["support_kind"] == "open_work"]
        visits.sort(key=lambda row: (_timestamp_value(row["observed_at"]), str(row["id"])))
        open_work.sort(key=lambda row: str(row["id"]))
        eligible_tasks = [
            {
                "id": candidate["registration_task_id"],
                "source_fingerprint": candidate["registration_task_fingerprint"],
                "status": candidate["registration_task_status"],
            },
            *(
                {
                    "id": task["id"],
                    "source_fingerprint": task["source_fingerprint"],
                    "visit_source_fingerprint": task["visit_source_fingerprint"],
                    "status": task["task_status"],
                }
                for task in (*visits, *open_work)
            ),
        ]
        eligible_tasks.sort(key=lambda task: str(task["id"]))
        fingerprint = _candidate_fingerprint(candidate, eligible_tasks)
        summary = _evidence_summary(candidate, visits, open_work)
        existing = repository.get_farm_truth_case_by_candidate(
            conn, str(candidate["plot_id"]), fingerprint
        )
        contexts = _queue_contexts(existing.evidence_summary if existing is not None else {})
        context_key = _queue_context_key(
            str(candidate["source_id"]), operating_unit_id, season_id
        )
        contexts[context_key] = True
        summary["_queue_contexts"] = contexts
        case = repository.create_or_refresh_farm_truth_case(
            conn,
            source_id=str(candidate["source_id"]),
            registration_id=str(candidate["registration_id"]),
            plot_id=str(candidate["plot_id"]),
            candidate_fingerprint=fingerprint,
            evidence_summary=summary,
        )
        if case.status == "open":
            current_cases.append(case)

    current_cases.sort(key=_case_sort_key)
    return [_serialize_case(case) for case in current_cases[:_QUEUE_LIMIT]]


def list_farm_truth_case_summaries(
    conn,
    operating_unit_id: str,
    season_id: str,
    status: str = "open",
    limit: int = _QUEUE_LIMIT,
) -> list[dict[str, Any]]:
    """List the newest receipt per plot as bounded, allowlisted summaries."""
    _validate_queue_limit(limit)
    _require_season_context(conn, operating_unit_id, season_id)
    context_keys = [
        _queue_context_key(source_id, operating_unit_id, season_id)
        for source_id in _trackwick_source_ids(conn)
    ]
    cases = repository.list_latest_farm_truth_cases(
        conn, status=status, queue_context_keys=context_keys
    )
    cases.sort(key=_case_sort_key)
    return [_serialize_case(case) for case in cases[:limit]]


def get_farm_truth_case_detail(
    conn,
    case_id: str,
    operating_unit_id: str,
    season_id: str,
) -> Optional[dict[str, Any]]:
    """Return one allowlisted case detail without re-querying source evidence."""
    _require_season_context(conn, operating_unit_id, season_id)
    case = repository.get_farm_truth_case(conn, case_id)
    if case is not None and not _case_is_current(case, operating_unit_id, season_id):
        return None
    return _serialize_case(case) if case is not None else None


def list_farm_truth_inbox_items(
    conn,
    owner_person_id: str,
    limit: int = _QUEUE_LIMIT,
) -> list[dict[str, Any]]:
    """Serialize manager-owned needs-evidence cases for the existing Inbox."""
    _validate_queue_limit(limit)
    cases = repository.list_latest_farm_truth_cases(
        conn,
        status="needs_evidence",
        owner_person_id=owner_person_id,
    )
    cases.sort(key=lambda case: (case.updated_at, case.id), reverse=True)
    items = []
    for case in cases[:limit]:
        summary = _safe_summary(case.evidence_summary)
        items.append({
            "id": case.id,
            "status": case.status,
            "title": "Farm Truth evidence needed",
            "missing_evidence_kind": case.missing_evidence_kind,
            "reason": _INBOX_REASON_LABELS.get(
                case.missing_evidence_kind, "Confirm required evidence"
            ),
            "place": summary["place"],
            "farmer_display_name": summary["people"]["farmer_display_name"],
        })
    return items


def selected_farm_truth_task_ids(
    conn,
    case_id: str,
    operating_unit_id: str,
    season_id: str,
    field_worker_party_id: Optional[str] = None,
) -> tuple[str, ...]:
    """Resolve acceptance evidence IDs entirely inside the private boundary.

    The browser may choose an optional source worker, but it cannot choose the
    task receipts used to justify that assignment.  Those receipts are derived
    from the same typed, valid visit/open-work rules used by candidate refresh.
    """
    season = repository.get_season(conn, season_id)
    if season is None or season.operating_unit_id != operating_unit_id:
        raise ValueError("season does not belong to operating unit")
    case = repository.get_farm_truth_case(conn, case_id)
    if case is None:
        raise ValueError("farm truth review case does not exist")
    if not _case_is_current(case, operating_unit_id, season_id):
        raise ValueError("farm truth review case is stale")
    farmer = conn.execute(
        """SELECT farmer_party_id
           FROM trackwick_registrations
           WHERE id = ? AND source_id = ?""",
        (case.registration_id, case.source_id),
    ).fetchone()
    if farmer is None or farmer["farmer_party_id"] is None:
        raise ValueError("farm truth case no longer has a linked source farmer")
    support = _supporting_tasks(conn).get(
        (case.source_id, str(farmer["farmer_party_id"])), ()
    )
    eligible = [
        task for task in support
        if task["support_kind"] == "open_work"
        or (
            task["support_kind"] == "visit"
            and _date_in_window(task["observed_at"], season.starts_on, season.ends_on)
        )
    ]
    if field_worker_party_id is not None:
        supported = any(
            task["field_worker_party_id"] == field_worker_party_id for task in eligible
        )
        worker = conn.execute(
            """SELECT 1 FROM trackwick_parties
               WHERE id = ? AND source_id = ? AND party_kind = 'field_worker'
                 AND data_quality_status = 'valid'""",
            (field_worker_party_id, case.source_id),
        ).fetchone()
        if not supported or worker is None:
            raise ValueError("field worker is not supported by the selected source evidence")
    return tuple(sorted(str(task["id"]) for task in eligible))


def _candidate_rows(conn) -> list[Mapping[str, Any]]:
    return list(conn.execute(
        """SELECT
               registration.source_id,
               registration.id AS registration_id,
               registration.source_fingerprint AS registration_fingerprint,
               registration.village_name,
               registration.block_name,
               registration.district_name,
               registration.reported_total_area_acres,
               registration.reported_plot_count,
               registration.reported_pb1_area_acres,
               registration.reported_1718_area_acres,
               plot.id AS plot_id,
               plot.source_fingerprint AS plot_fingerprint,
               plot.gata_number,
               plot.reported_area_bigha,
               plot.village_name AS plot_village_name,
               farmer.id AS farmer_party_id,
               farmer.display_name AS farmer_display_name,
               registration_task.id AS registration_task_id,
               registration_task.source_fingerprint AS registration_task_fingerprint,
               registration_task.task_status AS registration_task_status,
               COALESCE(registration_task.provider_completed_at,
                        registration_task.provider_created_at) AS registration_at
           FROM trackwick_registrations AS registration
           JOIN source_registry AS source
             ON source.id = registration.source_id AND source.source_type = 'trackwick'
           JOIN trackwick_registration_plots AS plot
             ON plot.registration_id = registration.id
            AND plot.source_id = registration.source_id
            AND plot.data_quality_status = 'valid'
           JOIN trackwick_parties AS farmer
             ON farmer.id = registration.farmer_party_id
            AND farmer.source_id = registration.source_id
            AND farmer.party_kind = 'farmer'
            AND farmer.data_quality_status = 'valid'
           JOIN trackwick_tasks AS registration_task
             ON registration_task.id = registration.task_id
            AND registration_task.source_id = registration.source_id
            AND registration_task.task_status = 'completed'
            AND registration_task.data_quality_status = 'valid'
           WHERE registration.registration_status = 'completed'
             AND registration.data_quality_status = 'valid'
             AND (COALESCE(plot.reported_area_bigha, 0) > 0
                  OR COALESCE(registration.reported_total_area_acres, 0) > 0)
             AND NOT EXISTS (
                 SELECT 1 FROM trackwick_plot_operating_links AS reviewed_link
                 WHERE reviewed_link.plot_id = plot.id
                   AND reviewed_link.link_status = 'reviewed'
             )
           ORDER BY registration.id, plot.ordinal, plot.id"""
    ).fetchall())


def _trackwick_source_ids(conn) -> list[str]:
    rows = conn.execute(
        """SELECT id FROM source_registry
           WHERE source_type = 'trackwick'
           ORDER BY id"""
    ).fetchall()
    return [str(row["id"]) for row in rows]


def _supporting_tasks(conn) -> dict[tuple[str, str], tuple[Mapping[str, Any], ...]]:
    rows = conn.execute(
        """SELECT
               task.id,
               task.source_id,
               task.farmer_party_id,
               task.field_worker_party_id,
               task.task_status,
               task.source_fingerprint,
               visit.source_fingerprint AS visit_source_fingerprint,
               visit.observed_at,
               visit.transplanted_on,
               visit.crop_stage,
               worker.display_name AS field_worker_display_name,
               CASE
                   WHEN lower(task.task_type) = 'farmer visit'
                        AND task.task_status = 'completed'
                        AND visit.task_id IS NOT NULL
                       THEN 'visit'
                   WHEN task.task_status IN ('pending', 'in_progress')
                       THEN 'open_work'
               END AS support_kind
           FROM trackwick_tasks AS task
           LEFT JOIN trackwick_visits AS visit
             ON visit.task_id = task.id
            AND visit.source_id = task.source_id
            AND visit.data_quality_status = 'valid'
           LEFT JOIN trackwick_parties AS worker
             ON worker.id = task.field_worker_party_id
            AND worker.source_id = task.source_id
            AND worker.party_kind = 'field_worker'
            AND worker.data_quality_status = 'valid'
           WHERE task.farmer_party_id IS NOT NULL
             AND task.data_quality_status = 'valid'
             AND (task.task_status IN ('pending', 'in_progress')
                  OR (lower(task.task_type) = 'farmer visit'
                      AND task.task_status = 'completed'
                      AND visit.task_id IS NOT NULL))
           ORDER BY task.source_id, task.farmer_party_id, task.id"""
    ).fetchall()
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["source_id"]), str(row["farmer_party_id"]))].append(row)
    return {key: tuple(value) for key, value in grouped.items()}


def _candidate_fingerprint(
    candidate: Mapping[str, Any], eligible_tasks: Iterable[Mapping[str, Any]]
) -> str:
    material = {
        "registration_source_fingerprint": candidate["registration_fingerprint"],
        "plot_source_fingerprint": candidate["plot_fingerprint"],
        "eligible_tasks": [dict(task) for task in eligible_tasks],
    }
    canonical = json.dumps(material, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _evidence_summary(
    candidate: Mapping[str, Any],
    visits: list[Mapping[str, Any]],
    open_work: list[Mapping[str, Any]],
) -> dict[str, Any]:
    latest_visit = visits[-1]
    visit_count = len(visits)
    open_count = len(open_work)
    workers = sorted({
        str(task["field_worker_display_name"])
        for task in (*visits, *open_work)
        if task["field_worker_display_name"]
    })
    reason_chips = [
        "Registration",
        "Recent visit" if visit_count == 1 else f"{visit_count} recent visits",
    ]
    if open_count:
        reason_chips.append("Open follow-up" if open_count == 1 else f"{open_count} open follow-ups")
    labels = ["Farmer visit"]
    if open_count:
        labels.append("Open follow-up")
    return {
        "place": {
            "village": candidate["plot_village_name"] or candidate["village_name"],
            "block": candidate["block_name"],
            "district": candidate["district_name"],
        },
        "area": {
            "gata_number": candidate["gata_number"],
            "plot_bigha": candidate["reported_area_bigha"],
            "registration_acres": candidate["reported_total_area_acres"],
            "registration_plot_count": candidate["reported_plot_count"],
        },
        "registration": {
            "completed_at": candidate["registration_at"],
            "pb1_acres": candidate["reported_pb1_area_acres"],
            "variety_1718_acres": candidate["reported_1718_area_acres"],
        },
        "crop_timing": {
            "latest_visit_at": latest_visit["observed_at"],
            "transplanted_on": latest_visit["transplanted_on"],
            "crop_stage": latest_visit["crop_stage"],
        },
        "people": {
            "farmer_display_name": candidate["farmer_display_name"],
            "field_worker_display_names": workers,
        },
        "evidence": {
            "recent_visit_count": visit_count,
            "open_work_count": open_count,
            "safe_task_labels": labels,
            "reason_chips": reason_chips,
        },
    }


def _serialize_case(case: repository.FarmTruthReviewCase) -> dict[str, Any]:
    return {
        "id": case.id,
        "status": case.status,
        **_safe_summary(case.evidence_summary),
    }


def _queue_context_key(source_id: str, operating_unit_id: str, season_id: str) -> str:
    material = json.dumps(
        [source_id, operating_unit_id, season_id],
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _queue_contexts(summary: Mapping[str, Any]) -> dict[str, bool]:
    value = summary.get("_queue_contexts")
    if not isinstance(value, Mapping):
        return {}
    return {
        key: current
        for key, current in value.items()
        if isinstance(key, str)
        and len(key) == 64
        and isinstance(current, bool)
    }


def _case_is_current(
    case: repository.FarmTruthReviewCase,
    operating_unit_id: str,
    season_id: str,
) -> bool:
    context_key = _queue_context_key(case.source_id, operating_unit_id, season_id)
    return _queue_contexts(case.evidence_summary).get(context_key) is True


def _require_season_context(conn, operating_unit_id: str, season_id: str) -> None:
    season = repository.get_season(conn, season_id)
    if season is None or season.operating_unit_id != operating_unit_id:
        raise ValueError("season does not belong to operating unit")


def _safe_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    """Copy only the explicit browser contract from persisted JSON."""
    place = _mapping(summary.get("place"))
    area = _mapping(summary.get("area"))
    registration = _mapping(summary.get("registration"))
    crop_timing = _mapping(summary.get("crop_timing"))
    people = _mapping(summary.get("people"))
    evidence = _mapping(summary.get("evidence"))
    return {
        "place": {
            "village": _text(place.get("village")),
            "block": _text(place.get("block")),
            "district": _text(place.get("district")),
        },
        "area": {
            "gata_number": _text(area.get("gata_number")),
            "plot_bigha": _number(area.get("plot_bigha")),
            "registration_acres": _number(area.get("registration_acres")),
            "registration_plot_count": _integer(area.get("registration_plot_count")),
        },
        "registration": {
            "completed_at": _text(registration.get("completed_at")),
            "pb1_acres": _number(registration.get("pb1_acres")),
            "variety_1718_acres": _number(registration.get("variety_1718_acres")),
        },
        "crop_timing": {
            "latest_visit_at": _text(crop_timing.get("latest_visit_at")),
            "transplanted_on": _text(crop_timing.get("transplanted_on")),
            "crop_stage": _text(crop_timing.get("crop_stage")),
        },
        "people": {
            "farmer_display_name": _text(people.get("farmer_display_name")),
            "field_worker_display_names": _text_list(people.get("field_worker_display_names")),
        },
        "evidence": {
            "recent_visit_count": _integer(evidence.get("recent_visit_count")) or 0,
            "open_work_count": _integer(evidence.get("open_work_count")) or 0,
            "safe_task_labels": _text_list(evidence.get("safe_task_labels")),
            "reason_chips": _text_list(evidence.get("reason_chips")),
        },
    }


def _case_sort_key(case: repository.FarmTruthReviewCase) -> tuple[Any, ...]:
    row = _safe_summary(case.evidence_summary)
    evidence = row["evidence"]
    return (
        -int(evidence["open_work_count"]),
        -_timestamp_value(row["crop_timing"]["latest_visit_at"]),
        -_timestamp_value(row["registration"]["completed_at"]),
        case.registration_id,
        case.plot_id,
        case.id,
    )


def _date_in_window(value: Any, starts_on: str, ends_on: str) -> bool:
    observed = _parse_timestamp(value)
    if observed is None:
        return False
    return date.fromisoformat(starts_on) <= observed.date() <= date.fromisoformat(ends_on)


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _timestamp_value(value: Any) -> float:
    parsed = _parse_timestamp(value)
    return parsed.timestamp() if parsed is not None else 0.0


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> Optional[str]:
    return value[:320] if isinstance(value, str) else None


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item[:320] for item in value if isinstance(item, str)][:50]


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _integer(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _validate_queue_limit(limit: int) -> None:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= _QUEUE_LIMIT:
        raise ValueError("limit must be between 1 and 50")
