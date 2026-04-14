"""CropSAR 2D integration for cloud-free vegetation index time series.

CropSAR_px fuses Sentinel-1 (radar) and Sentinel-2 (optical) to produce
gap-free NDVI, FAPAR, and FCOVER at 5-day intervals and 10m resolution.

STATUS: CropSAR_px is listed in the CDSE marketplace but is not yet
available as a callable openEO process. This module is ready to activate
once the process is deployed. In the meantime, the main pipeline uses the
Sentinel Hub Statistical API directly.

To check availability, run:
    python -c "from src.cropsar_client import check_availability; check_availability()"
"""

import json
import logging
import tempfile
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

OPENEO_URL = "https://openeo.dataspace.copernicus.eu"
CROPSAR_PROCESS_ID = "CropSAR_px"
CROPSAR_NAMESPACE = "vito"
CROPSAR_OUTPUT_TYPES = ("NDVI", "FAPAR", "FCOVER")


def check_availability(
    client_id: str | None = None,
    client_secret: str | None = None,
) -> bool:
    """Check if CropSAR_px is available on the CDSE openEO backend."""
    import openeo

    if client_id is None or client_secret is None:
        from config.settings import get_sentinel_config
        config = get_sentinel_config()
        client_id = config.client_id
        client_secret = config.client_secret

    conn = openeo.connect(OPENEO_URL)
    conn.authenticate_oidc_client_credentials(
        client_id=client_id,
        client_secret=client_secret,
    )

    for namespace in [CROPSAR_NAMESPACE, "backend", None]:
        try:
            procs = conn.list_processes(namespace=namespace)
            cropsar = [
                p for p in procs
                if "cropsar" in p.get("id", "").lower()
            ]
            if cropsar:
                logger.info(
                    "CropSAR found in namespace '%s': %s",
                    namespace,
                    [p["id"] for p in cropsar],
                )
                print(f"CropSAR available in namespace '{namespace}':")
                for p in cropsar:
                    print(f"  {p['id']}: {p.get('description', '')[:100]}")
                return True
        except Exception:
            continue

    print("CropSAR_px is NOT yet available on CDSE openEO backends.")
    print("The Sentinel Hub Statistical API is used as the primary data source.")
    return False


class CropSARClient:
    """Client for CropSAR 2D cloud-free time series via openEO.

    Will activate once CropSAR_px becomes available on CDSE.
    """

    def __init__(self, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._connection = None

    def connect(self):
        """Establish an authenticated openEO connection."""
        import openeo

        if self._connection is not None:
            return self._connection

        conn = openeo.connect(OPENEO_URL)
        conn.authenticate_oidc_client_credentials(
            client_id=self._client_id,
            client_secret=self._client_secret,
        )
        self._connection = conn
        logger.info("Connected to openEO at %s", OPENEO_URL)
        return conn

    def is_available(self) -> bool:
        """Check if CropSAR_px process is available."""
        try:
            conn = self.connect()
            procs = conn.list_processes(namespace=CROPSAR_NAMESPACE)
            return any(
                p.get("id", "").lower() == "cropsar_px"
                for p in procs
            )
        except Exception:
            return False

    def fetch_timeseries(
        self,
        polygon_geojson: dict,
        date_from: str,
        date_to: str,
        output_type: str = "NDVI",
    ) -> list[dict]:
        """Fetch cloud-free time series using CropSAR_px.

        Returns list of dicts: {date, mean, min, max, stdev, sample_count}
        """
        if output_type not in CROPSAR_OUTPUT_TYPES:
            raise ValueError(
                f"output_type must be one of {CROPSAR_OUTPUT_TYPES}"
            )

        conn = self.connect()

        coords = polygon_geojson["coordinates"][0]
        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        spatial_extent = {
            "west": min(lons), "south": min(lats),
            "east": max(lons), "north": max(lats),
            "crs": "EPSG:4326",
        }

        s2 = conn.load_collection(
            "SENTINEL2_L2A",
            spatial_extent=spatial_extent,
            temporal_extent=[date_from, date_to],
            bands=["B02", "B03", "B04", "B08"],
        )

        cropsar_result = s2.process(
            CROPSAR_PROCESS_ID,
            namespace=CROPSAR_NAMESPACE,
            arguments={"data": s2},
        )

        agg = cropsar_result.aggregate_spatial(
            geometries=polygon_geojson,
            reducer="mean",
        )

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            tmp_path = f.name

        job = agg.execute_batch(
            title=f"CropSAR {output_type} {date_from} to {date_to}",
            out_format="JSON",
        )
        job.get_results().download_file(tmp_path)

        with open(tmp_path) as f:
            raw_data = json.load(f)

        return _parse_timeseries_json(raw_data)


def _parse_timeseries_json(raw_data: dict | list) -> list[dict]:
    """Parse openEO JSON timeseries output into structured records."""
    results = []

    if isinstance(raw_data, dict):
        for date_key, values in raw_data.items():
            date_str = str(date_key)[:10]
            flat_values = _flatten(values)
            if not flat_values:
                continue
            arr = np.array(flat_values, dtype=float)
            arr = arr[np.isfinite(arr)]
            if len(arr) == 0:
                continue
            results.append({
                "date": date_str,
                "mean": float(np.mean(arr)),
                "min": float(np.min(arr)),
                "max": float(np.max(arr)),
                "stdev": float(np.std(arr)) if len(arr) > 1 else 0.0,
                "sample_count": len(arr),
            })

    results.sort(key=lambda x: x["date"])
    return results


def _flatten(obj) -> list[float]:
    """Recursively flatten nested lists/values into a flat list of floats."""
    if isinstance(obj, (int, float)):
        return [float(obj)]
    if isinstance(obj, list):
        flat = []
        for item in obj:
            flat.extend(_flatten(item))
        return flat
    return []
