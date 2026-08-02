from datetime import datetime, timezone
import hashlib

from fastapi.testclient import TestClient
import pytest

from ffl.app import create_app
from ffl.persistence import repository
from ffl.services import morning_brief, sources


NOW = datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc)


def _artifact(conn, person_id, text="soil lab report"):
    return repository.create_evidence_artifact(
        conn, hashlib.sha256(text.encode("utf-8")).hexdigest(), "application/pdf",
        "evidence/soil/report.pdf", created_by_person_id=person_id,
    )


def _location(conn, allocation, person_id):
    return repository.create_operating_unit_location(
        conn, allocation.operating_unit_id, "Uttar Pradesh", "Meerut", "IN-UP-MEERUT",
        person_id, "2026-07-31T10:00:00Z", village_name="Pilot Village", pincode="250001",
    )


def _imd(conn, owner_id, enabled=False):
    return sources.register_source(
        conn,
        source_key="imd-weather",
        display_name="India Meteorological Department",
        source_type="official_context",
        purpose="district weather context",
        authority_level="official",
        owner_id=owner_id,
        permitted_data_classes=["forecast", "warning"],
        schema_version="imd-v1",
        mapping_version="district-v1",
        default_coverage={"country": "IN", "state": "Uttar Pradesh"},
        credentials_reference="env://FFL_IMD_ACCESS_REFERENCE",
        freshness_target_hours=12,
        license_notes="official access review required",
        enabled=enabled,
    )


def test_brief_exposes_missing_foundations_without_inventing_context(ffl_db, crop_allocation):
    result = morning_brief.morning_brief(ffl_db, crop_allocation.operating_unit_id, NOW)

    assert result["brief_kind"] == "deterministic_operating_brief"
    assert result["model_generated"] is False
    assert result["context"]["location"] == {"status": "missing"}
    assert result["context"]["soil"] == {"status": "missing"}
    assert {item["code"] for item in result["attention"]} >= {
        "location_unverified", "soil_baseline_missing",
    }
    assert all("recommend" not in rule.lower() for rule in result["guardrails"])


def test_location_is_versioned_and_soil_is_evidence_linked(ffl_db, crop_allocation, users):
    first = _location(ffl_db, crop_allocation, users.manager.id)
    second = repository.create_operating_unit_location(
        ffl_db, crop_allocation.operating_unit_id, "Uttar Pradesh", "Meerut", "IN-UP-MEERUT",
        users.manager.id, "2026-08-01T07:00:00Z", village_name="Verified Pilot Village", pincode="250001",
    )
    artifact = _artifact(ffl_db, users.manager.id)
    baseline = repository.create_soil_baseline(
        ffl_db, crop_allocation.operating_unit_id, "2026-07-15", "Fortune Lab",
        {"pH": {"value": 7.2, "unit": "pH"}, "EC": {"value": 0.41, "unit": "dS/m"}},
        artifact.id, users.manager.id, depth_cm_start=0, depth_cm_end=15,
    )

    assert repository.get_operating_unit_location(ffl_db, first.id).status == "superseded"
    assert repository.get_active_operating_unit_location(ffl_db, crop_allocation.operating_unit_id) == second
    assert repository.list_soil_baselines(ffl_db, crop_allocation.operating_unit_id) == [baseline]
    with pytest.raises(ValueError, match="evidence artifact"):
        repository.create_soil_baseline(
            ffl_db, crop_allocation.operating_unit_id, "2026-07-15", "Fortune Lab",
            {"pH": {"value": 7.2, "unit": "pH"}}, "missing", users.manager.id,
        )
    with pytest.raises(ValueError, match="finite"):
        repository.create_soil_baseline(
            ffl_db, crop_allocation.operating_unit_id, "2026-07-15", "Fortune Lab",
            {"pH": {"value": float("nan"), "unit": "pH"}}, artifact.id, users.manager.id,
        )


def test_brief_renders_only_effective_approved_district_context(ffl_db, crop_allocation, users):
    _location(ffl_db, crop_allocation, users.manager.id)
    artifact = _artifact(ffl_db, users.manager.id)
    repository.create_soil_baseline(
        ffl_db, crop_allocation.operating_unit_id, "2026-07-31", "Fortune Lab",
        {"pH": {"value": 7.2, "unit": "pH"}}, artifact.id, users.manager.id,
    )
    source = _imd(ffl_db, users.manager.id, enabled=True)
    run = repository.create_source_run(
        ffl_db, source.id, coverage={"district": "Meerut"}, status="succeeded",
        rows_received=1, rows_accepted=1, mapping_version="district-v1", fetched_at="2026-08-01T07:00:00Z",
    )
    repository.create_regional_signal(
        ffl_db, source.id, "imd-warning-1", "IN-UP-MEERUT", "thunderstorm_warning",
        "2026-08-01T06:00:00Z", {"level": "watch"}, {"district": "Meerut"}, "forecast",
        source_run_id=run.id, source_url="https://mausam.imd.gov.in/example", valid_from="2026-08-01T06:00:00Z",
        valid_to="2026-08-01T20:00:00Z", resolution="district", freshness_target_hours=12,
    )

    result = morning_brief.morning_brief(ffl_db, crop_allocation.operating_unit_id, NOW)

    weather = result["context"]["district_weather"]
    assert weather["effective_signal_count"] == 1
    assert weather["signals"][0]["provenance"]["source_key"] == "imd-weather"
    alert = next(item for item in result["attention"] if item["code"] == "regional_thunderstorm_warning")
    assert alert["priority"] == "high"
    assert "proof" in alert["detail"]


def test_brief_marks_disabled_imd_as_access_pending(ffl_db, crop_allocation, users):
    _location(ffl_db, crop_allocation, users.manager.id)
    _imd(ffl_db, users.manager.id, enabled=False)

    result = morning_brief.morning_brief(ffl_db, crop_allocation.operating_unit_id, NOW)

    assert result["context"]["district_weather"]["status"] == "access_pending"
    assert any(item["code"] == "imd_access_pending" for item in result["attention"])


def test_context_api_supports_setup_and_returns_the_safe_brief(tmp_path):
    with TestClient(create_app(str(tmp_path / "context.db"))) as client:
        conn = client.app.state.conn
        manager = repository.create_person(conn, "Manager", "farm_manager")
        unit = repository.create_operating_unit(conn, "Fortune Pilot")
        evidence = _artifact(conn, manager.id)

        location = client.put("/api/v1/operating-units/{0}/location".format(unit.id), json={
            "state_name": "Uttar Pradesh",
            "district_name": "Meerut",
            "district_context_key": "IN-UP-MEERUT",
            "verified_by_person_id": manager.id,
            "verified_at": "2026-08-01T07:00:00Z",
            "village_name": "Pilot Village",
            "pincode": "250001",
        })
        soil = client.post("/api/v1/operating-units/{0}/soil-baselines".format(unit.id), json={
            "sampled_on": "2026-07-31",
            "lab_name": "Fortune Lab",
            "measurements": {"pH": {"value": 7.2, "unit": "pH"}},
            "evidence_artifact_id": evidence.id,
            "reviewed_by_person_id": manager.id,
        })
        brief = client.get("/api/v1/operating-units/{0}/morning-brief?as_of=2026-08-01T08:00:00Z".format(unit.id))

        assert location.status_code == 201
        assert soil.status_code == 201
        assert brief.status_code == 200
        assert brief.json()["context"]["location"]["district_context_key"] == "IN-UP-MEERUT"
        assert brief.json()["context"]["soil"]["measurement_count"] == 1
