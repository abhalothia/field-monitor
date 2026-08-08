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
import re
from typing import Any, Mapping, Optional


ENRICHMENT_VERSION = "operating-v3"
_OPEN_TASK_STATUSES = {"pending", "in_progress"}
_ENTITY_KINDS = {"reported_farm", "farmer", "field_worker"}
_CROP_PROFILES = {"pb1", "1718", "mixed", "not_recorded"}
_ACTIVITY_KINDS = {"registration", "visit", "issue", "work", "location", "photo", "attendance", "unknown"}
_ACTIVITY_PRIORITY = {
    "unknown": 0,
    "work": 1,
    "registration": 2,
    "location": 3,
    "photo": 4,
    "attendance": 5,
    "visit": 6,
    "issue": 7,
}


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

    classification_ready = classification_schema_available(conn)
    snapshots = _build_snapshots(conn, source_id)
    if not snapshots:
        return 0
    now = refreshed_at or _now()
    if classification_ready:
        _upsert_place_catalog(conn, source_id, snapshots, now)
        _upsert_task_taxonomy(conn, source_id, now)
        if place_summary_schema_available(conn):
            _upsert_place_summaries(conn, source_id, snapshots, now)
        rows = [_classified_snapshot_row(snapshot, source_id, source_run_id, now) for snapshot in snapshots]
        conn.executemany(
            """INSERT INTO entity_operating_snapshots (
                   source_id, source_run_id, entity_kind, entity_id,
                   place_key, linked_place_count, crop_profile,
                   farm_count, farmer_count, open_task_count, completed_work_count,
                   visit_count, disease_report_count, pest_report_count,
                   location_evidence_count, photo_reference_count,
                   attendance_present_days, reported_area_acres,
                   latest_activity_at, latest_activity_kind, enrichment_version, refreshed_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (source_id, entity_kind, entity_id) DO UPDATE SET
                   source_run_id = excluded.source_run_id,
                   place_key = excluded.place_key,
                   linked_place_count = excluded.linked_place_count,
                   crop_profile = excluded.crop_profile,
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
                   latest_activity_kind = excluded.latest_activity_kind,
                   enrichment_version = excluded.enrichment_version,
                   refreshed_at = excluded.refreshed_at""",
            rows,
        )
    else:
        # The existing read model remains usable during the short, deliberate
        # migration window.  It simply omits the new classifications until the
        # private migration has been applied.
        rows = [_snapshot_row(snapshot, source_id, source_run_id, now) for snapshot in snapshots]
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


def classification_schema_available(conn) -> bool:
    """Whether the additive classification migration is ready for use."""
    if getattr(conn, "dialect", "sqlite") == "postgres":
        row = conn.execute(
            "SELECT to_regclass(?) AS relation_name", ("agro_place_catalog",)
        ).fetchone()
        return row is not None and row["relation_name"] is not None
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        ("place_catalog",),
    ).fetchone()
    return row is not None


def place_summary_schema_available(conn) -> bool:
    """Whether private place rollups can be refreshed and read."""
    if getattr(conn, "dialect", "sqlite") == "postgres":
        row = conn.execute(
            "SELECT to_regclass(?) AS relation_name", ("agro_place_operating_summaries",)
        ).fetchone()
        return row is not None and row["relation_name"] is not None
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        ("place_operating_summaries",),
    ).fetchone()
    return row is not None


def snapshot_index_for_source(conn, source_id: str) -> dict[tuple[str, str], dict[str, Any]]:
    """Read the current private snapshots as browser-safe operating context."""
    if not snapshot_table_available(conn):
        return {}
    classification_columns = """
                  place_key, linked_place_count, crop_profile, latest_activity_kind,
    """ if classification_schema_available(conn) else ""
    rows = conn.execute(
        """SELECT entity_kind, entity_id,
               {classification_columns}
                  farm_count, farmer_count,
                  open_task_count, completed_work_count, visit_count,
                  disease_report_count, pest_report_count,
                  location_evidence_count, photo_reference_count,
                  attendance_present_days, reported_area_acres,
                  latest_activity_at, refreshed_at
           FROM entity_operating_snapshots
           WHERE source_id = ? AND enrichment_version = ?""".format(
            classification_columns=classification_columns
        ),
        (source_id, ENRICHMENT_VERSION),
    )
    rows = rows.fetchall()
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
    result = {
        "metrics": factual,
        "tags": tags_for_snapshot(snapshot, now=now),
    }
    if "crop_profile" in snapshot:
        result["categories"] = {
            "crop_profile": _crop_profile(snapshot.get("crop_profile")),
            "linked_place_count": _integer(snapshot.get("linked_place_count")),
            "latest_activity_kind": _activity_kind(snapshot.get("latest_activity_kind")),
            "coverage": _coverage_for_snapshot(snapshot),
            "freshness": _freshness_for_snapshot(snapshot, now=now),
            "workload": _workload_for_snapshot(snapshot),
        }
    return result


def place_summaries_for_source(conn, source_id: str) -> list[dict[str, Any]]:
    """Return compact, browser-safe place context for maps and directories.

    The returned work count belongs to reported farmers connected to the place.
    It is deliberately not represented as a field-boundary or geo-fenced claim.
    """
    if not place_summary_schema_available(conn):
        return []
    rows = conn.execute(
        """SELECT summary.place_key, catalog.village_name, catalog.block_name,
                  catalog.district_name, summary.reported_farm_count,
                  summary.farmer_count, summary.field_worker_count,
                  summary.open_task_count, summary.visit_count,
                  summary.issue_report_count, summary.location_evidence_count,
                  summary.photo_reference_count, summary.latest_activity_at,
                  summary.refreshed_at
           FROM place_operating_summaries AS summary
           JOIN place_catalog AS catalog
             ON catalog.source_id = summary.source_id
            AND catalog.place_key = summary.place_key
           WHERE summary.source_id = ? AND summary.enrichment_version = ?
           ORDER BY summary.open_task_count DESC, summary.latest_activity_at DESC,
                    summary.place_key""",
        (source_id, ENRICHMENT_VERSION),
    ).fetchall()
    return [
        {
            "id": str(row["place_key"]),
            "place": _display_place(row),
            "metrics": {
                "reported_farm_count": _integer(row["reported_farm_count"]),
                "farmer_count": _integer(row["farmer_count"]),
                "field_worker_count": _integer(row["field_worker_count"]),
                "open_task_count": _integer(row["open_task_count"]),
                "visit_count": _integer(row["visit_count"]),
                "issue_report_count": _integer(row["issue_report_count"]),
                "location_evidence_count": _integer(row["location_evidence_count"]),
                "photo_reference_count": _integer(row["photo_reference_count"]),
                "latest_activity_at": row["latest_activity_at"],
                "refreshed_at": row["refreshed_at"],
            },
        }
        for row in rows
    ]


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
    crop_profile = _crop_profile(snapshot.get("crop_profile"))
    if entity_kind == "reported_farm" and crop_profile != "not_recorded":
        tags.append(_tag("crop_" + crop_profile, _crop_profile_label(crop_profile), "neutral"))
    if entity_kind == "farmer":
        farm_count = _integer(snapshot.get("farm_count"))
        if farm_count > 1:
            tags.append(_tag("multiple_farms", "Multiple farms", "neutral"))
        elif farm_count == 1:
            tags.append(_tag("farm_recorded", "Farm recorded", "neutral"))
    if entity_kind == "field_worker" and _integer(snapshot.get("farmer_count")):
        tags.append(_tag("farmers_assigned", "Farmers assigned", "neutral"))
    linked_places = _integer(snapshot.get("linked_place_count"))
    if entity_kind in {"farmer", "field_worker"} and linked_places > 1:
        tags.append(_tag("multiple_places", f"Across {linked_places} places", "neutral"))
    if _integer(snapshot.get("location_evidence_count")):
        tags.append(_tag("location_available", "Location available", "neutral"))
    if _integer(snapshot.get("photo_reference_count")):
        tags.append(_tag("photo_evidence", "Photo evidence", "neutral"))
    if _integer(snapshot.get("completed_work_count")):
        tags.append(_tag("work_completed", "Work completed", "neutral"))
    if entity_kind == "field_worker" and _integer(snapshot.get("attendance_present_days")):
        tags.append(_tag("attendance_recorded", "Attendance recorded", "neutral"))
    return tags


def _snapshot_row(
    snapshot: Mapping[str, Any], source_id: str, source_run_id: Optional[str], refreshed_at: str,
) -> tuple[Any, ...]:
    return (
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
        refreshed_at,
    )


def _classified_snapshot_row(
    snapshot: Mapping[str, Any], source_id: str, source_run_id: Optional[str], refreshed_at: str,
) -> tuple[Any, ...]:
    return (
        source_id,
        source_run_id,
        snapshot["entity_kind"],
        snapshot["entity_id"],
        snapshot.get("place_key"),
        snapshot["linked_place_count"],
        _crop_profile(snapshot.get("crop_profile")),
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
        _activity_kind(snapshot.get("latest_activity_kind")),
        ENRICHMENT_VERSION,
        refreshed_at,
    )


def _upsert_place_catalog(conn, source_id: str, snapshots: list[Mapping[str, Any]], refreshed_at: str) -> None:
    """Record normalized place cohorts without guessing aliases or coordinates."""
    places = {
        str(snapshot["place_key"]): snapshot["_place"]
        for snapshot in snapshots
        if snapshot.get("entity_kind") == "reported_farm"
        and snapshot.get("place_key")
        and snapshot.get("_place")
    }
    if not places:
        return
    rows = [
        (
            source_id,
            key,
            place["village_name"],
            place["block_name"],
            place["district_name"],
            place["first_seen_at"] or refreshed_at,
            place["last_seen_at"] or refreshed_at,
            ENRICHMENT_VERSION,
            refreshed_at,
        )
        for key, place in places.items()
    ]
    conn.executemany(
        """INSERT INTO place_catalog (
               source_id, place_key, village_name, block_name, district_name,
               first_seen_at, last_seen_at, enrichment_version, refreshed_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (source_id, place_key) DO UPDATE SET
               village_name = excluded.village_name,
               block_name = excluded.block_name,
               district_name = excluded.district_name,
               first_seen_at = CASE WHEN excluded.first_seen_at < place_catalog.first_seen_at
                   THEN excluded.first_seen_at ELSE place_catalog.first_seen_at END,
               last_seen_at = CASE WHEN excluded.last_seen_at > place_catalog.last_seen_at
                   THEN excluded.last_seen_at ELSE place_catalog.last_seen_at END,
               enrichment_version = excluded.enrichment_version,
               refreshed_at = excluded.refreshed_at""",
        rows,
    )


def _upsert_task_taxonomy(conn, source_id: str, refreshed_at: str) -> None:
    """Keep a small controlled vocabulary; reviewed mappings are never overwritten."""
    rows = conn.execute(
        """SELECT task_type, MIN(first_seen_at) AS first_seen_at,
                  MAX(last_seen_at) AS last_seen_at
           FROM trackwick_tasks
           WHERE source_id = ? AND data_quality_status = 'valid'
           GROUP BY task_type""",
        (source_id,),
    ).fetchall()
    values = [
        (
            source_id,
            _task_type_key(row["task_type"]),
            _task_kind(row["task_type"]),
            row["first_seen_at"] or refreshed_at,
            row["last_seen_at"] or refreshed_at,
            ENRICHMENT_VERSION,
            refreshed_at,
        )
        for row in rows
        if _task_type_key(row["task_type"])
    ]
    if not values:
        return
    conn.executemany(
        """INSERT INTO task_type_taxonomy (
               source_id, task_type_key, task_kind,
               first_seen_at, last_seen_at, enrichment_version, refreshed_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (source_id, task_type_key) DO UPDATE SET
               task_kind = CASE
                   WHEN task_type_taxonomy.classification_state = 'automatic'
                   THEN excluded.task_kind ELSE task_type_taxonomy.task_kind END,
               first_seen_at = CASE WHEN excluded.first_seen_at < task_type_taxonomy.first_seen_at
                   THEN excluded.first_seen_at ELSE task_type_taxonomy.first_seen_at END,
               last_seen_at = CASE WHEN excluded.last_seen_at > task_type_taxonomy.last_seen_at
                   THEN excluded.last_seen_at ELSE task_type_taxonomy.last_seen_at END,
               enrichment_version = excluded.enrichment_version,
               refreshed_at = excluded.refreshed_at""",
        values,
    )


def _upsert_place_summaries(
    conn, source_id: str, snapshots: list[Mapping[str, Any]], refreshed_at: str,
) -> None:
    """Refresh all current place cohorts without retaining removed cohorts."""
    # Keep the read model append-only from an importer perspective: a source
    # deletion marks the old cohort retired instead of requiring DELETE.
    conn.execute(
        """UPDATE place_operating_summaries
           SET enrichment_version = ?
           WHERE source_id = ? AND enrichment_version = ?""",
        (ENRICHMENT_VERSION + "-retired", source_id, ENRICHMENT_VERSION),
    )
    rows = _place_summary_rows(snapshots, source_id, refreshed_at)
    if not rows:
        return
    conn.executemany(
        """INSERT INTO place_operating_summaries (
               source_id, place_key, reported_farm_count, farmer_count,
               field_worker_count, open_task_count, visit_count,
               issue_report_count, location_evidence_count,
               photo_reference_count, latest_activity_at,
               enrichment_version, refreshed_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (source_id, place_key) DO UPDATE SET
               reported_farm_count = excluded.reported_farm_count,
               farmer_count = excluded.farmer_count,
               field_worker_count = excluded.field_worker_count,
               open_task_count = excluded.open_task_count,
               visit_count = excluded.visit_count,
               issue_report_count = excluded.issue_report_count,
               location_evidence_count = excluded.location_evidence_count,
               photo_reference_count = excluded.photo_reference_count,
               latest_activity_at = excluded.latest_activity_at,
               enrichment_version = excluded.enrichment_version,
               refreshed_at = excluded.refreshed_at""",
        rows,
    )


def _place_summary_rows(
    snapshots: list[Mapping[str, Any]], source_id: str, refreshed_at: str,
) -> list[tuple[Any, ...]]:
    """Build strictly reported-place rollups from the current entity snapshots."""
    summaries: dict[str, dict[str, Any]] = {}
    farmer_places: dict[str, set[str]] = defaultdict(set)

    def summary_for(place_key: str) -> dict[str, Any]:
        return summaries.setdefault(place_key, {
            "reported_farm_count": 0,
            "farmer_ids": set(),
            "field_worker_ids": set(),
            "open_task_count": 0,
            "visit_count": 0,
            "issue_report_count": 0,
            "location_evidence_count": 0,
            "photo_reference_count": 0,
            "latest_activity_at": None,
        })

    for snapshot in snapshots:
        if snapshot.get("entity_kind") != "reported_farm" or not snapshot.get("place_key"):
            continue
        place_key = str(snapshot["place_key"])
        summary = summary_for(place_key)
        summary["reported_farm_count"] += 1
        farmer_id = snapshot.get("_farmer_id")
        if farmer_id:
            farmer_id = str(farmer_id)
            summary["farmer_ids"].add(farmer_id)
            farmer_places[farmer_id].add(place_key)
        summary["visit_count"] += _integer(snapshot.get("visit_count"))
        summary["issue_report_count"] += (
            _integer(snapshot.get("disease_report_count"))
            + _integer(snapshot.get("pest_report_count"))
        )
        summary["location_evidence_count"] += _integer(snapshot.get("location_evidence_count"))
        summary["photo_reference_count"] += _integer(snapshot.get("photo_reference_count"))
        latest = _timestamp(snapshot.get("latest_activity_at"))
        current = _timestamp(summary.get("latest_activity_at"))
        if latest is not None and (current is None or latest > current):
            summary["latest_activity_at"] = latest.isoformat()

    for snapshot in snapshots:
        entity_kind = snapshot.get("entity_kind")
        if entity_kind == "farmer":
            farmer_id = str(snapshot["entity_id"])
            for place_key in farmer_places.get(farmer_id, set()):
                summary_for(place_key)["open_task_count"] += _integer(snapshot.get("open_task_count"))
        elif entity_kind == "field_worker":
            worker_id = str(snapshot["entity_id"])
            assigned_farmer_ids = snapshot.get("_farmer_ids", set())
            places = set().union(*(
                farmer_places.get(str(farmer_id), set())
                for farmer_id in assigned_farmer_ids
            ))
            for place_key in places:
                summary_for(place_key)["field_worker_ids"].add(worker_id)

    return [
        (
            source_id,
            place_key,
            summary["reported_farm_count"],
            len(summary["farmer_ids"]),
            len(summary["field_worker_ids"]),
            summary["open_task_count"],
            summary["visit_count"],
            summary["issue_report_count"],
            summary["location_evidence_count"],
            summary["photo_reference_count"],
            summary["latest_activity_at"],
            ENRICHMENT_VERSION,
            refreshed_at,
        )
        for place_key, summary in summaries.items()
    ]


def _build_snapshots(conn, source_id: str) -> list[dict[str, Any]]:
    parties = conn.execute(
        """SELECT id, party_kind FROM trackwick_parties
           WHERE source_id = ? AND data_quality_status = 'valid'""",
        (source_id,),
    ).fetchall()
    tasks = conn.execute(
        """SELECT id, farmer_party_id, field_worker_party_id, task_type, task_status,
                  provider_created_at, provider_started_at, provider_completed_at
           FROM trackwick_tasks
           WHERE source_id = ? AND data_quality_status = 'valid'""",
        (source_id,),
    ).fetchall()
    registrations = conn.execute(
        """SELECT id, task_id, farmer_party_id, village_name, block_name, district_name,
                  reported_total_area_acres, reported_pb1_area_acres,
                  reported_1718_area_acres, first_seen_at, last_seen_at
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
        """SELECT task_id, provider_created_at FROM trackwick_media_references
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
    farmer_places: dict[str, set[str]] = defaultdict(set)
    farmer_crops: dict[str, set[str]] = defaultdict(set)

    for registration in registrations:
        registration_id = str(registration["id"])
        farm = _empty_snapshot("reported_farm", registration_id)
        farm["reported_area_acres"] = _number(registration["reported_total_area_acres"])
        place = _place_from_registration(registration)
        if place is not None:
            farm["place_key"] = place["place_key"]
            farm["linked_place_count"] = 1
            farm["_place"] = place
        crop_profile = _crop_profile_for_area(
            registration["reported_pb1_area_acres"], registration["reported_1718_area_acres"],
        )
        farm["crop_profile"] = crop_profile
        registration_task = task_by_id.get(str(registration["task_id"])) if registration["task_id"] else None
        if registration_task is not None:
            _add_task(farm, registration_task)
        snapshots[("reported_farm", registration_id)] = farm
        farmer_id = registration["farmer_party_id"]
        if farmer_id and ("farmer", str(farmer_id)) in snapshots:
            farm["_farmer_id"] = str(farmer_id)
            farmer = snapshots[("farmer", str(farmer_id))]
            farmer["farm_count"] += 1
            farmer["reported_area_acres"] = _sum_numbers(
                farmer["reported_area_acres"], registration["reported_total_area_acres"],
            )
            if place is not None:
                farmer_places[str(farmer_id)].add(place["place_key"])
            if crop_profile != "not_recorded":
                farmer_crops[str(farmer_id)].add(crop_profile)

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
        _add_task_event(snapshots, task, "visit_count", visit["observed_at"], "visit")
        _add_registration_task_event(
            snapshots, registration_by_task, task, "visit_count", visit["observed_at"], "visit",
        )

    for finding in findings:
        task = task_by_id.get(str(finding["visit_task_id"]))
        metric = "disease_report_count" if finding["finding_kind"] == "disease" else "pest_report_count"
        _add_task_event(snapshots, task, metric, finding["observed_at"], "issue")
        _add_registration_task_event(
            snapshots, registration_by_task, task, metric, finding["observed_at"], "issue",
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
            _observe(target, location["observed_at"], "location")

    for reference in media:
        task = task_by_id.get(str(reference["task_id"]))
        _add_task_event(snapshots, task, "photo_reference_count", reference["provider_created_at"], "photo")
        if task is not None:
            registration = registration_by_task.get(str(task["id"]))
            if registration is not None:
                farm = snapshots.get(("reported_farm", str(registration["id"])))
                if farm is not None:
                    farm["photo_reference_count"] += 1
                    _observe(farm, reference["provider_created_at"], "photo")

    for day in worker_days:
        worker = snapshots.get(("field_worker", str(day["field_worker_party_id"])))
        if worker is None:
            continue
        if day["attendance_status"] == "present":
            worker["attendance_present_days"] += 1
        _observe(worker, day["observed_on"], "attendance")

    for key, snapshot in snapshots.items():
        assigned_farmer_ids = snapshot.get("_farmer_ids", set())
        snapshot["farmer_count"] = len(assigned_farmer_ids)
        if key[0] == "farmer":
            places = farmer_places.get(key[1], set())
            snapshot["linked_place_count"] = len(places)
            snapshot["crop_profile"] = _merged_crop_profile(farmer_crops.get(key[1], set()))
        elif key[0] == "field_worker":
            places = set().union(*(farmer_places.get(farmer_id, set()) for farmer_id in assigned_farmer_ids))
            snapshot["linked_place_count"] = len(places)
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


def _place_from_registration(registration: Mapping[str, Any]) -> Optional[dict[str, Optional[str]]]:
    registration = dict(registration)
    village_name = _place_part(registration.get("village_name"))
    block_name = _place_part(registration.get("block_name"))
    district_name = _place_part(registration.get("district_name"))
    parts = [part for part in (village_name, block_name, district_name) if part]
    if not parts:
        return None
    place_key = "|".join(_normalised_key(part) for part in parts)
    return {
        "place_key": place_key,
        "village_name": village_name,
        "block_name": block_name,
        "district_name": district_name,
        "first_seen_at": registration.get("first_seen_at"),
        "last_seen_at": registration.get("last_seen_at"),
    }


def _place_part(value: Any) -> Optional[str]:
    if value is None:
        return None
    compact = " ".join(str(value).split())
    return compact or None


def _normalised_key(value: str) -> str:
    """Normalize case, whitespace, and punctuation—not spelling or identity."""
    return re.sub(r"[^\w]+", " ", value.casefold()).strip().replace(" ", "-")


def _task_type_key(value: Any) -> str:
    return _normalised_key(_place_part(value) or "")


def _task_kind(value: Any) -> str:
    key = _task_type_key(value)
    if "visit" in key:
        return "visit"
    if "registration" in key:
        return "registration"
    if "soil" in key:
        return "soil"
    if "query" in key:
        return "query"
    if "agronomy" in key or "team" in key:
        return "team_work"
    return "other"


def _task_activity_kind(value: Any) -> str:
    kind = _task_kind(value)
    return kind if kind in {"visit", "registration"} else "work"


def _crop_profile_for_area(pb1_area: Any, var1718_area: Any) -> str:
    has_pb1 = (_number(pb1_area) or 0) > 0
    has_1718 = (_number(var1718_area) or 0) > 0
    if has_pb1 and has_1718:
        return "mixed"
    if has_pb1:
        return "pb1"
    if has_1718:
        return "1718"
    return "not_recorded"


def _merged_crop_profile(profiles: set[str]) -> str:
    usable = {_crop_profile(profile) for profile in profiles if _crop_profile(profile) != "not_recorded"}
    return next(iter(usable)) if len(usable) == 1 else "mixed" if usable else "not_recorded"


def _crop_profile(value: Any) -> str:
    return str(value) if str(value) in _CROP_PROFILES else "not_recorded"


def _crop_profile_label(profile: str) -> str:
    return {"pb1": "PB1 paddy", "1718": "1718 paddy", "mixed": "Mixed paddy"}.get(profile, "")


def _activity_kind(value: Any) -> str:
    return str(value) if str(value) in _ACTIVITY_KINDS else "unknown"


def _coverage_for_snapshot(snapshot: Mapping[str, Any]) -> dict[str, bool]:
    """Exact evidence-presence flags, not a quality score or a prediction."""
    crop_profile = _crop_profile(snapshot.get("crop_profile"))
    return {
        "location_recorded": _integer(snapshot.get("location_evidence_count")) > 0,
        "photo_recorded": _integer(snapshot.get("photo_reference_count")) > 0,
        "visit_recorded": _integer(snapshot.get("visit_count")) > 0,
        "issue_recorded": (
            _integer(snapshot.get("disease_report_count"))
            + _integer(snapshot.get("pest_report_count"))
        ) > 0,
        "area_recorded": _number(snapshot.get("reported_area_acres")) is not None,
        "crop_recorded": crop_profile != "not_recorded",
    }


def _freshness_for_snapshot(
    snapshot: Mapping[str, Any], *, now: Optional[datetime] = None,
) -> str:
    """A live time band derived at read time, so a cached record ages honestly."""
    activity = _timestamp(snapshot.get("latest_activity_at"))
    if activity is None:
        return "no_activity_recorded"
    age_seconds = ((now or datetime.now(timezone.utc)) - activity).total_seconds()
    if age_seconds <= 86_400:
        return "updated_today"
    if age_seconds <= 7 * 86_400:
        return "updated_this_week"
    if age_seconds <= 30 * 86_400:
        return "updated_this_month"
    return "earlier_activity"


def _workload_for_snapshot(snapshot: Mapping[str, Any]) -> str:
    """A small factual filter band; detailed cards always retain the exact count."""
    open_tasks = _integer(snapshot.get("open_task_count"))
    if open_tasks == 0:
        return "no_open_tasks"
    if open_tasks <= 2:
        return "one_to_two_open_tasks"
    return "three_or_more_open_tasks"


def _display_place(row: Mapping[str, Any]) -> str:
    return " · ".join(
        str(row[key]) for key in ("village_name", "block_name", "district_name") if row[key]
    )


def _empty_snapshot(entity_kind: str, entity_id: str) -> dict[str, Any]:
    return {
        "entity_kind": entity_kind,
        "entity_id": entity_id,
        "place_key": None,
        "linked_place_count": 0,
        "crop_profile": "not_recorded",
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
        "latest_activity_kind": "unknown",
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
        _task_activity_kind(task["task_type"]),
    )


def _add_task_event(
    snapshots: Mapping[tuple[str, str], dict[str, Any]],
    task: Optional[Mapping[str, Any]],
    metric: str,
    observed_at: Optional[str],
    activity_kind: str,
) -> None:
    if task is None:
        return
    for entity_kind, party_key in (("farmer", "farmer_party_id"), ("field_worker", "field_worker_party_id")):
        party_id = task[party_key]
        if party_id and (entity_kind, str(party_id)) in snapshots:
            snapshot = snapshots[(entity_kind, str(party_id))]
            snapshot[metric] += 1
            _observe(snapshot, observed_at, activity_kind)


def _add_registration_task_event(
    snapshots: Mapping[tuple[str, str], dict[str, Any]],
    registrations_by_task: Mapping[str, Mapping[str, Any]],
    task: Optional[Mapping[str, Any]],
    metric: str,
    observed_at: Optional[str],
    activity_kind: str,
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
    _observe(snapshot, observed_at, activity_kind)


def _observe(snapshot: dict[str, Any], value: Any, activity_kind: str = "unknown") -> None:
    candidate = _timestamp(value)
    current = _timestamp(snapshot.get("latest_activity_at"))
    kind = _activity_kind(activity_kind)
    if candidate is not None and (
        current is None
        or candidate > current
        or candidate == current and _ACTIVITY_PRIORITY[kind] >= _ACTIVITY_PRIORITY[_activity_kind(snapshot.get("latest_activity_kind"))]
    ):
        snapshot["latest_activity_at"] = candidate.isoformat()
        snapshot["latest_activity_kind"] = kind


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
