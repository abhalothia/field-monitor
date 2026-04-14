"""Tests for Sentinel Hub API client."""

import json
from unittest.mock import MagicMock, patch

import pytest
import responses

from config.settings import SentinelHubConfig
from src.auth import TokenManager
from src.sentinel_client import SentinelClient

BASE_URL = "https://services.sentinel-hub.com/api/v1"
TOKEN_URL = (
    "https://services.sentinel-hub.com/auth/realms/main/"
    "protocol/openid-connect/token"
)

SAMPLE_POLYGON = {
    "type": "Polygon",
    "coordinates": [[[77.81, 28.09], [77.82, 28.09], [77.82, 28.10], [77.81, 28.10], [77.81, 28.09]]],
}

SAMPLE_BBOX = [77.81, 28.09, 77.82, 28.10]


def _make_client() -> SentinelClient:
    token_mgr = MagicMock(spec=TokenManager)
    token_mgr.get_token.return_value = "test-token"
    return SentinelClient(token_mgr, BASE_URL)


class TestFetchStatistics:
    @responses.activate
    def test_returns_interval_data(self):
        stat_response = {
            "data": [
                {
                    "interval": {
                        "from": "2026-01-01T00:00:00Z",
                        "to": "2026-01-05T23:59:59Z",
                    },
                    "outputs": {
                        "ndvi": {
                            "bands": {
                                "B0": {
                                    "stats": {
                                        "mean": 0.65,
                                        "min": 0.3,
                                        "max": 0.85,
                                        "stDev": 0.12,
                                        "sampleCount": 38,
                                    }
                                }
                            }
                        }
                    },
                }
            ]
        }
        responses.add(
            responses.POST, f"{BASE_URL}/statistics",
            json=stat_response, status=200,
        )

        client = _make_client()
        result = client.fetch_statistics(
            SAMPLE_POLYGON, "2026-01-01", "2026-01-31", "//evalscript",
        )

        assert len(result) == 1
        assert "interval" in result[0]
        assert "outputs" in result[0]

    @responses.activate
    def test_sends_correct_request_structure(self):
        responses.add(
            responses.POST, f"{BASE_URL}/statistics",
            json={"data": []}, status=200,
        )

        client = _make_client()
        client.fetch_statistics(
            SAMPLE_POLYGON, "2026-01-01", "2026-03-01", "//script",
            aggregation_interval="P10D",
            max_cloud_cover=20,
        )

        body = json.loads(responses.calls[0].request.body)
        assert body["input"]["bounds"]["geometry"] == SAMPLE_POLYGON
        assert body["aggregation"]["aggregationInterval"]["of"] == "P10D"
        assert body["input"]["data"][0]["dataFilter"]["maxCloudCoverage"] == 20

    @responses.activate
    def test_includes_bearer_token(self):
        responses.add(
            responses.POST, f"{BASE_URL}/statistics",
            json={"data": []}, status=200,
        )

        client = _make_client()
        client.fetch_statistics(SAMPLE_POLYGON, "2026-01-01", "2026-01-31", "//s")

        auth_header = responses.calls[0].request.headers["Authorization"]
        assert auth_header == "Bearer test-token"


class TestFetchImage:
    @responses.activate
    def test_returns_pil_image(self):
        # Create a minimal 1x1 PNG
        from PIL import Image
        import io
        img = Image.new("RGB", (1, 1), (255, 0, 0))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        responses.add(
            responses.POST, f"{BASE_URL}/process",
            body=png_bytes, status=200,
            content_type="image/png",
        )

        client = _make_client()
        result = client.fetch_image(
            SAMPLE_BBOX, "2026-03-20", "2026-03-25", "//evalscript",
        )

        assert isinstance(result, Image.Image)


class TestSearchScenes:
    @responses.activate
    def test_returns_features(self):
        catalog_response = {
            "features": [
                {"id": "scene-1", "properties": {"eo:cloud_cover": 5.2}},
                {"id": "scene-2", "properties": {"eo:cloud_cover": 12.1}},
            ]
        }
        responses.add(
            responses.POST, f"{BASE_URL}/catalog/1.0.0/search",
            json=catalog_response, status=200,
        )

        client = _make_client()
        scenes = client.search_scenes(SAMPLE_BBOX, "2026-01-01", "2026-03-25")

        assert len(scenes) == 2
        assert scenes[0]["id"] == "scene-1"
