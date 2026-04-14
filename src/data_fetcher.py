"""Orchestrator: fetches satellite data, runs analysis, stores results."""

import logging
import math
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

from config.settings import (
    AGGREGATION_INTERVAL,
    DEFAULT_LOOKBACK_DAYS,
    IMAGE_SIZE,
    IMAGES_DIR,
    MAX_CLOUD_COVER,
    SentinelHubConfig,
)
from db.repository import (
    get_observations,
    get_readings,
    insert_alert,
    insert_fetch_log,
    upsert_reading,
    upsert_risk_assessment,
    upsert_imagery,
)
from src.anomaly_detector import detect_anomalies
from src.auth import TokenManager
from src.evalscripts import IMAGERY_EVALSCRIPTS, STATISTICAL_EVALSCRIPTS
from src.geometry import get_bbox
from src.indices import ALL_INDEX_NAMES
from src.models import FieldPolygon, ImageryRecord, IndexReading
from src.risk_scorer import score_risk
from src.sentinel_client import SentinelClient

logger = logging.getLogger(__name__)


def _safe_float(value) -> float | None:
    """Convert API value to float, returning None for NaN/invalid."""
    if value is None:
        return None
    try:
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (ValueError, TypeError):
        return None


def fetch_and_analyze(
    conn: sqlite3.Connection,
    field: FieldPolygon,
    config: SentinelHubConfig,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> dict:
    """Run the full data pipeline for a field.

    1. Authenticate
    2. Fetch statistical time series for all indices
    3. Fetch latest imagery
    4. Run anomaly detection
    5. Compute risk scores
    6. Store everything

    Returns a summary dict with counts.
    """
    start_time = time.time()
    date_to = datetime.utcnow().strftime("%Y-%m-%d")
    date_from = (datetime.utcnow() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

    token_mgr = TokenManager(config)
    client = SentinelClient(token_mgr, config.base_url)

    summary = {
        "readings_stored": 0,
        "alerts_generated": 0,
        "images_saved": 0,
        "cropsar_used": False,
        "errors": [],
    }

    # --- Try CropSAR for cloud-free NDVI first ---
    try:
        _try_cropsar(conn, field, config, date_from, date_to, summary)
    except Exception as exc:
        logger.info("CropSAR not available, using Sentinel Hub only: %s", exc)

    # --- Fetch statistics for all indices via Sentinel Hub ---
    for index_name in ALL_INDEX_NAMES:
        # Skip NDVI if CropSAR already provided it
        if index_name == "NDVI" and summary["cropsar_used"]:
            continue
        try:
            _fetch_index_statistics(
                conn, client, field, index_name, date_from, date_to, summary,
            )
        except Exception as exc:
            logger.error("Failed to fetch %s: %s", index_name, exc)
            summary["errors"].append(f"{index_name}: {exc}")

    # --- Fetch imagery ---
    try:
        _fetch_imagery(conn, client, field, date_from, date_to, summary)
    except Exception as exc:
        logger.error("Failed to fetch imagery: %s", exc)
        summary["errors"].append(f"imagery: {exc}")

    # --- Run anomaly detection ---
    for index_name in ALL_INDEX_NAMES:
        try:
            readings = get_readings(conn, field.field_id, index_name=index_name)
            alerts = detect_anomalies(readings, field.field_id, index_name)
            for alert in alerts:
                insert_alert(conn, alert)
                summary["alerts_generated"] += 1
        except Exception as exc:
            logger.error("Anomaly detection failed for %s: %s", index_name, exc)

    # --- Compute risk score ---
    try:
        _compute_risk(conn, field)
    except Exception as exc:
        logger.error("Risk scoring failed: %s", exc)

    # --- Log fetch ---
    duration = time.time() - start_time
    status = "success" if not summary["errors"] else "partial"
    insert_fetch_log(
        conn, field.field_id, "full_sync", date_from, date_to,
        status=status,
        records_stored=summary["readings_stored"],
        duration_secs=round(duration, 2),
        error_message="; ".join(summary["errors"]) if summary["errors"] else None,
    )

    logger.info(
        "Fetch complete: %d readings, %d alerts, %d images in %.1fs",
        summary["readings_stored"], summary["alerts_generated"],
        summary["images_saved"], duration,
    )
    return summary


def _fetch_index_statistics(
    conn: sqlite3.Connection,
    client: SentinelClient,
    field: FieldPolygon,
    index_name: str,
    date_from: str,
    date_to: str,
    summary: dict,
) -> None:
    """Fetch and store statistical time series for one index."""
    evalscript_fn = STATISTICAL_EVALSCRIPTS.get(index_name)
    if evalscript_fn is None:
        return

    intervals = client.fetch_statistics(
        field.polygon_geojson,
        date_from, date_to,
        evalscript_fn(),
        aggregation_interval=AGGREGATION_INTERVAL,
        max_cloud_cover=MAX_CLOUD_COVER,
    )

    output_key = index_name.lower()

    for interval_data in intervals:
        interval = interval_data.get("interval", {})
        reading_date = interval.get("from", "")[:10]
        outputs = interval_data.get("outputs", {})
        index_output = outputs.get(output_key, {})
        bands = index_output.get("bands", {})

        # The Statistical API returns bands as B0, B1, etc.
        b0 = bands.get("B0", {})
        stats = b0.get("stats", {})

        sample_count = stats.get("sampleCount", 0)
        if sample_count == 0:
            continue

        reading = IndexReading(
            field_id=field.field_id,
            index_name=index_name,
            reading_date=reading_date,
            mean_value=_safe_float(stats.get("mean")),
            min_value=_safe_float(stats.get("min")),
            max_value=_safe_float(stats.get("max")),
            stdev_value=_safe_float(stats.get("stDev")),
            sample_count=sample_count,
            cloud_cover_pct=None,
        )
        upsert_reading(conn, reading)
        summary["readings_stored"] += 1


def _fetch_imagery(
    conn: sqlite3.Connection,
    client: SentinelClient,
    field: FieldPolygon,
    date_from: str,
    date_to: str,
    summary: dict,
) -> None:
    """Fetch and save satellite imagery for the most recent clear date."""
    # Use coordinates from geojson if direct coordinates are empty (DB-loaded fields)
    coords = field.coordinates
    if not coords and field.polygon_geojson.get("coordinates"):
        coords = [
            (pt[0], pt[1])
            for pt in field.polygon_geojson["coordinates"][0]
        ]
    if not coords:
        logger.warning("No coordinates available for imagery fetch")
        return
    bbox = get_bbox(coords)

    # Use last 15 days for imagery to get something recent
    recent_from = (datetime.utcnow() - timedelta(days=15)).strftime("%Y-%m-%d")

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    for image_type, evalscript_fn in IMAGERY_EVALSCRIPTS.items():
        try:
            img = client.fetch_image(
                bbox, recent_from, date_to,
                evalscript_fn(),
                width=IMAGE_SIZE, height=IMAGE_SIZE,
                max_cloud_cover=MAX_CLOUD_COVER,
            )

            filename = f"{field.field_id}_{date_to}_{image_type}.png"
            filepath = IMAGES_DIR / filename
            img.save(str(filepath))

            record = ImageryRecord(
                field_id=field.field_id,
                image_date=date_to,
                image_type=image_type,
                file_path=str(filepath),
                width_px=img.width,
                height_px=img.height,
            )
            upsert_imagery(conn, record)
            summary["images_saved"] += 1

        except Exception as exc:
            logger.warning("Failed to fetch %s image: %s", image_type, exc)
            summary["errors"].append(f"image_{image_type}: {exc}")


def _compute_risk(conn: sqlite3.Connection, field: FieldPolygon) -> None:
    """Compute and store current risk assessment."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    latest_readings: dict[str, float] = {}

    for index_name in ALL_INDEX_NAMES:
        readings = get_readings(conn, field.field_id, index_name=index_name)
        if readings and readings[-1].mean_value is not None:
            latest_readings[index_name] = readings[-1].mean_value

    if not latest_readings:
        return

    # Check for recent observations (last 14 days)
    obs_from = (datetime.utcnow() - timedelta(days=14)).strftime("%Y-%m-%d")
    recent_obs = get_observations(conn, field.field_id, date_from=obs_from)

    assessment = score_risk(
        latest_readings, field.field_id, today,
        recent_observations=recent_obs if recent_obs else None,
    )
    upsert_risk_assessment(conn, assessment)


def _try_cropsar(
    conn: sqlite3.Connection,
    field: FieldPolygon,
    config: SentinelHubConfig,
    date_from: str,
    date_to: str,
    summary: dict,
) -> None:
    """Try to fetch cloud-free NDVI via CropSAR 2D.

    CropSAR_px fuses Sentinel-1 radar with Sentinel-2 optical data
    to produce gap-free time series. Falls back silently if unavailable.
    """
    from src.cropsar_client import CropSARClient

    client = CropSARClient(config.client_id, config.client_secret)
    if not client.is_available():
        logger.info("CropSAR_px not available on openEO, skipping")
        return

    logger.info("CropSAR_px available -- fetching cloud-free NDVI")
    timeseries = client.fetch_timeseries(
        field.polygon_geojson, date_from, date_to, output_type="NDVI",
    )

    for record in timeseries:
        reading = IndexReading(
            field_id=field.field_id,
            index_name="NDVI",
            reading_date=record["date"],
            mean_value=_safe_float(record.get("mean")),
            min_value=_safe_float(record.get("min")),
            max_value=_safe_float(record.get("max")),
            stdev_value=_safe_float(record.get("stdev")),
            sample_count=record.get("sample_count"),
            cloud_cover_pct=0.0,  # CropSAR is cloud-free
        )
        upsert_reading(conn, reading)
        summary["readings_stored"] += 1

    summary["cropsar_used"] = True
    logger.info("CropSAR provided %d cloud-free NDVI readings", len(timeseries))
