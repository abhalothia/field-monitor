"""Season-long orchestrator for paddy kharif data ingestion.

Pulls the weekly time series for one field from June 1 2025 → Jan 15 2026
across three API surfaces, in this order:

  1. CropSAR_px via openEO (cloud-free NDVI, if CDSE has it enabled)
  2. Sentinel-2 L2A Statistical API (NDVI if CropSAR missed it, LSWI,
     NDWI, NDRE) via `SentinelClient.fetch_statistics`
  3. Sentinel-1 GRD Statistical API (VV/VH/RVI) via
     `sar_client.fetch_s1_statistics`
  4. Sentinel-2 Process API for RGBA NDVI overlay PNGs, gated on
     `sampleCount > 0` for that week
  5. Sentinel-1 Process API for RGBA RVI overlay PNGs on weeks where (4)
     was skipped — so the UI always has a tile to show

## Credit conservation

Sentinel Hub bills per HTTP request. The four no-double-pull guards:

  G1: Pre-flight DB diff. Before any HTTP call, we query
      `index_readings` for (field, index, season_tag) and skip indices
      whose weekly grid is already fully populated.
  G2: CropSAR-then-skip. If CropSAR covers NDVI for the season, we tag
      NDVI as covered in the summary and the S2 NDVI Statistical call is
      never made.
  G3: Chunk coalescing. Instead of one Statistical call per missing
      week, we merge contiguous missing ranges into a handful of
      `fetch_statistics(date_from, date_to, P7D)` calls. Sentinel Hub
      returns the whole time series in one response.
  G4: Overlay fetch gated on sampleCount. For a week where the NDVI
      reading has `sample_count == 0`, the PNG would be grey anyway, so
      we don't spend a Process API unit on it. Instead we try the RVI
      SAR overlay for that week (which is always available under cloud).

On a fresh run for one field, the estimated cost is ≈48 requests per
season. On a re-run with a fully-populated DB: **zero** requests.
"""

from __future__ import annotations

import logging
import math
import sqlite3
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from config.settings import IMAGES_DIR, SentinelHubConfig
from db.repository import upsert_imagery, upsert_reading, insert_fetch_log
from src.auth import TokenManager
from src.evalscripts import STATISTICAL_EVALSCRIPTS
from src.models import FieldPolygon, ImageryRecord, IndexReading
from src.paddy_kharif import config as pk_config
from src.paddy_kharif import evalscripts_paddy as ev_paddy
from src.paddy_kharif.phenology import detect_events
from src.paddy_kharif.repository_paddy import (
    get_existing_reading_dates,
    overlay_exists,
    reading_has_valid_samples,
)
from src.paddy_kharif.sar_client import (
    fetch_s1_image_by_geometry,
    fetch_s1_statistics,
    fetch_s2_image_by_geometry,
    parse_s1_intervals,
)
from src.sentinel_client import SentinelClient


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _safe_float(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (ValueError, TypeError):
        return None


def _iso(d: date) -> str:
    return d.isoformat()


def _enumerate_weeks(start: date, end: date, step_days: int) -> list[date]:
    """All weekly snap dates between start and end inclusive, aligned to start."""
    out: list[date] = []
    d = start
    while d <= end:
        out.append(d)
        d += timedelta(days=step_days)
    return out


def _coalesce_missing(
    missing_dates: set[date],
    chunk_days: int = 60,
) -> list[tuple[date, date]]:
    """Collapse a set of missing week-centers into contiguous fetch ranges.

    Sentinel Hub Statistical returns a whole time series for one call, so we
    want as few date windows as possible. Any gap ≤ `chunk_days` is merged
    into the surrounding window.
    """
    if not missing_dates:
        return []
    sorted_dates = sorted(missing_dates)
    ranges: list[tuple[date, date]] = []
    cur_start = sorted_dates[0]
    cur_end = sorted_dates[0]
    for d in sorted_dates[1:]:
        if (d - cur_end).days <= chunk_days:
            cur_end = d
        else:
            ranges.append((cur_start, cur_end))
            cur_start = d
            cur_end = d
    ranges.append((cur_start, cur_end))
    return ranges


def _parse_stat_intervals(
    intervals: list[dict], index_name: str, output_key: str,
) -> list[tuple[str, dict]]:
    """Flatten a single-output Statistical API response.

    Returns (reading_date, stats) pairs; skips intervals with sampleCount 0
    upstream guards will still record an empty week so we don't re-ask.
    """
    out = []
    for iv in intervals:
        reading_date = iv.get("interval", {}).get("from", "")[:10]
        stats = (
            iv.get("outputs", {})
              .get(output_key, {})
              .get("bands", {})
              .get("B0", {})
              .get("stats", {})
        )
        out.append((reading_date, stats))
    return out


def _upsert_zero_reading(
    conn: sqlite3.Connection,
    field_id: str,
    index_name: str,
    reading_date: str,
    season_tag: str,
) -> None:
    """Write a sampleCount=0 row so the pre-flight diff knows we've already
    tried this week and won't request it again."""
    upsert_reading(conn, IndexReading(
        field_id=field_id,
        index_name=index_name,
        reading_date=reading_date,
        mean_value=None, min_value=None, max_value=None,
        stdev_value=None, sample_count=0, cloud_cover_pct=None,
    ), season_tag=season_tag)


def _missing_weeks_for_index(
    conn: sqlite3.Connection,
    field_id: str,
    index_name: str,
    weekly_dates: list[date],
    season_tag: str,
) -> set[date]:
    """Which week-centers are NOT yet in DB for this (field, index)."""
    have = get_existing_reading_dates(conn, field_id, index_name, season_tag)
    return {d for d in weekly_dates if _iso(d) not in have}


# ---------------------------------------------------------------------------
# Optical statistics
# ---------------------------------------------------------------------------

def _fetch_optical_stats(
    conn: sqlite3.Connection,
    client: SentinelClient,
    field: FieldPolygon,
    weekly_dates: list[date],
    season_tag: str,
    skip_indices: set[str],
    summary: dict,
) -> None:
    """G1 + G3 applied for each S2 optical index."""
    for idx in pk_config.OPTICAL_INDICES:
        if idx in skip_indices:
            summary["skipped_covered_by_cropsar"].append(idx)
            continue

        evalscript_fn = STATISTICAL_EVALSCRIPTS.get(idx)
        if idx == "LSWI":
            evalscript_fn = ev_paddy.statistical_lswi
        if evalscript_fn is None:
            logger.warning("No evalscript registered for %s", idx)
            continue

        missing = _missing_weeks_for_index(
            conn, field.field_id, idx, weekly_dates, season_tag,
        )
        if not missing:
            summary["skipped_already_fetched"] += 1
            continue

        output_key = idx.lower()
        for d_from, d_to in _coalesce_missing(missing):
            try:
                intervals = client.fetch_statistics(
                    field.polygon_geojson,
                    _iso(d_from), _iso(d_to),
                    evalscript_fn(),
                    aggregation_interval=pk_config.STATS_INTERVAL,
                    max_cloud_cover=pk_config.MAX_CLOUD_COVER,
                )
                summary["api_requests"] += 1
            except Exception as exc:
                logger.error("%s statistics %s..%s failed: %s",
                             idx, d_from, d_to, exc)
                summary["errors"].append(f"{idx}: {exc}")
                continue

            # Record every interval the server sent back so we don't
            # re-request the same weeks next time.
            for r_date, stats in _parse_stat_intervals(intervals, idx, output_key):
                sample_count = stats.get("sampleCount", 0) or 0
                upsert_reading(conn, IndexReading(
                    field_id=field.field_id,
                    index_name=idx,
                    reading_date=r_date,
                    mean_value=_safe_float(stats.get("mean")),
                    min_value=_safe_float(stats.get("min")),
                    max_value=_safe_float(stats.get("max")),
                    stdev_value=_safe_float(stats.get("stDev")),
                    sample_count=sample_count,
                    cloud_cover_pct=None,
                ), season_tag=season_tag)
                summary["readings_stored"] += 1
            time.sleep(pk_config.REQUEST_THROTTLE_SECS)


# ---------------------------------------------------------------------------
# SAR statistics (VV, VH, RVI in one evalscript)
# ---------------------------------------------------------------------------

def _fetch_sar_stats(
    conn: sqlite3.Connection,
    client: SentinelClient,
    field: FieldPolygon,
    weekly_dates: list[date],
    season_tag: str,
    summary: dict,
) -> None:
    """One evalscript returns VV/VH/RVI so we check all three for missing
    weeks and fetch whichever superset needs filling."""
    missing: set[date] = set()
    for idx in pk_config.SAR_SIGNALS:
        missing |= _missing_weeks_for_index(
            conn, field.field_id, idx, weekly_dates, season_tag,
        )
    if not missing:
        summary["skipped_already_fetched"] += 1
        return

    evalscript = ev_paddy.statistical_s1_vvvh_rvi()

    for d_from, d_to in _coalesce_missing(missing):
        try:
            intervals = fetch_s1_statistics(
                client,
                field.polygon_geojson,
                _iso(d_from), _iso(d_to),
                evalscript,
                aggregation_interval=pk_config.STATS_INTERVAL,
            )
            summary["api_requests"] += 1
        except Exception as exc:
            logger.error("SAR statistics %s..%s failed: %s", d_from, d_to, exc)
            summary["errors"].append(f"SAR: {exc}")
            continue

        for record in parse_s1_intervals(intervals):
            for out_key, idx_name in (
                ("vv_db", "S1_VV"),
                ("vh_db", "S1_VH"),
                ("rvi", "S1_RVI"),
            ):
                stats = record.get(out_key, {})
                upsert_reading(conn, IndexReading(
                    field_id=field.field_id,
                    index_name=idx_name,
                    reading_date=record["date"],
                    mean_value=_safe_float(stats.get("mean")),
                    min_value=_safe_float(stats.get("min")),
                    max_value=_safe_float(stats.get("max")),
                    stdev_value=_safe_float(stats.get("stdev")),
                    sample_count=stats.get("count", 0) or 0,
                    cloud_cover_pct=None,
                ), season_tag=season_tag)
                summary["readings_stored"] += 1
        time.sleep(pk_config.REQUEST_THROTTLE_SECS)


# ---------------------------------------------------------------------------
# Overlay PNGs (G4 — gated on sampleCount)
# ---------------------------------------------------------------------------

def _overlay_dir_for(field_id: str) -> Path:
    d = Path(IMAGES_DIR) / "overlays" / field_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _fetch_week_overlay(
    conn: sqlite3.Connection,
    client: SentinelClient,
    field: FieldPolygon,
    week: date,
    season_tag: str,
    summary: dict,
) -> None:
    """For one weekly snap date, decide which overlay to fetch:
      - NDVI (S2) if that week has any valid S2 samples and no overlay yet
      - RVI (S1) fallback otherwise (cloud-independent)
    """
    iso_week = _iso(week)
    week_from = _iso(week)
    week_to = _iso(week + timedelta(days=pk_config.SLIDER_STEP_DAYS - 1))

    # Guard 1: overlay already in DB -> skip
    if overlay_exists(conn, field.field_id, iso_week, "ndvi_overlay", season_tag):
        return
    if overlay_exists(conn, field.field_id, iso_week, "rvi_overlay", season_tag):
        return

    # Guard 4: NDVI only if sample_count > 0 for that week
    if reading_has_valid_samples(conn, field.field_id, "NDVI", iso_week, season_tag):
        try:
            img = fetch_s2_image_by_geometry(
                client,
                field.polygon_geojson,
                week_from, week_to,
                ev_paddy.imagery_paddy_ndvi_overlay(),
                max_cloud_cover=pk_config.MAX_CLOUD_COVER,
            )
            summary["api_requests"] += 1
            path = _overlay_dir_for(field.field_id) / f"{iso_week}_ndvi.png"
            img.save(str(path))
            upsert_imagery(conn, ImageryRecord(
                field_id=field.field_id,
                image_date=iso_week,
                image_type="ndvi_overlay",
                file_path=str(path),
                width_px=img.width,
                height_px=img.height,
            ), season_tag=season_tag)
            summary["overlays_ndvi"] += 1
            time.sleep(pk_config.REQUEST_THROTTLE_SECS)
            return
        except Exception as exc:
            logger.warning("NDVI overlay fetch failed for %s: %s", iso_week, exc)
            summary["errors"].append(f"ndvi_overlay {iso_week}: {exc}")
            # fall through to SAR fallback

    # SAR fallback: always try an RVI tile if no NDVI possible.
    try:
        img = fetch_s1_image_by_geometry(
            client,
            field.polygon_geojson,
            week_from, week_to,
            ev_paddy.imagery_paddy_rvi_overlay(),
        )
        summary["api_requests"] += 1
        path = _overlay_dir_for(field.field_id) / f"{iso_week}_rvi.png"
        img.save(str(path))
        upsert_imagery(conn, ImageryRecord(
            field_id=field.field_id,
            image_date=iso_week,
            image_type="rvi_overlay",
            file_path=str(path),
            width_px=img.width,
            height_px=img.height,
        ), season_tag=season_tag)
        summary["overlays_rvi"] += 1
        time.sleep(pk_config.REQUEST_THROTTLE_SECS)
    except Exception as exc:
        logger.warning("RVI overlay fetch failed for %s: %s", iso_week, exc)
        summary["errors"].append(f"rvi_overlay {iso_week}: {exc}")


def _fetch_overlays(
    conn: sqlite3.Connection,
    client: SentinelClient,
    field: FieldPolygon,
    weekly_dates: list[date],
    season_tag: str,
    summary: dict,
) -> None:
    for week in weekly_dates:
        _fetch_week_overlay(conn, client, field, week, season_tag, summary)


# ---------------------------------------------------------------------------
# CropSAR opportunistic NDVI (G2)
# ---------------------------------------------------------------------------

def _try_cropsar(
    conn: sqlite3.Connection,
    field: FieldPolygon,
    cfg: SentinelHubConfig,
    season_start: str,
    season_end: str,
    season_tag: str,
    summary: dict,
) -> bool:
    """Returns True if CropSAR successfully covered NDVI for the season."""
    try:
        from src.cropsar_client import CropSARClient
        client = CropSARClient(cfg.client_id, cfg.client_secret)
        if not client.is_available():
            logger.info("CropSAR_px not available on openEO for this field; skip")
            return False
        logger.info("CropSAR_px available; fetching full-season NDVI in one batch")
        records = client.fetch_timeseries(
            field.polygon_geojson, season_start, season_end, output_type="NDVI",
        )
    except Exception as exc:
        logger.info("CropSAR attempt failed (will fall back to S2): %s", exc)
        return False

    for rec in records:
        upsert_reading(conn, IndexReading(
            field_id=field.field_id,
            index_name="NDVI",
            reading_date=rec["date"],
            mean_value=_safe_float(rec.get("mean")),
            min_value=_safe_float(rec.get("min")),
            max_value=_safe_float(rec.get("max")),
            stdev_value=_safe_float(rec.get("stdev")),
            sample_count=rec.get("sample_count") or 1,
            cloud_cover_pct=0.0,
        ), season_tag=season_tag)
        summary["readings_stored"] += 1

    summary["cropsar_used"] = len(records) > 0
    logger.info("CropSAR delivered %d NDVI points", len(records))
    return summary["cropsar_used"]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_kharif_season(
    conn: sqlite3.Connection,
    field: FieldPolygon,
    config: SentinelHubConfig,
    year: int = 2025,
    run_detect: bool = True,
) -> dict:
    """Ingest the full paddy kharif season for one field.

    Idempotent: reruns skip weeks already in DB and make zero API calls if
    everything is already cached.
    """
    if year != 2025:
        raise NotImplementedError(
            "Only kharif_2025 is wired up; add a season config for other years."
        )
    season_tag = pk_config.SEASON_TAG
    season_start = datetime.strptime(pk_config.SEASON_START, "%Y-%m-%d").date()
    season_end = datetime.strptime(pk_config.SEASON_END, "%Y-%m-%d").date()

    weekly_dates = _enumerate_weeks(season_start, season_end, pk_config.SLIDER_STEP_DAYS)

    token_mgr = TokenManager(config)
    client = SentinelClient(token_mgr, config.base_url)

    summary = {
        "field_id": field.field_id,
        "season_tag": season_tag,
        "weeks_planned": len(weekly_dates),
        "readings_stored": 0,
        "overlays_ndvi": 0,
        "overlays_rvi": 0,
        "api_requests": 0,
        "skipped_already_fetched": 0,
        "skipped_covered_by_cropsar": [],
        "cropsar_used": False,
        "errors": [],
    }

    start_time = time.time()

    # G2: CropSAR-first for NDVI
    skip_indices: set[str] = set()
    if _try_cropsar(
        conn, field, config,
        pk_config.SEASON_START, pk_config.SEASON_END, season_tag, summary,
    ):
        skip_indices.add("NDVI")

    # Optical: NDVI (if not covered) + LSWI + NDWI + NDRE
    _fetch_optical_stats(
        conn, client, field, weekly_dates, season_tag, skip_indices, summary,
    )

    # SAR: VV/VH/RVI (monsoon-proof backbone)
    _fetch_sar_stats(conn, client, field, weekly_dates, season_tag, summary)

    # Overlays
    _fetch_overlays(conn, client, field, weekly_dates, season_tag, summary)

    duration = time.time() - start_time
    status = "success" if not summary["errors"] else "partial"
    insert_fetch_log(
        conn, field.field_id, "paddy_kharif",
        pk_config.SEASON_START, pk_config.SEASON_END,
        status=status,
        records_stored=summary["readings_stored"],
        duration_secs=round(duration, 2),
        error_message="; ".join(summary["errors"][:5]) if summary["errors"] else None,
        season_tag=season_tag,
    )

    if run_detect:
        try:
            events = detect_events(conn, field.field_id, season_tag=season_tag)
            summary["events_detected"] = len(events)
        except Exception as exc:
            logger.error("Phenology detection failed for %s: %s", field.field_id, exc)
            summary["errors"].append(f"detect_events: {exc}")

    logger.info(
        "Kharif fetch for %s done: %d API requests, %d readings, "
        "%d NDVI overlays, %d RVI overlays in %.1fs",
        field.field_id, summary["api_requests"], summary["readings_stored"],
        summary["overlays_ndvi"], summary["overlays_rvi"], duration,
    )
    return summary
