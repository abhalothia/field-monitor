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
        board_denied = client.get("/api/v1/trackwick/board")
        metrics = client.get("/api/v1/trackwick/metrics", headers={"X-FFL-Manager-Token": "manager-secret"})
        health = client.get("/api/v1/trackwick/health", headers={"X-FFL-Manager-Token": "manager-secret"})
        board = client.get("/api/v1/trackwick/board", headers={"X-FFL-Manager-Token": "manager-secret"})

    assert denied.status_code == 403
    assert board_denied.status_code == 403
    assert metrics.status_code == 200
    assert health.status_code == 200
    assert board.status_code == 200
    assert health.json() == {"source_key": "trackwick-fortune-paddy", "state": "not_configured"}
    assert "api-key" not in repr(metrics.json()).lower()
    assert "customer" not in repr(health.json()).lower()
    assert board.json()["source"] == {"state": "not_configured", "last_synced_at": None}


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


def test_trackwick_cron_refresh_requires_only_the_server_cron_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "cron-secret")
    app = create_app(str(tmp_path / "trackwick-cron.db"))
    with TestClient(app) as client:
        manager = repository.create_person(app.state.conn, "Fortune COO", "operations_lead")
        app.state.manager_person_id = manager.id
        denied = client.post("/api/v1/trackwick/cron-refresh")
        allowed = client.post(
            "/api/v1/trackwick/cron-refresh",
            headers={"Authorization": "Bearer cron-secret"},
        )

    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert allowed.json() == {
        "source_key": "trackwick-fortune-paddy",
        "state": "unavailable",
        "valid_count": 0,
        "quarantined_count": 0,
    }


def test_command_centre_board_is_manager_only_and_literal_safe(tmp_path):
    app = create_app(str(tmp_path / "command-centre-board.db"), manager_api_token="manager-secret")
    with TestClient(app) as client:
        manager = repository.create_person(app.state.conn, "Fortune COO", "operations_lead")
        app.state.manager_person_id = manager.id
        source = repository.create_source_registry(
            app.state.conn, "trackwick-fortune-paddy", "TrackWick", "trackwick",
            "reported context", "partner", manager.id, ["farm_task_context"],
            "v1", "v1", {}, enabled=True,
        )
        now = "2026-08-03T10:00:00+05:30"
        app.state.conn.execute(
            """INSERT INTO trackwick_parties (
                id, source_id, party_kind, provider_identifier, display_name,
                source_fingerprint, mapping_version, data_quality_status,
                first_seen_at, last_seen_at, created_at
            ) VALUES ('route-farmer', ?, 'farmer', 'private-provider-farmer',
                      'Ramesh Kumar', ?, 'v1', 'valid', ?, ?, ?)""",
            (source.id, "a" * 64, now, now, now),
        )
        app.state.conn.execute(
            """INSERT INTO trackwick_tasks (
                id, source_id, provider_task_id, farmer_party_id, task_type, task_status,
                provider_created_at, source_fingerprint, mapping_version,
                data_quality_status, first_seen_at, last_seen_at, created_at
            ) VALUES ('route-task', ?, 'private-provider-task', 'route-farmer',
                      'RAW ACTION SENTINEL 4419', 'pending', ?, ?, 'v1', 'valid', ?, ?, ?)""",
            (source.id, now, "b" * 64, now, now, now),
        )
        app.state.conn.commit()
        denied = client.get("/api/v1/trackwick/command-centre-board")
        allowed = client.get(
            "/api/v1/trackwick/command-centre-board",
            headers={"X-FFL-Manager-Token": "manager-secret"},
        )
        legacy_board = client.get(
            "/api/v1/trackwick/board",
            headers={"X-FFL-Manager-Token": "manager-secret"},
        )

    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert legacy_board.status_code == 200
    serialized = repr([allowed.json(), legacy_board.json()]).lower()
    assert allowed.json()["inbox"][0]["label"] == "TrackWick source work"
    assert "task_type" not in allowed.json()["inbox"][0]
    assert "raw action sentinel 4419" not in serialized
    for forbidden in ("map", "location", "latitude", "longitude", "crm_status", "provider_tag", "field_worker", "registration_status", "pb1", "1718"):
        assert forbidden not in serialized
