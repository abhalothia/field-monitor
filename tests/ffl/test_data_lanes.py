from fastapi import FastAPI
from fastapi.testclient import TestClient

from ffl.api.data_lanes_routes import router as data_lanes_router
from ffl.persistence.database import open_connection
from ffl.persistence import repository
from ffl.persistence.schema import create_schema
from ffl.services import data_lanes, season, sources, templates


def _lane(snapshot, key):
    return next(lane for lane in snapshot["lanes"] if lane["key"] == key)


def _register_source(ffl_db, owner, source_key):
    return sources.register_source(
        ffl_db,
        source_key=source_key,
        display_name="Reviewed source",
        source_type="not-installed",
        purpose="regional context",
        authority_level="official",
        owner_id=owner.id,
        permitted_data_classes=["forecast"],
        schema_version="v1",
        mapping_version="v1",
        default_coverage={"district": "reviewed"},
        enabled=True,
    )


def test_data_lanes_are_fixed_honest_and_read_only_before_first_farm(ffl_db):
    before = ffl_db.total_changes

    snapshot = data_lanes.data_lanes_snapshot(ffl_db)

    assert snapshot["version"] == "data-lanes-v1"
    assert [lane["key"] for lane in snapshot["lanes"]] == [
        "field_truth", "weather", "soil_water", "satellite", "market",
    ]
    assert snapshot["scope"] == {"farm_recorded": False, "active_allocation_recorded": False}
    assert _lane(snapshot, "field_truth")["status"] == "needs_active_crop"
    assert _lane(snapshot, "weather")["status"] == "needs_first_farm"
    assert _lane(snapshot, "soil_water")["status"] == "needs_first_farm"
    assert _lane(snapshot, "satellite")["status"] == "needs_first_farm"
    assert _lane(snapshot, "market")["status"] == "needs_active_crop"
    assert ffl_db.total_changes == before
    assert "https://" not in repr(snapshot)


def test_data_lanes_keep_context_gated_by_farm_truth_and_review(ffl_db, crop_allocation, users):
    unit_row = ffl_db.execute(
        "SELECT operating_unit_id FROM crop_allocations WHERE id = ?", (crop_allocation.id,)
    ).fetchone()
    repository.create_operating_unit_location(
        ffl_db,
        unit_row["operating_unit_id"],
        state_name="Uttar Pradesh",
        district_name="Reviewed district",
        district_context_key="up:reviewed-district",
        verified_by_person_id=users.lead.id,
        verified_at="2026-08-01T09:00:00+00:00",
    )
    evidence = repository.create_evidence_artifact(
        ffl_db,
        "a" * 64,
        "application/pdf",
        "private://evidence/soil-report",
        created_by_person_id=users.lead.id,
    )
    repository.create_soil_baseline(
        ffl_db,
        unit_row["operating_unit_id"],
        sampled_on="2026-07-30",
        lab_name="Reviewed lab",
        measurements={"ph": {"value": 6.8, "unit": "pH"}},
        evidence_artifact_id=evidence.id,
        reviewed_by_person_id=users.lead.id,
    )
    _register_source(ffl_db, users.lead, "imd-weather")
    _register_source(ffl_db, users.lead, "copernicus-sentinel-2-context")
    _register_source(ffl_db, users.lead, "agmarknet-market-context")

    before = ffl_db.total_changes
    snapshot = data_lanes.data_lanes_snapshot(ffl_db)

    assert _lane(snapshot, "field_truth")["status"] == "needs_first_observation"
    assert _lane(snapshot, "weather")["status"] == "not_run"
    assert _lane(snapshot, "soil_water")["status"] == "ready"
    assert _lane(snapshot, "satellite")["status"] == "needs_field_boundary"
    assert _lane(snapshot, "market")["status"] == "needs_market_mapping"
    assert "private://" not in repr(snapshot)
    assert "Reviewed district" not in repr(snapshot)
    assert ffl_db.total_changes == before


def test_submitted_field_signal_is_review_needed_not_ready(ffl_db, crop_allocation, users):
    template = templates.publish_signal_template(
        ffl_db,
        "data-lane-check",
        1,
        [{"key": "condition", "type": "text", "required": True}],
        users.lead.id,
    )
    season.record_field_signal(
        ffl_db,
        crop_allocation.id,
        template.id,
        1,
        "2026-08-01T08:00:00+00:00",
        users.operator.id,
        {"condition": "reported"},
        status="submitted",
    )

    snapshot = data_lanes.data_lanes_snapshot(ffl_db)

    lane = _lane(snapshot, "field_truth")
    assert lane["status"] == "review_needed"
    assert "submitted report is not an accepted operating fact" in lane["limitation"]


def test_data_lanes_route_is_read_only_and_has_no_operating_identifiers():
    conn = open_connection(":memory:", check_same_thread=False)
    create_schema(conn)
    app = FastAPI()
    app.state.conn = conn
    app.include_router(data_lanes_router)
    client = TestClient(app)
    before = conn.total_changes

    response = client.get("/api/v1/data-lanes")

    assert response.status_code == 200
    body = response.json()
    assert len(body["lanes"]) == 5
    assert "operating_unit_id" not in repr(body)
    assert conn.total_changes == before
    conn.close()
