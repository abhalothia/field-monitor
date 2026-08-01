from fastapi.testclient import TestClient

from ffl.app import create_app


def test_health_endpoint_reports_ffl_service():
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"service": "ffl-operating-kernel", "status": "ok"}


def test_v1_season_evidence_trials_and_sources_routes_are_mounted_on_the_operating_app():
    client = TestClient(create_app())

    evidence = client.post(
        "/api/v1/evidence", json={"content_base64": "not base64", "media_type": "text/plain"}
    )
    calendar = client.get("/api/v1/allocations/not-a-real-allocation/calendar")
    trial = client.post("/api/v1/trials", json={})
    candidates = client.get("/api/v1/sources/india-candidates")

    assert evidence.status_code == 422
    assert calendar.status_code == 422
    assert trial.status_code == 422
    assert candidates.status_code == 200
