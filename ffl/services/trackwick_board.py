"""Small manager-only operating board derived from private TrackWick evidence.

This is intentionally not a canonical farm model.  A TrackWick registration is
a reported farm candidate, and a TrackWick coordinate is a source point—not a
boundary or a verified Fortune field.  The service returns only the minimum
identity and work context that a manager needs.  Contacts, remote media URLs,
provider IDs, raw forms, and addresses never leave the private source lane.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Iterable, Mapping, Optional

from ffl.persistence import repository
from ffl.services.trackwick_ingest import SOURCE_KEY


_OPEN_TASK_STATUSES = {"pending", "in_progress"}
_MAP_POINT_LIMIT = 4_000


def manager_board_for_source(conn, *, source_key: str = SOURCE_KEY) -> dict[str, Any]:
    """Return the private-source operating primitives for an authorised manager.

    There is no fallback to fabricated records.  Before the source sync exists,
    callers get an empty board with an explicit source state.
    """
    source = repository.get_source_registry_by_key(conn, source_key)
    if source is None:
        return _empty_board("not_configured")

    latest_run = _latest_source_run(conn, source.id)
    source_state = latest_run["status"] if latest_run is not None else "registered"
    last_synced_at = latest_run["fetched_at"] if latest_run is not None else None
    parties = _rows(
        conn,
        """SELECT id, party_kind, display_name, crm_status, provider_tag, last_seen_at
           FROM trackwick_parties
           WHERE source_id = ? AND data_quality_status = 'valid'""",
        source.id,
    )
    tasks = _rows(
        conn,
        """SELECT id, farmer_party_id, field_worker_party_id, task_type, task_status,
                  provider_created_at, provider_started_at, provider_completed_at, provider_follow_up_at
           FROM trackwick_tasks
           WHERE source_id = ? AND data_quality_status = 'valid'""",
        source.id,
    )
    registrations = _rows(
        conn,
        """SELECT id, task_id, farmer_party_id, registration_status, village_name, block_name,
                  district_name, reported_total_area_acres, reported_plot_count,
                  reported_pb1_area_acres, reported_1718_area_acres
           FROM trackwick_registrations
           WHERE source_id = ? AND data_quality_status = 'valid'""",
        source.id,
    )
    plots = _rows(
        conn,
        """SELECT registration_id
           FROM trackwick_registration_plots
           WHERE source_id = ? AND data_quality_status = 'valid'""",
        source.id,
    )
    media = _rows(
        conn,
        """SELECT task_id, media_kind
           FROM trackwick_media_references
           WHERE source_id = ? AND data_quality_status = 'valid'""",
        source.id,
    )
    locations = _rows(
        conn,
        """SELECT party_id, task_id, registration_id, media_reference_id, location_kind,
                  location_confidence, latitude, longitude, observed_at
           FROM trackwick_location_observations
           WHERE source_id = ? AND data_quality_status = 'valid'
           ORDER BY observed_at DESC, id DESC""",
        source.id,
    )
    worker_days = _rows(
        conn,
        """SELECT field_worker_party_id, observed_on, attendance_status
           FROM trackwick_worker_days
           WHERE source_id = ? AND data_quality_status = 'valid'
           ORDER BY observed_on DESC, id DESC""",
        source.id,
    )

    party_by_id = {row["id"]: row for row in parties}
    farmers = [row for row in parties if row["party_kind"] == "farmer"]
    workers = [row for row in parties if row["party_kind"] == "field_worker"]
    tasks_by_farmer = _group_by(tasks, "farmer_party_id")
    tasks_by_worker = _group_by(tasks, "field_worker_party_id")
    registrations_by_farmer = _group_by(registrations, "farmer_party_id")
    plot_counts = Counter(row["registration_id"] for row in plots if row["registration_id"])
    media_counts = _media_counts(media)
    latest_task_location = _latest_locations(locations, "task_id")
    latest_registration_location = _latest_locations(locations, "registration_id")
    latest_party_location = _latest_locations(locations, "party_id")
    latest_worker_day = _latest_worker_days(worker_days)

    farm_rows = _farm_rows(
        registrations,
        party_by_id,
        tasks_by_farmer,
        tasks,
        plot_counts,
        media_counts,
        latest_registration_location,
        latest_task_location,
        latest_party_location,
    )
    farmer_rows = _farmer_rows(
        farmers,
        tasks_by_farmer,
        registrations_by_farmer,
        registrations,
        media_counts,
        latest_party_location,
    )
    worker_rows = _worker_rows(workers, tasks_by_worker, latest_worker_day)
    inbox_rows = _inbox_rows(tasks, party_by_id)
    map_points, map_truncated = _map_points(
        locations,
        registrations,
        party_by_id,
        tasks,
    )
    counts = {
        "farmers": len(farmers),
        "farm_candidates": len(registrations),
        "field_workers": len(workers),
        "open_work": sum(row["task_status"] in _OPEN_TASK_STATUSES for row in tasks),
        "source_points": len(locations),
        "crop_photo_references": sum(kind_counts["crop_photo"] for kind_counts in media_counts.values()),
        "plot_photo_references": sum(kind_counts["plot_photo"] for kind_counts in media_counts.values()),
    }
    return {
        "source": {"state": source_state, "last_synced_at": last_synced_at},
        "counts": counts,
        "farms": farm_rows,
        "farmers": farmer_rows,
        "field_workers": worker_rows,
        "inbox": inbox_rows,
        "map": {
            "points": map_points,
            "total_source_points": len(locations),
            "truncated": map_truncated,
            "point_meaning": "Source evidence points, not farm boundaries or verified fields.",
        },
        "limitations": [
            "Reported farm candidates require Fortune review before they become canonical farms.",
            "TrackWick points are source evidence, not field boundaries.",
            "Photo counts are references only; image files and links remain private.",
        ],
    }


def _empty_board(state: str) -> dict[str, Any]:
    return {
        "source": {"state": state, "last_synced_at": None},
        "counts": {
            "farmers": 0,
            "farm_candidates": 0,
            "field_workers": 0,
            "open_work": 0,
            "source_points": 0,
            "crop_photo_references": 0,
            "plot_photo_references": 0,
        },
        "farms": [],
        "farmers": [],
        "field_workers": [],
        "inbox": [],
        "map": {
            "points": [],
            "total_source_points": 0,
            "truncated": False,
            "point_meaning": "Source evidence points, not farm boundaries or verified fields.",
        },
        "limitations": [
            "Reported farm candidates require Fortune review before they become canonical farms.",
            "TrackWick points are source evidence, not field boundaries.",
            "Photo counts are references only; image files and links remain private.",
        ],
    }


def _latest_source_run(conn, source_id: str) -> Optional[Mapping[str, Any]]:
    row = conn.execute(
        """SELECT status, fetched_at FROM source_runs
           WHERE source_id = ? ORDER BY created_at DESC LIMIT 1""",
        (source_id,),
    ).fetchone()
    return row


def _rows(conn, statement: str, source_id: str) -> list[Mapping[str, Any]]:
    return list(conn.execute(statement, (source_id,)).fetchall())


def _group_by(rows: Iterable[Mapping[str, Any]], key: str) -> dict[str, list[Mapping[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        value = row[key]
        if value:
            grouped[str(value)].append(row)
    return grouped


def _media_counts(rows: Iterable[Mapping[str, Any]]) -> dict[str, Counter[str]]:
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        task_id, media_kind = row["task_id"], row["media_kind"]
        if task_id and media_kind:
            counts[str(task_id)][str(media_kind)] += 1
    return counts


def _latest_locations(rows: Iterable[Mapping[str, Any]], key: str) -> dict[str, Mapping[str, Any]]:
    latest: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        value = row[key]
        if value and str(value) not in latest:
            latest[str(value)] = row
    return latest


def _latest_worker_days(rows: Iterable[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    latest: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        worker_id = row["field_worker_party_id"]
        if worker_id and str(worker_id) not in latest:
            latest[str(worker_id)] = row
    return latest


def _farm_rows(
    registrations: Iterable[Mapping[str, Any]],
    parties: Mapping[str, Mapping[str, Any]],
    tasks_by_farmer: Mapping[str, list[Mapping[str, Any]]],
    tasks: Iterable[Mapping[str, Any]],
    plot_counts: Mapping[str, int],
    media_counts: Mapping[str, Counter[str]],
    locations_by_registration: Mapping[str, Mapping[str, Any]],
    locations_by_task: Mapping[str, Mapping[str, Any]],
    locations_by_party: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for registration in registrations:
        farmer_id = registration["farmer_party_id"]
        farmer = parties.get(str(farmer_id)) if farmer_id else None
        farmer_tasks = tasks_by_farmer.get(str(farmer_id), []) if farmer_id else []
        task_ids = {task["id"] for task in farmer_tasks}
        registration_task_id = registration["task_id"]
        linked_task_ids = task_ids | ({registration_task_id} if registration_task_id else set())
        count_media = Counter()
        for task_id in linked_task_ids:
            count_media.update(media_counts.get(str(task_id), Counter()))
        location = (
            locations_by_registration.get(str(registration["id"]))
            or locations_by_task.get(str(registration_task_id))
            or (locations_by_party.get(str(farmer_id)) if farmer_id else None)
        )
        rows.append({
            "id": registration["id"],
            "farmer_name": farmer["display_name"] if farmer is not None else "Unlinked grower",
            "place": _place(registration),
            "registration_status": registration["registration_status"],
            "reported_area_acres": _number(registration["reported_total_area_acres"]),
            "reported_plot_count": _integer(registration["reported_plot_count"]) or plot_counts.get(str(registration["id"]), 0),
            "pb1_area_acres": _number(registration["reported_pb1_area_acres"]),
            "var1718_area_acres": _number(registration["reported_1718_area_acres"]),
            "open_work": sum(task["task_status"] in _OPEN_TASK_STATUSES for task in farmer_tasks),
            "latest_activity_at": _latest_task_at(farmer_tasks),
            "location": _location(location),
            "plot_photo_references": count_media["plot_photo"],
            "crop_photo_references": count_media["crop_photo"],
            "record_kind": "reported_farm_candidate",
        })
    return sorted(rows, key=lambda row: (row["open_work"] == 0, row["place"], row["farmer_name"]))


def _farmer_rows(
    farmers: Iterable[Mapping[str, Any]],
    tasks_by_farmer: Mapping[str, list[Mapping[str, Any]]],
    registrations_by_farmer: Mapping[str, list[Mapping[str, Any]]],
    registrations: Iterable[Mapping[str, Any]],
    media_counts: Mapping[str, Counter[str]],
    locations_by_party: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    registration_by_task = {row["task_id"]: row for row in registrations}
    rows: list[dict[str, Any]] = []
    for farmer in farmers:
        farmer_id = str(farmer["id"])
        farmer_tasks = tasks_by_farmer.get(farmer_id, [])
        farmer_registrations = registrations_by_farmer.get(farmer_id, [])
        counts = Counter()
        for task in farmer_tasks:
            counts.update(media_counts.get(str(task["id"]), Counter()))
        reported_area = sum(
            value for value in (_number(registration["reported_total_area_acres"]) for registration in farmer_registrations)
            if value is not None
        )
        rows.append({
            "id": farmer_id,
            "name": farmer["display_name"],
            "crm_status": farmer["crm_status"],
            "tag": farmer["provider_tag"],
            "farm_candidates": len(farmer_registrations),
            "reported_area_acres": reported_area or None,
            "open_work": sum(task["task_status"] in _OPEN_TASK_STATUSES for task in farmer_tasks),
            "latest_activity_at": _latest_task_at(farmer_tasks) or farmer["last_seen_at"],
            "crop_photo_references": counts["crop_photo"],
            "location": _location(locations_by_party.get(farmer_id)),
            "record_kind": "source_farmer",
        })
    return sorted(rows, key=lambda row: (row["open_work"] == 0, row["name"]))


def _worker_rows(
    workers: Iterable[Mapping[str, Any]],
    tasks_by_worker: Mapping[str, list[Mapping[str, Any]]],
    latest_worker_day: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for worker in workers:
        worker_id = str(worker["id"])
        tasks = tasks_by_worker.get(worker_id, [])
        day = latest_worker_day.get(worker_id)
        rows.append({
            "id": worker_id,
            "name": worker["display_name"],
            "open_work": sum(task["task_status"] in _OPEN_TASK_STATUSES for task in tasks),
            "completed_work": sum(task["task_status"] == "completed" for task in tasks),
            "latest_activity_at": _latest_task_at(tasks) or worker["last_seen_at"],
            "latest_attendance": (
                None if day is None else {
                    "observed_on": day["observed_on"],
                    "status": day["attendance_status"],
                }
            ),
            "record_kind": "source_field_worker",
        })
    return sorted(rows, key=lambda row: (row["open_work"] == 0, row["name"]))


def _inbox_rows(tasks: Iterable[Mapping[str, Any]], parties: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    open_tasks = [task for task in tasks if task["task_status"] in _OPEN_TASK_STATUSES]
    rows = []
    for task in open_tasks:
        farmer = parties.get(str(task["farmer_party_id"])) if task["farmer_party_id"] else None
        worker = parties.get(str(task["field_worker_party_id"])) if task["field_worker_party_id"] else None
        rows.append({
            "id": task["id"],
            "task_type": task["task_type"],
            "status": task["task_status"],
            "farmer_name": farmer["display_name"] if farmer is not None else None,
            "field_worker_name": worker["display_name"] if worker is not None else None,
            "follow_up_at": task["provider_follow_up_at"],
            "opened_at": task["provider_created_at"] or task["provider_started_at"],
            "record_kind": "source_work_item",
        })
    return sorted(rows, key=lambda row: (row["follow_up_at"] is None, row["follow_up_at"] or row["opened_at"] or "", row["task_type"]))


def _map_points(
    locations: Iterable[Mapping[str, Any]],
    registrations: Iterable[Mapping[str, Any]],
    parties: Mapping[str, Mapping[str, Any]],
    tasks: Iterable[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], bool]:
    registration_by_id = {str(row["id"]): row for row in registrations}
    task_by_id = {str(row["id"]): row for row in tasks}
    points: list[dict[str, Any]] = []
    seen: set[str] = set()
    total = 0
    for location in locations:
        total += 1
        key = _location_entity_key(location)
        if key in seen:
            continue
        seen.add(key)
        if len(points) >= _MAP_POINT_LIMIT:
            continue
        registration = registration_by_id.get(str(location["registration_id"])) if location["registration_id"] else None
        task = task_by_id.get(str(location["task_id"])) if location["task_id"] else None
        farmer = None
        if registration is not None and registration["farmer_party_id"]:
            farmer = parties.get(str(registration["farmer_party_id"]))
        elif task is not None and task["farmer_party_id"]:
            farmer = parties.get(str(task["farmer_party_id"]))
        elif location["party_id"]:
            farmer = parties.get(str(location["party_id"]))
        points.append({
            "id": key,
            "latitude": float(location["latitude"]),
            "longitude": float(location["longitude"]),
            "kind": location["location_kind"],
            "confidence": location["location_confidence"],
            "observed_at": location["observed_at"],
            "label": _point_label(registration, task, farmer),
            "record_kind": "source_point",
            "is_boundary": False,
        })
    return points, len(seen) > _MAP_POINT_LIMIT


def _location_entity_key(row: Mapping[str, Any]) -> str:
    for field in ("registration_id", "task_id", "party_id", "media_reference_id"):
        if row[field]:
            return field + ":" + str(row[field])
    # Database-level constraints guarantee this is unreachable.  Keep the
    # fallback stable rather than ever leaking a provider location key.
    return "unlinked:" + str(row["observed_at"]) + ":" + str(row["latitude"]) + ":" + str(row["longitude"])


def _point_label(
    registration: Optional[Mapping[str, Any]],
    task: Optional[Mapping[str, Any]],
    farmer: Optional[Mapping[str, Any]],
) -> str:
    if registration is not None:
        return "Reported farm candidate · " + _place(registration)
    if task is not None:
        return "Field observation · " + task["task_type"]
    if farmer is not None:
        return "Grower source point · " + farmer["display_name"]
    return "TrackWick source point"


def _location(row: Optional[Mapping[str, Any]]) -> Optional[dict[str, Any]]:
    if row is None:
        return None
    return {
        "latitude": float(row["latitude"]),
        "longitude": float(row["longitude"]),
        "kind": row["location_kind"],
        "confidence": row["location_confidence"],
        "observed_at": row["observed_at"],
    }


def _place(registration: Mapping[str, Any]) -> str:
    pieces = [registration[field] for field in ("village_name", "block_name", "district_name") if registration[field]]
    return " · ".join(str(piece) for piece in pieces) or "Location not reported"


def _latest_task_at(tasks: Iterable[Mapping[str, Any]]) -> Optional[str]:
    values = []
    for task in tasks:
        values.extend(value for value in (
            task["provider_completed_at"],
            task["provider_started_at"],
            task["provider_created_at"],
        ) if value)
    return max(values) if values else None


def _number(value: Any) -> Optional[float]:
    return None if value is None else float(value)


def _integer(value: Any) -> Optional[int]:
    return None if value is None else int(value)
