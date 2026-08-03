"""Regression coverage for the server-side manager browser boundary."""

from fastapi.testclient import TestClient
from pathlib import Path

from ffl.app import create_app
from ffl.seed import seed_pilot


def _manager_app(tmp_path, **overrides):
    values = {
        "database_path": str(tmp_path / "manager-session.db"),
        "manager_api_token": "legacy-server-token",
        "manager_session_secret": "browser-manager-secret",
        "manager_session_max_age_seconds": 120,
    }
    values.update(overrides)
    app = create_app(**values)
    seed = seed_pilot(app.state.conn)
    app.state.manager_person_id = seed["manager_id"]
    app.state.manager_session_clock = lambda: 1_000
    return app


def test_manager_routes_reject_anonymous_and_bad_manager_secret(tmp_path):
    app = _manager_app(tmp_path)

    with TestClient(app) as client:
        assert client.get("/api/v1/communications/readiness").status_code == 403
        assert client.get("/api/v1/manager-session/status").json() == {"authenticated": False}

        rejected = client.post("/api/v1/manager-session/login", json={"secret": "not-the-secret"})
        assert rejected.status_code == 401
        assert client.get("/api/v1/communications/readiness").status_code == 403


def test_valid_manager_session_unlocks_existing_manager_routes_without_a_browser_token(tmp_path):
    app = _manager_app(tmp_path)

    with TestClient(app) as client:
        response = client.post("/api/v1/manager-session/login", json={"secret": "browser-manager-secret"})
        assert response.status_code == 200
        assert response.json() == {"status": "authenticated", "expires_at": 1120}
        assert "browser-manager-secret" not in response.text
        signed_cookie = client.cookies.get("session")
        assert "browser-manager-secret" not in signed_cookie
        assert app.state.manager_person_id not in signed_cookie

        status_response = client.get("/api/v1/manager-session/status")
        assert status_response.json() == {"authenticated": True, "expires_at": 1120}
        # This route depends on require_manager.  It succeeds solely with the
        # signed HttpOnly session cookie: the browser sends no manager header.
        assert client.get("/api/v1/communications/readiness").status_code == 200
        assert client.get("/api/v1/trackolap/metrics").status_code == 200


def test_tampered_browser_session_never_becomes_manager_authority(tmp_path):
    app = _manager_app(tmp_path)

    with TestClient(app) as client:
        assert client.post("/api/v1/manager-session/login", json={"secret": "browser-manager-secret"}).status_code == 200
        client.cookies.set("session", "not-a-signed-session", domain="testserver.local", path="/")
        assert client.get("/api/v1/communications/readiness").status_code == 403


def test_launch_login_does_not_grant_manager_authority(tmp_path):
    app = _manager_app(tmp_path, launch_password="launch-only-secret")

    with TestClient(app) as client:
        assert client.post("/api/v1/launch/login", json={"password": "launch-only-secret"}).status_code == 200
        assert client.get("/api/v1/communications/readiness").status_code == 403

        assert client.post("/api/v1/manager-session/login", json={"secret": "browser-manager-secret"}).status_code == 200
        assert client.get("/api/v1/communications/readiness").status_code == 200


def test_expired_manager_session_fails_closed_and_is_removed(tmp_path):
    app = _manager_app(tmp_path)

    with TestClient(app) as client:
        assert client.post("/api/v1/manager-session/login", json={"secret": "browser-manager-secret"}).status_code == 200
        app.state.manager_session_clock = lambda: 1120
        assert client.get("/api/v1/communications/readiness").status_code == 403
        assert client.get("/api/v1/manager-session/status").json() == {"authenticated": False}


def test_manager_session_configuration_failure_does_not_create_authority(tmp_path):
    app = _manager_app(tmp_path, manager_session_secret="")

    with TestClient(app) as client:
        unavailable = client.post("/api/v1/manager-session/login", json={"secret": "anything"})
        assert unavailable.status_code == 503
        assert client.get("/api/v1/communications/readiness").status_code == 403


def test_manager_session_logout_clears_only_manager_authority(tmp_path):
    app = _manager_app(tmp_path)

    with TestClient(app) as client:
        assert client.post("/api/v1/manager-session/login", json={"secret": "browser-manager-secret"}).status_code == 200
        assert client.get("/api/v1/communications/readiness").status_code == 200
        assert client.post("/api/v1/manager-session/logout").json() == {"status": "signed_out"}
        assert client.get("/api/v1/communications/readiness").status_code == 403


def test_legacy_server_header_remains_supported_without_a_browser_session(tmp_path):
    app = _manager_app(tmp_path, manager_session_secret="")

    with TestClient(app) as client:
        assert client.get(
            "/api/v1/communications/readiness", headers={"X-FFL-Manager-Token": "legacy-server-token"}
        ).status_code == 200


def test_manager_dashboard_never_embeds_the_manager_bearer_token_boundary():
    manager_assets = Path(__file__).resolve().parents[2] / "ffl" / "static" / "manager"
    rendered = (manager_assets / "index.html").read_text(encoding="utf-8") + (manager_assets / "app.js").read_text(encoding="utf-8")

    assert "X-FFL-Manager-Token" not in rendered
    assert "FFL_MANAGER_API_TOKEN" not in rendered
    assert "managerSessionLoginUrl" in rendered
