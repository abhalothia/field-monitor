"""Sentinel Hub API client for Statistical, Process, and Catalog endpoints."""

import io
import logging
import time

import requests
from PIL import Image

from src.auth import TokenManager

logger = logging.getLogger(__name__)

_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
_MAX_RETRIES = 3
_BACKOFF_BASE = 2.0


class SentinelClient:
    """Wraps Sentinel Hub Statistical, Process, and Catalog APIs."""

    def __init__(self, token_manager: TokenManager, base_url: str) -> None:
        self._token = token_manager
        self._base_url = base_url.rstrip("/")

    def fetch_statistics(
        self,
        polygon_geojson: dict,
        date_from: str,
        date_to: str,
        evalscript: str,
        aggregation_interval: str = "P5D",
        max_cloud_cover: int = 30,
        resolution: int = 10,
    ) -> list[dict]:
        """Fetch time-series statistics for a polygon.

        Returns a list of interval dicts with stats (mean, min, max, stdev).
        """
        body = {
            "input": {
                "bounds": {
                    "geometry": polygon_geojson,
                    "properties": {
                        "crs": "http://www.opengis.net/def/crs/EPSG/0/4326"
                    },
                },
                "data": [{
                    "type": "sentinel-2-l2a",
                    "dataFilter": {
                        "maxCloudCoverage": max_cloud_cover,
                    },
                }],
            },
            "aggregation": {
                "timeRange": {
                    "from": f"{date_from}T00:00:00Z",
                    "to": f"{date_to}T23:59:59Z",
                },
                "aggregationInterval": {"of": aggregation_interval},
                "evalscript": evalscript,
                "resx": resolution,
                "resy": resolution,
            },
            "calculations": {"default": {}},
        }

        url = f"{self._base_url}/statistics"
        resp = self._post_with_retry(url, body)
        return resp.get("data", [])

    def fetch_image(
        self,
        bbox: list[float],
        date_from: str,
        date_to: str,
        evalscript: str,
        width: int = 512,
        height: int = 512,
        max_cloud_cover: int = 30,
    ) -> Image.Image:
        """Fetch a satellite image for a bounding box.

        Returns a PIL Image.
        """
        body = {
            "input": {
                "bounds": {
                    "bbox": bbox,
                    "properties": {
                        "crs": "http://www.opengis.net/def/crs/EPSG/0/4326"
                    },
                },
                "data": [{
                    "type": "sentinel-2-l2a",
                    "dataFilter": {
                        "timeRange": {
                            "from": f"{date_from}T00:00:00Z",
                            "to": f"{date_to}T23:59:59Z",
                        },
                        "maxCloudCoverage": max_cloud_cover,
                        "mosaickingOrder": "leastCC",
                    },
                }],
            },
            "output": {
                "width": width,
                "height": height,
                "responses": [{
                    "identifier": "default",
                    "format": {"type": "image/png"},
                }],
            },
            "evalscript": evalscript,
        }

        url = f"{self._base_url}/process"
        raw = self._post_with_retry(url, body, parse_json=False)
        return Image.open(io.BytesIO(raw))

    def search_scenes(
        self,
        bbox: list[float],
        date_from: str,
        date_to: str,
        max_cloud_cover: int = 30,
    ) -> list[dict]:
        """Search available Sentinel-2 scenes for an area and date range."""
        body = {
            "bbox": bbox,
            "datetime": f"{date_from}T00:00:00Z/{date_to}T23:59:59Z",
            "collections": ["sentinel-2-l2a"],
            "limit": 100,
            "filter": f"eo:cloud_cover < {max_cloud_cover}",
            "filter-lang": "cql2-text",
        }

        url = f"{self._base_url}/catalog/1.0.0/search"
        resp = self._post_with_retry(url, body)
        return resp.get("features", [])

    def _post_with_retry(
        self,
        url: str,
        body: dict,
        parse_json: bool = True,
    ) -> dict | bytes:
        """POST with exponential backoff retry on transient errors."""
        last_error = None

        for attempt in range(_MAX_RETRIES):
            token = self._token.get_token()
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }

            try:
                resp = requests.post(
                    url, json=body, headers=headers, timeout=120,
                )

                if resp.status_code in _RETRY_STATUS_CODES:
                    wait = _BACKOFF_BASE ** attempt
                    logger.warning(
                        "Sentinel Hub %s returned %d, retrying in %.1fs",
                        url, resp.status_code, wait,
                    )
                    time.sleep(wait)
                    last_error = requests.HTTPError(
                        f"{resp.status_code}: {resp.text[:200]}"
                    )
                    continue

                resp.raise_for_status()

                if parse_json:
                    return resp.json()
                return resp.content

            except requests.ConnectionError as exc:
                last_error = exc
                wait = _BACKOFF_BASE ** attempt
                logger.warning("Connection error, retrying in %.1fs", wait)
                time.sleep(wait)

        raise last_error  # type: ignore[misc]
