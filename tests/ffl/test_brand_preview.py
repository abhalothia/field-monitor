from fastapi.testclient import TestClient

from ffl.app import create_app


def test_public_landing_is_data_free_and_has_absolute_share_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv("FFL_PUBLIC_ORIGIN", "https://pilot.agroceo.co")
    with TestClient(create_app(str(tmp_path / "brand.db"), launch_password="pilot-password")) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "AGRO CEO — Fortune Farms" in response.text
    assert "https://pilot.agroceo.co/brand/agro-ceo-social.png" in response.text
    assert "Open exceptions" not in response.text
    assert "agro_*" not in response.text


def test_brand_assets_and_legacy_favicon_are_public_with_launch_gate_enabled(tmp_path):
    with TestClient(create_app(str(tmp_path / "brand.db"), launch_password="pilot-password")) as client:
        assert client.get("/favicon.svg").headers["content-type"].startswith("image/svg+xml")
        assert client.get("/site.webmanifest").headers["content-type"].startswith("application/manifest+json")
        social_card = client.get("/brand/agro-ceo-social.png")
        assert social_card.headers["content-type"].startswith("image/png")
        assert social_card.content.startswith(b"\x89PNG\r\n\x1a\n")
        assert client.get("/brand/apple-touch-icon.png").content.startswith(b"\x89PNG\r\n\x1a\n")
        assert client.get("/assets/public.css").headers["content-type"].startswith("text/css")
        assert client.get("/assets/not-a-file.txt").status_code == 404
        assert client.get("/favicon.ico", follow_redirects=False).headers["location"] == "/favicon.svg"
        assert client.get("/manager", follow_redirects=False).status_code == 303


def test_public_origin_rejects_paths_and_untrusted_shapes(tmp_path, monkeypatch):
    monkeypatch.setenv("FFL_PUBLIC_ORIGIN", "https://agroceo.co/not-allowed?unexpected=value")
    with TestClient(create_app(str(tmp_path / "brand.db")), raise_server_exceptions=False) as client:
        response = client.get("/")

    assert response.status_code == 500
