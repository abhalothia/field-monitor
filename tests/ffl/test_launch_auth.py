from fastapi.testclient import TestClient

from ffl.app import create_app


def test_launch_password_protects_pilot_surfaces_and_creates_a_signed_session(tmp_path):
    app = create_app(str(tmp_path / "launch.db"), launch_password="test-fortune-password")

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/manager", follow_redirects=False).status_code == 303
        assert client.get("/api/v1/runtime").status_code == 401

        rejected = client.post("/api/v1/launch/login", json={"password": "wrong", "next_path": "https://bad.example"})
        assert rejected.status_code == 401

        accepted = client.post("/api/v1/launch/login", json={"password": "test-fortune-password", "next_path": "/field"})
        assert accepted.status_code == 200
        assert accepted.json() == {"status": "authenticated", "next_path": "/field"}
        assert client.get("/manager").status_code == 200
        assert client.get("/api/v1/runtime").status_code == 404

        assert client.post("/api/v1/launch/logout").json() == {"status": "signed_out"}
        assert client.get("/manager", follow_redirects=False).status_code == 303


def test_launch_gate_stays_off_for_disposable_local_preview_without_a_password(tmp_path):
    with TestClient(create_app(str(tmp_path / "preview.db"), launch_password="")) as client:
        assert client.get("/manager").status_code == 200


def test_vercel_without_launch_password_fails_closed_except_for_the_data_free_share_shell(tmp_path, monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    with TestClient(create_app(str(tmp_path / "preview.db"), launch_password="")) as client:
        assert client.get("/").status_code == 200
        assert client.get("/brand/agro-ceo-social.png").status_code == 200
        assert client.get("/manager").status_code == 503
        assert client.get("/api/v1/runtime").status_code == 503
