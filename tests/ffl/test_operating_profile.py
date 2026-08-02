from fastapi.testclient import TestClient
import pytest

from ffl.app import create_app
from ffl.services.operating_profile import (
    normalize_operating_profile,
    operating_profile_from_environment,
)


def test_operating_profile_is_empty_until_a_customer_profile_is_reviewed(tmp_path, monkeypatch):
    monkeypatch.delenv("FFL_OPERATING_PROFILE_JSON", raising=False)
    with TestClient(create_app(str(tmp_path / "profile.db"), operating_profile=None)) as client:
        response = client.get("/api/v1/operating-profile")

    assert response.status_code == 200
    assert response.json() == {
        "configured": False,
        "display_name": "Operating profile not set",
        "website_url": None,
        "coverage_label": None,
        "public_hub_label": None,
        "source_url": None,
        "map_embed_url": None,
    }


def test_operating_profile_exposes_only_reviewed_public_context(tmp_path):
    configured_profile = {
        "display_name": "Example Rice Operations",
        "website_url": "https://example.test",
        "coverage_label": "Western Uttar Pradesh",
        "public_hub_label": "Dadri public hub",
        "source_url": "https://example.test/operations",
        "map_embed_url": "https://www.openstreetmap.org/export/embed.html?bbox=76.6%2C27.4%2C79.0%2C29.7&layer=mapnik&marker=28.58%2C77.55",
    }
    profile = normalize_operating_profile(configured_profile)
    with TestClient(create_app(str(tmp_path / "profile.db"), operating_profile=configured_profile)) as client:
        response = client.get("/api/v1/operating-profile")

    assert response.status_code == 200
    assert response.json() == profile
    assert "farmer" not in response.text.lower()
    assert "field" not in response.text.lower()


@pytest.mark.parametrize("profile", [
    {"display_name": "Example", "website_url": "http://example.test"},
    {"display_name": "Example", "map_embed_url": "https://example.test/map", "public_hub_label": "Hub"},
    {"display_name": "Example", "map_embed_url": "https://www.openstreetmap.org/export/embed.html?bbox=1&token=secret", "public_hub_label": "Hub"},
    {"display_name": "Example", "map_embed_url": "https://www.openstreetmap.org/export/embed.html?bbox=1"},
    {"display_name": "Example", "unsupported": "nope"},
])
def test_operating_profile_rejects_unreviewed_or_unsafe_display_configuration(profile):
    with pytest.raises(ValueError):
        normalize_operating_profile(profile)


def test_operating_profile_environment_is_strict_json():
    assert operating_profile_from_environment({})["configured"] is False
    with pytest.raises(ValueError, match="valid JSON"):
        operating_profile_from_environment({"FFL_OPERATING_PROFILE_JSON": "not-json"})
