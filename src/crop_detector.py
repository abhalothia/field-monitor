"""ESA WorldCereal crop type detection via openEO.

Uses the WorldCereal Presto foundation model + CatBoost classifier
to produce 10m crop-type maps from Sentinel-1/2 time series.
Runs as an openEO batch job on the CDSE federation backend.
"""

import json
import logging
import tempfile
from pathlib import Path

import numpy as np
import openeo

logger = logging.getLogger(__name__)

OPENEO_FED_URL = "https://openeofed.dataspace.copernicus.eu"

WORLDCEREAL_PROCESS_ID = "worldcereal_crop_type"
WORLDCEREAL_NAMESPACE = (
    "https://raw.githubusercontent.com/WorldCereal/worldcereal-classification/"
    "refs/tags/worldcereal_crop_type_v2.0.3/src/worldcereal/udp/"
    "worldcereal_crop_type.json"
)
DEFAULT_MODEL_URL = (
    "https://s3.waw3-1.cloudferro.com/swift/v1/APEx-benchmarks/"
    "worldcereal_crop_type/test_worldcereal_crop_type_custommodel.onnx"
)

# WorldCereal crop type codes to human-readable labels
CROP_TYPE_LABELS = {
    0: "No crop / other",
    10: "Cereals",
    11: "Wheat",
    12: "Maize",
    13: "Rice",
    14: "Barley",
    15: "Rye",
    16: "Oats",
    17: "Millet",
    18: "Sorghum",
    19: "Other cereals",
    20: "Oil crops",
    21: "Rapeseed",
    22: "Sunflower",
    23: "Soybean",
    30: "Root crops",
    31: "Potatoes",
    32: "Sugar beet",
    40: "Legumes",
    50: "Fruits and vegetables",
    60: "Fibre crops",
    61: "Cotton",
    70: "Sugar crops",
    71: "Sugarcane",
    100: "Cropland (generic)",
}


def get_crop_label(code: int) -> str:
    """Map a WorldCereal crop type code to a human-readable label."""
    return CROP_TYPE_LABELS.get(code, f"Unknown ({code})")


class CropDetector:
    """Detects crop type on a field using ESA WorldCereal via openEO."""

    def __init__(self, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._connection: openeo.Connection | None = None

    def connect(self) -> openeo.Connection:
        if self._connection is not None:
            return self._connection

        conn = openeo.connect(OPENEO_FED_URL)
        conn.authenticate_oidc_client_credentials(
            client_id=self._client_id,
            client_secret=self._client_secret,
        )
        self._connection = conn
        logger.info("Connected to openEO federation at %s", OPENEO_FED_URL)
        return conn

    def detect(
        self,
        polygon_geojson: dict,
        season_start: str,
        season_end: str,
        model_url: str = DEFAULT_MODEL_URL,
        output_dir: str | Path | None = None,
    ) -> dict:
        """Run crop type detection for a field polygon.

        Args:
            polygon_geojson: GeoJSON geometry dict
            season_start: Start of growing season (YYYY-MM-DD)
            season_end: End of growing season (YYYY-MM-DD)
            model_url: URL to the ONNX classification model
            output_dir: Directory to save result GeoTIFF

        Returns:
            Dict with keys: crop_type (str), crop_code (int),
            confidence (float), pixel_counts (dict), geotiff_path (str|None)
        """
        conn = self.connect()

        # Build spatial extent from polygon bbox
        coords = polygon_geojson["coordinates"][0]
        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        spatial_extent = {
            "west": min(lons),
            "south": min(lats),
            "east": max(lons),
            "north": max(lats),
            "crs": "EPSG:4326",
        }

        temporal_extent = [season_start, season_end]

        logger.info(
            "Running WorldCereal crop detection: %s to %s, bbox=%s",
            season_start, season_end,
            [spatial_extent["west"], spatial_extent["south"],
             spatial_extent["east"], spatial_extent["north"]],
        )

        cube = conn.datacube_from_process(
            process_id=WORLDCEREAL_PROCESS_ID,
            namespace=WORLDCEREAL_NAMESPACE,
            temporal_extent=temporal_extent,
            spatial_extent=spatial_extent,
            model_url=model_url,
        )

        job = cube.create_job(
            title=(
                f"WorldCereal crop type {season_start} to {season_end}"
            ),
        )

        logger.info("Batch job created: %s. Waiting for completion...", job.job_id)
        job.start_and_wait()
        logger.info("Batch job completed: %s", job.job_id)

        # Download result
        if output_dir is None:
            output_dir = tempfile.mkdtemp(prefix="worldcereal_")
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        results = job.get_results()
        downloaded = results.download_files(str(output_path))

        # Find the GeoTIFF
        tiff_path = None
        for f in output_path.iterdir():
            if f.suffix.lower() in (".tif", ".tiff"):
                tiff_path = f
                break

        if tiff_path is None:
            logger.warning("No GeoTIFF found in results: %s", list(output_path.iterdir()))
            return {
                "crop_type": "Unknown",
                "crop_code": -1,
                "confidence": 0.0,
                "pixel_counts": {},
                "geotiff_path": None,
            }

        # Analyze the raster
        return _analyze_crop_raster(tiff_path)


def _analyze_crop_raster(tiff_path: Path) -> dict:
    """Read the crop type GeoTIFF and compute majority class."""
    try:
        from PIL import Image
        img = Image.open(str(tiff_path))
        data = np.array(img)
    except Exception:
        # Fallback: try rasterio if available
        try:
            import rasterio
            with rasterio.open(str(tiff_path)) as src:
                data = src.read(1)
        except ImportError:
            logger.error("Cannot read GeoTIFF: install rasterio or ensure Pillow supports it")
            return {
                "crop_type": "Unknown",
                "crop_code": -1,
                "confidence": 0.0,
                "pixel_counts": {},
                "geotiff_path": str(tiff_path),
            }

    # Count pixels per crop type (exclude nodata = 0 or 255)
    unique, counts = np.unique(data, return_counts=True)
    pixel_counts = {}
    total_valid = 0

    for code, count in zip(unique, counts):
        code_int = int(code)
        if code_int in (0, 255) or code_int < 0:
            continue
        label = get_crop_label(code_int)
        pixel_counts[label] = int(count)
        total_valid += int(count)

    if not pixel_counts:
        return {
            "crop_type": "No crop detected",
            "crop_code": 0,
            "confidence": 0.0,
            "pixel_counts": {},
            "geotiff_path": str(tiff_path),
        }

    # Majority class
    majority_label = max(pixel_counts, key=pixel_counts.get)
    majority_count = pixel_counts[majority_label]
    confidence = majority_count / total_valid if total_valid > 0 else 0.0

    # Find the code for the majority label
    majority_code = 0
    for code, label in CROP_TYPE_LABELS.items():
        if label == majority_label:
            majority_code = code
            break

    return {
        "crop_type": majority_label,
        "crop_code": majority_code,
        "confidence": round(confidence, 3),
        "pixel_counts": pixel_counts,
        "geotiff_path": str(tiff_path),
    }
