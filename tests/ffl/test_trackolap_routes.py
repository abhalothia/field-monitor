from __future__ import annotations

from fastapi.testclient import TestClient

from ffl.app import create_app
from ffl.persistence import repository


def test_metrics_route_does_not_expose_task_urls_or_credentials(tmp_path):
    app = create_app(str(tmp_path / "trackolap-routes.db"), manager_api_token="manager-secret")
    with TestClient(app) as client:
        manager = repository.create_person(app.state.conn, "Fortune COO", "operations_lead")
        app.state.manager_person_id = manager.id

        response = client.get("/api/v1/trackolap/metrics", headers={"X-FFL-Manager-Token": "manager-secret"})

    assert response.status_code == 200
    assert "https://" not in repr(response.json())
    assert "token" not in repr(response.json()).lower()


def test_trackolap_routes_are_manager_only(tmp_path):
    app = create_app(str(tmp_path / "trackolap-auth.db"), manager_api_token="manager-secret")
    with TestClient(app) as client:
        manager = repository.create_person(app.state.conn, "Fortune COO", "operations_lead")
        app.state.manager_person_id = manager.id

        response = client.get("/api/v1/trackolap/health")

    assert response.status_code == 403


def test_refresh_without_reviewed_configuration_is_safe_and_unavailable(tmp_path):
    app = create_app(str(tmp_path / "trackolap-refresh.db"), manager_api_token="manager-secret")
    with TestClient(app) as client:
        manager = repository.create_person(app.state.conn, "Fortune COO", "operations_lead")
        app.state.manager_person_id = manager.id

        response = client.post("/api/v1/trackolap/refresh", headers={"X-FFL-Manager-Token": "manager-secret"})

    assert response.status_code == 200
    assert response.json()["state"] == "unavailable"
    assert "token" not in repr(response.json()).lower()
