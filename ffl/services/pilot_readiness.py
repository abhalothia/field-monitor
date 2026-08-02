"""A manager-safe, read-only account of what the first farm still needs.

This is intentionally an onboarding ledger, not a seed generator.  It never
creates a fictional farm, assigns a person, chooses a crop, or treats an
external reference dataset as the farm's location.  It gives the AGRO CEO
surface an honest next step before the first operating record exists.
"""

from typing import Any, Dict, List, Sequence, Tuple


_STAGES: Sequence[Tuple[str, str, str]] = (
    (
        "farm_and_team",
        "Farm and accountable team",
        "Add the real operating unit and the named people who can own field work and review it.",
    ),
    (
        "land_and_rights",
        "Land and operating rights",
        "Record the usable parcels, operating blocks, and dated right-to-operate evidence.",
    ),
    (
        "active_season",
        "Active crop plan",
        "Add the current season and an active crop allocation with its accountable owner.",
    ),
    (
        "verified_context",
        "Verified local context",
        "Confirm state, district, village or PIN where available; this is not a parcel boundary or GPS claim.",
    ),
    (
        "soil_evidence",
        "Reviewed soil baseline",
        "Retain the original lab report as evidence, then record measured values with sampling date and units.",
    ),
    (
        "field_loop",
        "First evidence loop",
        "Define the next critical work and its required field evidence before asking the field team to report.",
    ),
)


def _count(conn, query: str, params: Tuple[object, ...] = ()) -> int:
    row = conn.execute(query, params).fetchone()
    return int(row[0] if row is not None else 0)


def pilot_readiness(conn) -> Dict[str, Any]:
    """Return aggregate setup progress without leaking people, evidence, or IDs."""

    counts = {
        "operating_units": _count(conn, "SELECT count(*) FROM operating_units"),
        "people": _count(conn, "SELECT count(*) FROM people"),
        "land_parcels": _count(conn, "SELECT count(*) FROM land_parcels"),
        "operational_blocks": _count(conn, "SELECT count(*) FROM operational_blocks"),
        "rights_to_operate": _count(conn, "SELECT count(*) FROM rights_to_operate"),
        "active_allocations": _count(conn, "SELECT count(*) FROM crop_allocations WHERE status = 'active'"),
        "active_locations": _count(conn, "SELECT count(*) FROM operating_unit_locations WHERE status = 'active'"),
        "reviewed_soil_baselines": _count(conn, "SELECT count(*) FROM soil_baselines WHERE status = 'reviewed'"),
        "published_signal_templates": _count(conn, "SELECT count(*) FROM signal_templates WHERE status = 'published'"),
        "open_work_items": _count(
            conn,
            "SELECT count(*) FROM work_items WHERE status IN ('planned', 'in_progress', 'blocked', 'submitted', 'rejected')",
        ),
    }
    complete = {
        "farm_and_team": counts["operating_units"] > 0 and counts["people"] >= 2,
        "land_and_rights": (
            counts["land_parcels"] > 0
            and counts["operational_blocks"] > 0
            and counts["rights_to_operate"] > 0
        ),
        "active_season": counts["active_allocations"] > 0,
        "verified_context": counts["active_locations"] > 0,
        "soil_evidence": counts["reviewed_soil_baselines"] > 0,
        "field_loop": counts["published_signal_templates"] > 0 and counts["open_work_items"] > 0,
    }
    stages: List[Dict[str, str]] = []
    for key, title, next_action in _STAGES:
        stages.append(
            {
                "key": key,
                "title": title,
                "status": "ready" if complete[key] else "not_started",
                "next_action": next_action,
            }
        )
    completed = sum(1 for stage in stages if stage["status"] == "ready")
    if completed == len(stages):
        overall = "ready_for_field_loop"
    elif completed == 0:
        overall = "not_started"
    else:
        overall = "in_setup"
    next_stage = next((stage for stage in stages if stage["status"] != "ready"), None)
    return {
        "version": "pilot-readiness-v1",
        "overall": overall,
        "progress": {"completed": completed, "total": len(stages)},
        "next_stage": next_stage,
        "stages": stages,
        "counts": counts,
    }
