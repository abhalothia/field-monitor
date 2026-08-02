"""Manager-safe readiness for the five FFL operating-data lanes.

This is deliberately a *read model*, not a source orchestrator.  It lets the
AGRO CEO surface say which evidence/context lane is ready for use and which
gate remains, without fetching a public source, exposing a farm location, or
turning context into agronomic advice.
"""

from typing import Any, Dict, Optional


_SOURCE_KEYS = {
    "weather": "imd-weather",
    "satellite": "copernicus-sentinel-2-context",
    "market": "agmarknet-market-context",
}


def _count(conn, query: str, params: tuple = ()) -> int:
    row = conn.execute(query, params).fetchone()
    return int(row[0] if row is not None else 0)


def _source_state(conn, key: str) -> Dict[str, str]:
    """Return a purpose-limited source state with no endpoint or payload data."""
    source = conn.execute(
        "SELECT id, enabled FROM source_registry WHERE source_key = ?", (key,)
    ).fetchone()
    if source is None:
        return {"state": "not_connected", "detail": "No approved FFL connection is configured."}
    if not bool(source["enabled"]):
        return {"state": "access_review", "detail": "A source record exists but is not enabled."}
    run = conn.execute(
        """SELECT status FROM source_runs WHERE source_id = ?
           ORDER BY created_at DESC, id DESC LIMIT 1""",
        (source["id"],),
    ).fetchone()
    if run is None:
        return {"state": "not_run", "detail": "The approved connection has not produced a reviewed run."}
    if run["status"] == "succeeded":
        return {"state": "context_available", "detail": "A reviewed source run is available as context."}
    return {"state": "attention", "detail": "The latest source run needs operator attention."}


def _lane(
    key: str,
    name: str,
    status: str,
    source: str,
    fact: str,
    limitation: str,
    next_move: str,
) -> Dict[str, str]:
    return {
        "key": key,
        "name": name,
        "status": status,
        "source": source,
        "fact": fact,
        "limitation": limitation,
        "next_move": next_move,
    }


def data_lanes_snapshot(conn) -> Dict[str, Any]:
    """Describe the five data lanes using aggregate canonical-record state.

    The result intentionally excludes IDs, people, exact locations, crop
    values, evidence metadata/content, provider URLs, credentials, and source
    payloads.  A source being available means *context available*, never that
    a farm fact, task completion, sale, or agronomic decision is proven.
    """
    farm_count = _count(conn, "SELECT count(*) FROM operating_units")
    active_allocations = _count(conn, "SELECT count(*) FROM crop_allocations WHERE status = 'active'")
    active_locations = _count(conn, "SELECT count(*) FROM operating_unit_locations WHERE status = 'active'")
    reviewed_soil = _count(conn, "SELECT count(*) FROM soil_baselines WHERE status = 'reviewed'")
    field_reports_waiting = _count(
        conn, "SELECT count(*) FROM field_signals WHERE status IN ('draft', 'submitted')"
    )
    approved_field_reports = _count(conn, "SELECT count(*) FROM field_signals WHERE status = 'approved'")

    if active_allocations == 0:
        field_truth = _lane(
            "field_truth", "Field truth", "needs_active_crop", "Field team + retained FFL evidence",
            "No active crop allocation is recorded yet.",
            "Public data never replaces an attributable field observation.",
            "Record the first active crop plan, then define the first field check.",
        )
    elif field_reports_waiting:
        field_truth = _lane(
            "field_truth", "Field truth", "review_needed", "Field team + retained FFL evidence",
            "A field report is waiting for human review.",
            "A submitted report is not an accepted operating fact.",
            "Review the submitted field report through the canonical field-signal path.",
        )
    elif approved_field_reports:
        field_truth = _lane(
            "field_truth", "Field truth", "ready", "Field team + retained FFL evidence",
            "Reviewed field evidence exists for the active operating record.",
            "Keep observed time, accountable person, and required evidence attached to each new report.",
            "Use the next crop-stage check to keep the field loop current.",
        )
    else:
        field_truth = _lane(
            "field_truth", "Field truth", "needs_first_observation", "Field team + retained FFL evidence",
            "An active crop exists, but no reviewed field observation is recorded.",
            "A weather or satellite signal cannot prove what happened in the field.",
            "Define one critical check and collect attributable field evidence.",
        )

    if farm_count == 0:
        weather = _lane(
            "weather", "Weather", "needs_first_farm", "India Meteorological Department (IMD)",
            "No operating farm is recorded yet.",
            "Regional weather is context, not a local station reading or a work instruction.",
            "Create the reviewed first-farm pack before connecting district context.",
        )
    elif active_locations == 0:
        weather = _lane(
            "weather", "Weather", "needs_verified_district", "India Meteorological Department (IMD)",
            "The farm has no reviewed administrative context yet.",
            "A district is not a parcel boundary and does not prove plot conditions.",
            "Review the farm district before connecting IMD context.",
        )
    else:
        state = _source_state(conn, _SOURCE_KEYS["weather"])
        weather = _lane(
            "weather", "Weather", state["state"], "India Meteorological Department (IMD)", state["detail"],
            "District weather and warnings guide a manager watch; they never complete work or prescribe a crop action.",
            "Complete IMD access, attribution, cache, and mapping review before enabling a live adapter.",
        )

    if farm_count == 0:
        soil = _lane(
            "soil_water", "Soil & water", "needs_first_farm", "Reviewed lab report + field measurement",
            "No operating farm is recorded yet.",
            "Predicted soil layers do not replace a current, attributable lab report.",
            "Create the first farm, then retain its soil report as private evidence.",
        )
    elif reviewed_soil:
        soil = _lane(
            "soil_water", "Soil & water", "ready", "Reviewed lab report + field measurement",
            "A reviewed soil baseline is linked to private evidence.",
            "A baseline is a starting point; irrigation and soil conditions still need observed field checks.",
            "Add irrigation observations at the next critical crop stage.",
        )
    else:
        soil = _lane(
            "soil_water", "Soil & water", "needs_lab_report", "Reviewed lab report + field measurement",
            "No reviewed soil baseline is attached to the operating record.",
            "SoilGrids can inform a sampling plan, not a farm-specific decision.",
            "Retain one current lab report with sample date, depth, units, and reviewer.",
        )

    if farm_count == 0:
        satellite = _lane(
            "satellite", "Satellite", "needs_first_farm", "Copernicus Sentinel-2",
            "No operating farm is recorded yet.",
            "Imagery cannot establish a farm boundary, diagnose a crop, or prove work was completed.",
            "Create the first farm and its field-evidence loop before considering imagery.",
        )
    else:
        source_state = _source_state(conn, _SOURCE_KEYS["satellite"])
        satellite = _lane(
            "satellite", "Satellite", "needs_field_boundary", "Copernicus Sentinel-2",
            source_state["detail"] + " A reviewed field boundary is not yet part of FFL's operating record.",
            "Satellite context is corroboration only and must be checked against field evidence.",
            "Design the private reviewed-boundary workflow, then validate imagery against ground observations.",
        )

    if active_allocations == 0:
        market = _lane(
            "market", "Market", "needs_active_crop", "AGMARKNET / data.gov.in",
            "No active crop allocation is recorded yet.",
            "Public mandi prices are not buyer offers, sale commitments, or realised farm prices.",
            "Record the active crop before mapping a relevant market and commodity.",
        )
    else:
        source_state = _source_state(conn, _SOURCE_KEYS["market"])
        market = _lane(
            "market", "Market", "needs_market_mapping", "AGMARKNET / data.gov.in",
            source_state["detail"] + " No named market/commodity/grade mapping is recorded.",
            "Market context informs a conversation; it does not make a sale decision.",
            "Choose the relevant market, commodity, grade, unit, and freshness rule for manager review.",
        )

    return {
        "version": "data-lanes-v1",
        "scope": {
            "farm_recorded": farm_count > 0,
            "active_allocation_recorded": active_allocations > 0,
        },
        "lanes": [field_truth, weather, soil, satellite, market],
    }
