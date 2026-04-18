"""Sentinel-1 SAR client + polygon-geometry image fetching.

Thin wrappers over the existing SentinelClient that swap the data-collection
block to `sentinel-1-grd` with the processing parameters needed for a
consistent rice time series (fixed orbit direction, IW mode, dual-pol DV,
GAMMA0 ellipsoid).

`fetch_image_by_geometry` is a Process-API variant that uses
`input.bounds.geometry` (polygon-clipped) instead of `input.bounds.bbox`
(rectangle). The overlay PNGs returned this way have transparent pixels
outside the polygon, which is what the Folium ImageOverlay expects.
"""

import io
import logging

from PIL import Image

from src.paddy_kharif import config as pk_config
from src.sentinel_client import SentinelClient


logger = logging.getLogger(__name__)


def _s1_data_block(max_cloud_cover: int | None = None) -> dict:
    """Build the `input.data[0]` block for a Sentinel-1 GRD request.

    `max_cloud_cover` is intentionally ignored for S1 (clouds are irrelevant
    to radar) but kept in the signature so call sites can pass through the
    same kwargs they use for optical.
    """
    return {
        "type": "sentinel-1-grd",
        "dataFilter": {
            "resolution": pk_config.S1_RESOLUTION,
            "acquisitionMode": pk_config.S1_ACQUISITION_MODE,
            "polarization": pk_config.S1_POLARIZATION,
            "orbitDirection": pk_config.S1_ORBIT_DIRECTION,
        },
        "processing": {
            "orthorectify": True,
            "backCoeff": pk_config.S1_BACK_COEFF,
        },
    }


def fetch_s1_statistics(
    client: SentinelClient,
    polygon_geojson: dict,
    date_from: str,
    date_to: str,
    evalscript: str,
    aggregation_interval: str = "P7D",
    resolution: int = 10,
) -> list[dict]:
    """Time-series VV/VH/RVI over a polygon from Sentinel-1 GRD.

    Mirrors SentinelClient.fetch_statistics but hand-builds the request body
    so it can inject the S1 data block. We POST directly via the client's
    retry helper to reuse auth and throttling.
    """
    body = {
        "input": {
            "bounds": {
                "geometry": polygon_geojson,
                "properties": {
                    "crs": "http://www.opengis.net/def/crs/EPSG/0/4326",
                },
            },
            "data": [_s1_data_block()],
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
    url = f"{client._base_url}/statistics"
    resp = client._post_with_retry(url, body)
    return resp.get("data", [])


def fetch_s1_image_by_geometry(
    client: SentinelClient,
    polygon_geojson: dict,
    date_from: str,
    date_to: str,
    evalscript: str,
    width: int = 512,
    height: int = 512,
) -> Image.Image:
    """Render an S1-derived RGBA overlay PNG clipped to the polygon."""
    body = {
        "input": {
            "bounds": {
                "geometry": polygon_geojson,
                "properties": {
                    "crs": "http://www.opengis.net/def/crs/EPSG/0/4326",
                },
            },
            "data": [{
                **_s1_data_block(),
                "dataFilter": {
                    **_s1_data_block()["dataFilter"],
                    "timeRange": {
                        "from": f"{date_from}T00:00:00Z",
                        "to": f"{date_to}T23:59:59Z",
                    },
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
    url = f"{client._base_url}/process"
    raw = client._post_with_retry(url, body, parse_json=False)
    return Image.open(io.BytesIO(raw))


def fetch_s2_image_by_geometry(
    client: SentinelClient,
    polygon_geojson: dict,
    date_from: str,
    date_to: str,
    evalscript: str,
    width: int = 512,
    height: int = 512,
    max_cloud_cover: int = 80,
) -> Image.Image:
    """Render an S2-derived RGBA overlay PNG clipped to the polygon.

    The existing SentinelClient.fetch_image uses bbox; for Folium overlays we
    want the geometry-clipped variant so pixels outside the polygon are
    transparent.
    """
    body = {
        "input": {
            "bounds": {
                "geometry": polygon_geojson,
                "properties": {
                    "crs": "http://www.opengis.net/def/crs/EPSG/0/4326",
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
    url = f"{client._base_url}/process"
    raw = client._post_with_retry(url, body, parse_json=False)
    return Image.open(io.BytesIO(raw))


def parse_s1_intervals(intervals: list[dict]) -> list[dict]:
    """Flatten the Statistical API response for the three S1 outputs.

    Returns a list of dicts keyed by ISO date:
        {"date": "YYYY-MM-DD", "vv_db": {mean,min,max,stdev,count},
         "vh_db": {...}, "rvi": {...}}
    Intervals where sampleCount==0 for all three outputs are skipped.
    """
    out = []
    for interval in intervals:
        date_str = interval.get("interval", {}).get("from", "")[:10]
        outputs = interval.get("outputs", {})
        record: dict = {"date": date_str}
        non_empty = False
        for key in ("vv_db", "vh_db", "rvi"):
            bands = outputs.get(key, {}).get("bands", {})
            stats = bands.get("B0", {}).get("stats", {})
            count = stats.get("sampleCount", 0)
            if count:
                non_empty = True
            record[key] = {
                "mean": stats.get("mean"),
                "min": stats.get("min"),
                "max": stats.get("max"),
                "stdev": stats.get("stDev"),
                "count": count,
            }
        if non_empty:
            out.append(record)
    return out
