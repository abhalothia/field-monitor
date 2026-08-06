"""Regression tests for named password accounts and their narrow scopes."""

from pathlib import Path

from fastapi.testclient import TestClient

from ffl.app import create_app
from ffl.password_identity import provision_password_identity
from ffl.seed import seed_pilot


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "db" / "postgres" / "0016_agro_password_identities.sql"


def _app(tmp_path):
    app = create_app(
        str(tmp_path / "password-identities.db"), launch_password="shared-bootstrap-only",
        manager_api_token="legacy-manager-token", manager_session_secret="manager-browser-secret",
        manager_session_max_age_seconds=600,
    )
    seed = seed_pilot(app.state.conn)
    app.state.manager_person_id = seed["manager_id"]
    app.state.password_identity_session_clock = lambda: 1_000
    admin = provision_password_identity(
        app.state.conn, actor_person_id=seed["manager_id"], person_id=seed["manager_id"],
        access_role="admin", login_id="farm.admin", temporary_password="correct-horse-identity",
    )
    worker = provision_password_identity(
        app.state.conn, actor_person_id=seed["manager_id"], person_id=seed["operator_id"],
        access_role="field_worker", login_id="field.worker", temporary_password="correct-horse-worker",
    )
    return app, admin, worker


def test_named_password_identity_is_hashed_role_checked_and_opens_only_the_admin_shell(tmp_path):
    app, admin, _worker = _app(tmp_path)
    stored = app.state.conn.execute(
        "SELECT login_id, password_hash, access_role FROM password_identities WHERE id = ?", (admin.identity_id,)
    ).fetchone()
    assert stored["login_id"] == "farm.admin"
    assert stored["access_role"] == "admin"
    assert "correct-horse-identity" not in stored["password_hash"]

    with TestClient(app) as client:
        bad = client.post("/api/v1/identity/login", json={"login_id": "farm.admin", "password": "wrong-password"})
        signed_in = client.post(
            "/api/v1/identity/login",
            json={"login_id": "FARM.ADMIN", "password": "correct-horse-identity"},
        )
        session = client.get("/api/v1/identity/session")
        manager_route = client.get("/api/v1/communications/readiness")

    assert bad.status_code == 401
    assert signed_in.json() == {
        "status": "authenticated", "access_role": "admin", "next_path": "/home", "expires_at": 29_800,
    }
    assert session.json()["person_name"] == "Farm Manager"
    assert session.json()["access_role"] == "admin"
    assert manager_route.status_code == 200


def test_worker_password_login_can_read_only_its_own_empty_work_envelope(tmp_path):
    app, _admin, _worker = _app(tmp_path)

    with TestClient(app) as client:
        signed_in = client.post(
            "/api/v1/identity/login",
            json={"login_id": "field.worker", "password": "correct-horse-worker"},
        )
        own = client.get("/api/v1/my/overview")
        company_board = client.get("/api/v1/portfolio")
        privileged = client.get("/api/v1/communications/readiness")

    assert signed_in.json()["next_path"] == "/field-work"
    assert own.status_code == 200
    assert own.json()["person"] == {"name": "Field Operator", "role": "field_worker"}
    assert own.json()["work"] == [] and own.json()["requests"] == []
    assert company_board.status_code == 401
    assert privileged.status_code == 401


def test_password_admin_can_provision_a_new_farmer_account_without_returning_the_password(tmp_path):
    app, _admin, _worker = _app(tmp_path)

    with TestClient(app) as client:
        assert client.post(
            "/api/v1/identity/login",
            json={"login_id": "farm.admin", "password": "correct-horse-identity"},
        ).status_code == 200
        created = client.post(
            "/api/v1/identities",
            json={
                "access_role": "farmer", "login_id": "ravi.grower",
                "temporary_password": "ravi-safe-password", "person_name": "Ravi Kumar",
                "operational_role": "grower",
            },
        )
        listed = client.get("/api/v1/identities")
        client.post("/api/v1/identity/logout")
        farmer = client.post(
            "/api/v1/identity/login",
            json={"login_id": "ravi.grower", "password": "ravi-safe-password"},
        )

    assert created.status_code == 201
    assert "temporary_password" not in created.text
    assert created.json()["person_name"] == "Ravi Kumar"
    assert [item["login_id"] for item in listed.json()["items"]] == ["farm.admin", "field.worker", "ravi.grower"]
    assert farmer.json()["next_path"] == "/farmer"


def test_password_session_rechecks_role_and_is_invalidated_when_account_is_suspended(tmp_path):
    app, admin, _worker = _app(tmp_path)

    with TestClient(app) as client:
        assert client.post(
            "/api/v1/identity/login",
            json={"login_id": "farm.admin", "password": "correct-horse-identity"},
        ).status_code == 200
        app.state.conn.execute(
            "UPDATE password_identities SET identity_status = 'suspended' WHERE id = ?", (admin.identity_id,)
        )
        app.state.conn.commit()
        session = client.get("/api/v1/identity/session")
        manager = client.get("/api/v1/communications/readiness")

    assert session.status_code == 401
    assert manager.status_code == 401


def test_signed_in_person_can_rotate_their_own_password_and_old_sessions_are_invalidated(tmp_path):
    app, _admin, _worker = _app(tmp_path)

    with TestClient(app) as client:
        assert client.post(
            "/api/v1/identity/login",
            json={"login_id": "farm.admin", "password": "correct-horse-identity"},
        ).status_code == 200
        changed = client.post(
            "/api/v1/identity/password",
            json={"current_password": "correct-horse-identity", "new_password": "replacement-safe-password"},
        )
        client.post("/api/v1/identity/logout")
        old = client.post(
            "/api/v1/identity/login",
            json={"login_id": "farm.admin", "password": "correct-horse-identity"},
        )
        new = client.post(
            "/api/v1/identity/login",
            json={"login_id": "farm.admin", "password": "replacement-safe-password"},
        )

    assert changed.json() == {"status": "password_changed", "expires_at": 29_800}
    assert old.status_code == 401
    assert new.status_code == 200


def test_password_identity_migration_is_private_hashed_and_runtime_only():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS agro_password_identities" in sql
    assert "password_hash TEXT NOT NULL" in sql
    assert "access_role IN ('owner', 'admin', 'field_worker', 'farmer')" in sql
    assert "REVOKE ALL ON TABLE agro_password_identities FROM PUBLIC, anon, authenticated" in sql
    assert "GRANT SELECT, INSERT, UPDATE ON TABLE agro_password_identities TO agro_vc_runtime" in sql
    assert "GRANT DELETE" not in sql
