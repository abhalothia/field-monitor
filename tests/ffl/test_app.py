from fastapi.testclient import TestClient

from ffl.app import create_app


def test_health_endpoint_reports_ffl_service():
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"service": "ffl-operating-kernel", "status": "ok"}


def test_blank_field_manifest_template_is_an_explicitly_allowed_csv_asset():
    client = TestClient(create_app())

    response = client.get("/assets/first-field-manifest.csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.text.splitlines() == [
        "source_farm_id,source_plot_id,plot_label,area_hectares,record_status,state_name,"
        "district_name,subdistrict_name,village_name,village_lgd_code,pincode,source_recorded_at,"
        "source_record_ref,crop_name,cultivar,season_name,latitude,longitude,boundary_geojson,"
        "location_precision,boundary_evidence_ref"
    ]


def test_v1_operating_routes_are_mounted_on_the_app():
    client = TestClient(create_app())

    evidence = client.post(
        "/api/v1/evidence", json={"content_base64": "not base64", "media_type": "text/plain"}
    )
    calendar = client.get("/api/v1/allocations/not-a-real-allocation/calendar")
    trial = client.post("/api/v1/trials", json={})
    candidates = client.get("/api/v1/sources/india-candidates")
    village_finder = client.get("/api/v1/geography/village-finder")
    up_geography = client.get("/api/v1/geography/uttar-pradesh")
    readiness = client.get("/api/v1/pilot/readiness")
    portfolio = client.get("/api/v1/portfolio")

    assert evidence.status_code == 422
    assert calendar.status_code == 422
    assert trial.status_code == 422
    assert candidates.status_code == 200
    assert village_finder.status_code == 200
    assert village_finder.json()["status"] == "not_imported"
    assert "Uttar Pradesh" not in village_finder.json()["supported_states"]
    assert up_geography.status_code == 200
    assert up_geography.json()["source_key"] == "lgd-up-geography"
    assert up_geography.json()["automation_policy"] == "no CAPTCHA scraping or unattended LGD download"
    assert readiness.status_code == 200
    assert readiness.json()["overall"] == "not_started"
    assert portfolio.status_code == 200
