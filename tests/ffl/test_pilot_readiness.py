from ffl.api.context_routes import router as context_router
from ffl.persistence import repository
from ffl.persistence.schema import create_schema
from ffl.services import pilot_readiness, templates


def test_pilot_readiness_starts_with_real_setup_questions(ffl_db):
    result = pilot_readiness.pilot_readiness(ffl_db)

    assert result["overall"] == "not_started"
    assert result["progress"] == {"completed": 0, "total": 6}
    assert result["next_stage"]["key"] == "farm_and_team"
    assert result["counts"]["operating_units"] == 0
    assert "GPS" in result["stages"][3]["next_action"]


def test_pilot_readiness_tracks_the_complete_minimum_field_loop(ffl_db):
    manager = repository.create_person(ffl_db, "Field Manager", "farm_manager")
    operator = repository.create_person(ffl_db, "Field Operator", "field_operator")
    unit = repository.create_operating_unit(ffl_db, "Fortune Farm")
    parcel = repository.create_land_parcel(ffl_db, unit.id, "Paddy parcel", 2.0)
    block = repository.create_operational_block(ffl_db, unit.id, "Paddy block", 2.0)
    repository.link_block_parcel(ffl_db, block.id, parcel.id)
    repository.create_right_to_operate(ffl_db, parcel.id, "lease", "2026-06-01", "2026-11-30")
    season = repository.create_season(ffl_db, unit.id, "Kharif 2026", "2026-06-01", "2026-11-30")
    allocation = repository.create_crop_allocation(
        ffl_db, unit.id, block.id, season.id, "Rice", "Pusa 1121", 2.0
    )
    repository.create_operating_unit_location(
        ffl_db, unit.id, "Uttar Pradesh", "Meerut", "up:meerut", manager.id,
        "2026-08-01T08:00:00Z", village_name="Verified village", pincode="250001",
    )
    evidence = repository.create_evidence_artifact(
        ffl_db, "a" * 64, "application/pdf", "private://evidence/soil-a.pdf", "soil-a.pdf", 123,
        created_by_person_id=manager.id,
    )
    repository.create_soil_baseline(
        ffl_db, unit.id, "2026-07-20", "Pilot lab", {"pH": {"value": 7.1, "unit": "pH"}},
        evidence.id, manager.id,
    )
    template = templates.publish_signal_template(
        ffl_db, "field-check", 1, [{"key": "note", "type": "text", "required": True}], manager.id
    )
    assert template.status == "published"
    repository.create_work_item(
        ffl_db, allocation.id, "Inspect irrigation", operator.id, "2026-08-02T08:00:00Z", initial_status="planned"
    )

    result = pilot_readiness.pilot_readiness(ffl_db)

    assert result["overall"] == "ready_for_field_loop"
    assert result["progress"] == {"completed": 6, "total": 6}
    assert result["next_stage"] is None
    assert result["counts"]["active_allocations"] == 1
    assert {stage["status"] for stage in result["stages"]} == {"ready"}


def test_readiness_route_is_read_only_and_returns_aggregate_setup_state(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from ffl.persistence.database import open_connection

    app = FastAPI()
    app.include_router(context_router)
    conn = open_connection(str(tmp_path / "readiness.db"), check_same_thread=False)
    create_schema(conn)
    app.state.conn = conn
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/pilot/readiness")
        assert response.status_code == 200
        assert response.json()["overall"] == "not_started"
        assert conn.execute("SELECT count(*) FROM operating_units").fetchone()[0] == 0
    finally:
        conn.close()
