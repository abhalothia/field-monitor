"""Deterministic, private operating snapshots for fast manager read models.

Snapshots are deliberately factual.  They cache counts and timestamps from the
typed source lane; presentation tags are derived from those facts at read time
so an "active this week" label can age honestly without a database rewrite.
No raw form values, contacts, coordinates, provider fields, farm boundaries,
or diagnostic claims are copied into this layer.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Mapping, Optional


ENRICHMENT_VERSION = "operating-v1"
_OPEN_TASK_STATUSES = {"pending", "in_progress"}
_ENTITY_KINDS = {"reported_farm", "farmer", "field_worker"}


def refresh_source_snapshots(
    conn,
    source_id: str,
    *,
    source_run_id: Optional[str] = None,
    refreshed_at: Optional[str] = None,
    commit: bool = True,
) -> int:
    """Upsert the current factual snapshot for every supported source entity.

    This intentionally reads the existing typed records rather than a provider
    payload.  It is safe to run after every source import and idempotent for a
    historical backfill.  Removed source rows remain private but are not
    returned by board joins, so this function never needs DELETE permission.
    """
    if not snapshot_table_available(conn) or not _typed_graph_available(conn):
        return 0

    snapshots = _build_snapshots(conn, source_id)
    if not snapshots:
        return 0
    now = refreshed_at or _now()
    rows = [
        (
            source_id,
            source_run_id,
            snapshot["entity_kind"],
            snapshot["entity_id"],
            snapshot["farm_count"],
            snapshot["farmer_count"],
            snapshot["open_task_count"],
            snapshot["completed_work_count"],
            snapshot["visit_count"],
            snapshot["disease_report_count"],
            snapshot["pest_report_count"],
            snapshot["location_evidence_count"],
            snapshot["photo_reference_count"],
            snapshot["attendance_present_days"],
            snapshot["reported_area_acres"],
            snapshot["latest_activity_at"],
            ENRICHMENT_VERSION,
            now,
        )
        for snapshot in snapshots
    ]
    conn.executemany(
        """INSERT INTO entity_operating_snapshots (
               source_id, source_run_id, entity_kind, entity_id,
               farm_count, farmer_count, open_task_count, completed_work_count,
               visit_count, disease_report_count, pest_report_count,
               location_evidence_count, photo_reference_count,
               attendance_present_days, reported_area_acres,
               latest_activity_at, enrichment_version, refreshed_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (source_id, entity_kind, entity_id) DO UPDATE SET
               source_run_id = excluded.source_run_id,
               farm_count = excluded.farm_count,
               farmer_count = excluded.farmer_count,
               open_task_count = excluded.open_task_count,
               completed_work_count = excluded.completed_work_count,
               visit_count = excluded.visit_count,
               disease_report_count = excluded.disease_report_count,
               pest_report_count = excluded.pest_report_count,
               location_evidence_count = excluded.location_evidence_count,
               photo_reference_count = excluded.photo_reference_count,
               attendance_present_days = excluded.attendance_present_days,
               reported_area_acres = excluded.reported_area_acres,
               latest_activity_at = excluded.latest_activity_at,
               enrichment_version = excluded.enrichment_version,
               refreshed_at = excluded.refreshed_at""",
        rows,
    )
    if commit:
        conn.commit()
    # psycopg's executemany rowcount is intentionally driver-dependent.  The
    # input is one upsert per entity, which is the stable result our callers
    # need for an import receipt or one-time backfill.
    return len(rows)


def snapshot_table_available(conn) -> bool:
    """Support deployed code during the short migration rollout window."""
    if getattr(conn, "dialect", "sqlite") == "postgres":
        row = conn.execute(
            "SELECT to_regclass(?) AS relation_name", ("agro_entity_operating_snapshots",)
        ).fetchone()
        return row is not None and row["relation_name"] is not None
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        ("entity_operating_snapshots",),
    ).fetchone()
    return row is not None


def snapshot_index_for_source(conn, source_id: str) -> dict[tuple[str, str], dict[str, Any]]:
    """Read the current private snapshots as browser-safe operating context."""
    if not snapshot_table_available(conn):
        return {}
    rows = conn.execute(
        """SELECT entity_kind, entity_id, farm_count, farmer_count,
                  open_task_count, completed_work_count, visit_count,
                  disease_report_count, pest_report_count,
                  location_evidence_count, photo_reference_count,
                  attendance_present_days, reported_area_acres,
                  latest_activity_at, refreshed_at
           FROM entity_operating_snapshots
           WHERE source_id = ? AND enrichment_version = ?""",
        (source_id, ENRICHMENT_VERSION),
    ).fetchall()
    return {
        (str(row["entity_kind"]), str(row["entity_id"])): public_snapshot(row)
        for row in rows
    }


def public_snapshot(snapshot: Mapping[str, Any], *, now: Optional[datetime] = None) -> dict[str, Any]:
    """Return the tiny safe enrichment shape shared by cards, maps, and profiles."""
    # sqlite3.Row deliberately exposes keys but not Mapping.get; normalize the
    # two database row facades before deriving browser-safe facts.
    snapshot = dict(snapshot)
    factual = {
        "farm_count": _integer(snapshot.get("farm_count")),
        "farmer_count": _integer(snapshot.get("farmer_count")),
        "open_task_count": _integer(snapshot.get("open_task_count")),
        "completed_work_count": _integer(snapshot.get("completed_work_count")),
        "visit_count": _integer(snapshot.get("visit_count")),
        "disease_report_count": _integer(snapshot.get("disease_report_count")),
        "pest_report_count": _integer(snapshot.get("pest_report_count")),
        "location_evidence_count": _integer(snapshot.get("location_evidence_count")),
        "photo_reference_count": _integer(snapshot.get("photo_reference_count")),
        "attendance_present_days": _integer(snapshot.get("attendance_present_days")),
        "reported_area_acres": _number(snapshot.get("reported_area_acres")),
        "latest_activity_at": snapshot.get("latest_activity_at"),
        "refreshed_at": snapshot.get("refreshed_at"),
    }
    return {
        "metrics": factual,
        "tags": tags_for_snapshot(snapshot, now=now),
    }


def tags_for_snapshot(snapshot: Mapping[str, Any], *, now: Optional[datetime] = None) -> list[dict[str, str]]:
    """Small, explainable UI labels; never an inference or diagnosis."""
    entity_kind = str(snapshot.get("entity_kind") or "")
    if entity_kind not in _ENTITY_KINDS:
        return []
    tags: list[dict[str, str]] = []
    if _integer(snapshot.get("open_task_count")):
        tags.append(_tag("needs_attention", "Needs attention", "attention"))
    if _integer(snapshot.get("disease_report_count")):
        tags.append(_tag("disease_reported", "Disease reported", "attention"))
    if _integer(snapshot.get("pest_report_count")):
        tags.append(_tag("pest_reported", "Pest reported", "attention"))

    activity = _timestamp(snapshot.get("latest_activity_at"))
    reference = now or datetime.now(timezone.utc)
    if activity is not None:
        age_days = (reference - activity).total_seconds() / 86_400
        if age_days <= 7:
            tags.append(_tag("active_this_week", "Active this week", "current"))
        elif age_days > 30:
            tags.append(_tag("earlier_activity", "Earlier activity", "neutral"))

    if entity_kind == "reported_farm" and _number(snapshot.get("reported_area_acres")) is not None:
        tags.append(_tag("area_recorded", "Area recorded", "neutral"))
    if entity_kind == "farmer":
        farm_count = _integer(snapshot.get("farm_count"))
        if farm_count > 1:
            tags.append(_tag("multiple_farms", "Multiple farms", "neutral"))
        elif farm_count == 1:
            tags.append(_tag("farm_recorded", "Farm recorded", "neutral"))
    if entity_kind == "field_worker" and _integer(snapshot.get("farmer_count")):
        tags.append(_tag("farmers_assigned", "Farmers assigned", "neutral"))
    if _integer(snapshot.get("location_evidence_count")):
        tags.append(_tag("location_available", "Location available", "neutral"))
    if _integer(snapshot.get("photo_reference_count")):
        tags.append(_tag("photo_evidence", "Photo evidence", "neutral"))
    if _integer(snapshot.get("completed_work_count")):
        tags.append(_tag("work_completed", "Work completed", "neutral"))
    if entity_kind == "field_worker" and _integer(snapshot.get("attendance_present_days")):
        tags.append(_tag("attendance_recorded", "Attendance recorded", "neutral"))
    return tags


def _build_snapshots(conn, source_id: str) -> list[dict[str, Any]]:
    parties = conn.execute(
        """SELECT id, party_kind FROM trackwick_parties
           WHERE source_id = ? AND data_quality_status = 'valid'""",
        (source_id,),
    ).fetchall()
    tasks = conn.execute(
        """SELECT id, farmer_party_id, field_worker_party_id, task_status,
                  provider_created_at, provider_started_at, provider_completed_at
           FROM trackwick_tasks
           WHERE source_id = ? AND data_quality_status = 'valid'""",
        (source_id,),
    ).fetchall()
    registrations = conn.execute(
        """SELECT id, task_id, farmer_party_id, reported_total_area_acres
           FROM trackwick_registrations
           WHERE source_id = ? AND data_quality_status = 'valid'""",
        (source_id,),
    ).fetchall()
    visits = conn.execute(
        """SELECT task_id, observed_at FROM trackwick_visits
           WHERE source_id = ? AND data_quality_status = 'valid'""",
        (source_id,),
    ).fetchall()
    findings = conn.execute(
        """SELECT visit_task_id, finding_kind, observed_at
           FROM trackwick_visit_findings
           WHERE source_id = ? AND data_quality_status = 'valid'""",
        (source_id,),
    ).fetchall()
    locations = conn.execute(
        """SELECT id, party_id, task_id, registration_id, observed_at
           FROM trackwick_location_observations
           WHERE source_id = ? AND data_quality_status = 'valid'""",
        (source_id,),
    ).fetchall()
    media = conn.execute(
        """SELECT task_id FROM trackwick_media_references
           WHERE source_id = ? AND data_quality_status = 'valid'""",
        (source_id,),
    ).fetchall()
    worker_days = conn.execute(
        """SELECT field_worker_party_id, observed_on, attendance_status
           FROM trackwick_worker_days
           WHERE source_id = ? AND data_quality_status = 'valid'""",
        (source_id,),
    ).fetchall()

    snapshots = {
        ("farmer", str(row["id"])): _empty_snapshot("farmer", str(row["id"]))
        for row in parties if row["party_kind"] == "farmer"
    }
    snapshots.update({
        ("field_worker", str(row["id"])): _empty_snapshot("field_worker", str(row["id"]))
        for row in parties if row["party_kind"] == "field_worker"
    })
    task_by_id = {str(row["id"]): row for row in tasks}
    registration_by_task = {
        str(row["task_id"]): row for row in registrations if row["task_id"]
    }
    party_kind_by_id = {str(row["id"]): str(row["party_kind"]) for row in parties}

    for registration in registrations:
        registration_id = str(registration["id"])
        farm = _empty_snapshot("reported_farm", registration_id)
        farm["reported_area_acres"] = _number(registration["reported_total_area_acres"])
        registration_task = task_by_id.get(str(registration["task_id"])) if registration["task_id"] else None
        if registration_task is not None:
            _add_task(farm, registration_task)
        snapshots[("reported_farm", registration_id)] = farm
        farmer_id = registration["farmer_party_id"]
        if farmer_id and ("farmer", str(farmer_id)) in snapshots:
            farmer = snapshots[("farmer", str(farmer_id))]
            farmer["farm_count"] += 1
            farmer["reported_area_acres"] = _sum_numbers(
                farmer["reported_area_acres"], registration["reported_total_area_acres"],
            )

    for task in tasks:
        farmer_id = task["farmer_party_id"]
        worker_id = task["field_worker_party_id"]
        if farmer_id and ("farmer", str(farmer_id)) in snapshots:
            _add_task(snapshots[("farmer", str(farmer_id))], task)
        if worker_id and ("field_worker", str(worker_id)) in snapshots:
            worker = snapshots[("field_worker", str(worker_id))]
            _add_task(worker, task)
            if farmer_id:
                worker["_farmer_ids"].add(str(farmer_id))

    for visit in visits:
        task = task_by_id.get(str(visit["task_id"]))
        _add_task_event(snapshots, task, "visit_count", visit["observed_at"])
        _add_registration_task_event(
            snapshots, registration_by_task, task, "visit_count", visit["observed_at"],
        )

    for finding in findings:
        task = task_by_id.get(str(finding["visit_task_id"]))
        metric = "disease_report_count" if finding["finding_kind"] == "disease" else "pest_report_count"
        _add_task_event(snapshots, task, metric, finding["observed_at"])
        _add_registration_task_event(
            snapshots, registration_by_task, task, metric, finding["observed_at"],
        )

    location_targets: dict[tuple[str, str], set[str]] = defaultdict(set)
    for location in locations:
        target_keys: set[tuple[str, str]] = set()
        registration_id = location["registration_id"]
        if registration_id and ("reported_farm", str(registration_id)) in snapshots:
            target_keys.add(("reported_farm", str(registration_id)))
        party_id = location["party_id"]
        if party_id:
            party_kind = party_kind_by_id.get(str(party_id))
            if party_kind and (party_kind, str(party_id)) in snapshots:
                target_keys.add((party_kind, str(party_id)))
        task = task_by_id.get(str(location["task_id"])) if location["task_id"] else None
        if task is not None:
            for entity_kind, party_key in (("farmer", "farmer_party_id"), ("field_worker", "field_worker_party_id")):
                party_id = task[party_key]
                if party_id and (entity_kind, str(party_id)) in snapshots:
                    target_keys.add((entity_kind, str(party_id)))
            registration = registration_by_task.get(str(task["id"]))
            if registration is not None:
                target_keys.add(("reported_farm", str(registration["id"])))
        location_id = str(location["id"])
        for key in target_keys:
            if location_id in location_targets[key]:
                continue
            location_targets[key].add(location_id)
            target = snapshots[key]
            target["location_evidence_count"] += 1
            _observe(target, location["observed_at"])

    for reference in media:
        task = task_by_id.get(str(reference["task_id"]))
        _add_task_event(snapshots, task, "photo_reference_count", None)
        if task is not None:
            registration = registration_by_task.get(str(task["id"]))
            if registration is not None:
                farm = snapshots.get(("reported_farm", str(registration["id"])))
                if farm is not None:
                    farm["photo_reference_count"] += 1

    for day in worker_days:
        worker = snapshots.get(("field_worker", str(day["field_worker_party_id"])))
        if worker is None:
            continue
        if day["attendance_status"] == "present":
            worker["attendance_present_days"] += 1
        _observe(worker, day["observed_on"])

    for snapshot in snapshots.values():
        snapshot["farmer_count"] = len(snapshot.pop("_farmer_ids", set()))
    return list(snapshots.values())


def _typed_graph_available(conn) -> bool:
    required = (
        "trackwick_parties", "trackwick_tasks", "trackwick_registrations",
        "trackwick_visits", "trackwick_visit_findings", "trackwick_location_observations",
        "trackwick_media_references", "trackwick_worker_days",
    )
    if getattr(conn, "dialect", "sqlite") == "postgres":
        for table in required:
            row = conn.execute("SELECT to_regclass(?) AS relation_name", ("agro_" + table,)).fetchone()
            if row is None or row["relation_name"] is None:
                return False
        return True
    for table in required:
        if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        ).fetchone() is None:
            return False
    return True


def _empty_snapshot(entity_kind: str, entity_id: str) -> dict[str, Any]:
    return {
        "entity_kind": entity_kind,
        "entity_id": entity_id,
        "farm_count": 0,
        "farmer_count": 0,
        "open_task_count": 0,
        "completed_work_count": 0,
        "visit_count": 0,
        "disease_report_count": 0,
        "pest_report_count": 0,
        "location_evidence_count": 0,
        "photo_reference_count": 0,
        "attendance_present_days": 0,
        "reported_area_acres": None,
        "latest_activity_at": None,
        "_farmer_ids": set(),
    }


def _add_task(snapshot: dict[str, Any], task: Mapping[str, Any]) -> None:
    if task["task_status"] in _OPEN_TASK_STATUSES:
        snapshot["open_task_count"] += 1
    if task["task_status"] == "completed":
        snapshot["completed_work_count"] += 1
    _observe(
        snapshot,
        task["provider_completed_at"] or task["provider_started_at"] or task["provider_created_at"],
    )


def _add_task_event(
    snapshots: Mapping[tuple[str, str], dict[str, Any]],
    task: Optional[Mapping[str, Any]],
    metric: str,
    observed_at: Optional[str],
) -> None:
    if task is None:
        return
    for entity_kind, party_key in (("farmer", "farmer_party_id"), ("field_worker", "field_worker_party_id")):
        party_id = task[party_key]
        if party_id and (entity_kind, str(party_id)) in snapshots:
            snapshot = snapshots[(entity_kind, str(party_id))]
            snapshot[metric] += 1
            _observe(snapshot, observed_at)


def _add_registration_task_event(
    snapshots: Mapping[tuple[str, str], dict[str, Any]],
    registrations_by_task: Mapping[str, Mapping[str, Any]],
    task: Optional[Mapping[str, Any]],
    metric: str,
    observed_at: Optional[str],
) -> None:
    """Attribute an event to a Farm only when its registration task matches."""
    if task is None:
        return
    registration = registrations_by_task.get(str(task["id"]))
    if registration is None:
        return
    snapshot = snapshots.get(("reported_farm", str(registration["id"])))
    if snapshot is None:
        return
    snapshot[metric] += 1
    _observe(snapshot, observed_at)


def _observe(snapshot: dict[str, Any], value: Any) -> None:
    candidate = _timestamp(value)
    current = _timestamp(snapshot.get("latest_activity_at"))
    if candidate is not None and (current is None or candidate > current):
        snapshot["latest_activity_at"] = candidate.isoformat()


def _sum_numbers(left: Any, right: Any) -> Optional[float]:
    values = [_number(value) for value in (left, right)]
    usable = [value for value in values if value is not None]
    return None if not usable else sum(usable)


def _tag(key: str, label: str, tone: str) -> dict[str, str]:
    return {"key": key, "label": label, "tone": tone}


def _integer(value: Any) -> int:
    return int(value or 0)


def _number(value: Any) -> Optional[float]:
    return None if value is None else float(value)


def _timestamp(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed = datetime.fromisoformat(str(value) + "T00:00:00+00:00")
            except ValueError:
                return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
