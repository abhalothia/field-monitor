from __future__ import annotations

from fastapi.testclient import TestClient

from ffl.app import create_app
from ffl.persistence import repository


def test_trackwick_routes_are_manager_only_and_never_return_connection_details(tmp_path):
    app = create_app(str(tmp_path / "trackwick-routes.db"), manager_api_token="manager-secret")
    with TestClient(app) as client:
        manager = repository.create_person(app.state.conn, "Fortune COO", "operations_lead")
        app.state.manager_person_id = manager.id

        denied = client.get("/api/v1/trackwick/health")
        metrics = client.get("/api/v1/trackwick/metrics", headers={"X-FFL-Manager-Token": "manager-secret"})
        health = client.get("/api/v1/trackwick/health", headers={"X-FFL-Manager-Token": "manager-secret"})

    assert denied.status_code == 403
    assert metrics.status_code == 200
    assert health.status_code == 200
    assert health.json() == {"source_key": "trackwick-fortune-paddy", "state": "not_configured"}
    assert "api-key" not in repr(metrics.json()).lower()
    assert "customer" not in repr(health.json()).lower()


def test_trackwick_refresh_without_server_configuration_is_safe(tmp_path):
    app = create_app(str(tmp_path / "trackwick-refresh.db"), manager_api_token="manager-secret")
    with TestClient(app) as client:
        manager = repository.create_person(app.state.conn, "Fortune COO", "operations_lead")
        app.state.manager_person_id = manager.id

        response = client.post("/api/v1/trackwick/refresh", headers={"X-FFL-Manager-Token": "manager-secret"})

    assert response.status_code == 200
    assert response.json() == {
        "source_key": "trackwick-fortune-paddy",
        "state": "unavailable",
        "valid_count": 0,
        "quarantined_count": 0,
    }
