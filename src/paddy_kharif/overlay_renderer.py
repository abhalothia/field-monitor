"""Turn stored overlay PNGs into Folium ImageOverlay layers.

The fetcher writes polygon-clipped RGBA PNGs (NDVI in clear weeks, RVI in
monsoon weeks) to `data/overlays/<field>/<YYYY-MM-DD>_<kind>.png` and
registers them in the `imagery` table. This module is the read side: given
a selected week, find the best overlay PNG and produce the kwargs Folium
needs to paint it on the map.

"Best" means: if an NDVI overlay exists for this week, use it; otherwise
fall back to the nearest RVI overlay within ±7 days (monsoon fallback).
If neither exists, return None and the caller should draw the polygon
outline alone.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from src.geometry import get_bbox
from src.paddy_kharif.config import SEASON_TAG
from src.paddy_kharif.repository_paddy import get_overlay, list_overlays


if TYPE_CHECKING:
    from src.models import FieldPolygon, ImageryRecord


logger = logging.getLogger(__name__)


def _polygon_coords(field: "FieldPolygon") -> list[tuple[float, float]]:
    """Pull (lon, lat) coords from the field's stored GeoJSON polygon."""
    geom = field.polygon_geojson or {}
    coords = geom.get("coordinates") or []
    if not coords:
        return field.coordinates or []
    ring = coords[0]
    return [(pt[0], pt[1]) for pt in ring]


def folium_bounds_for_field(field: "FieldPolygon") -> list[list[float]]:
    """Folium wants [[south, west], [north, east]] — lat/lon, not lon/lat."""
    coords = _polygon_coords(field)
    min_lon, min_lat, max_lon, max_lat = get_bbox(coords)
    return [[min_lat, min_lon], [max_lat, max_lon]]


def pick_overlay_for_week(
    conn: sqlite3.Connection,
    field_id: str,
    target_date: str,
    season_tag: str = SEASON_TAG,
    fallback_window_days: int = 7,
) -> "ImageryRecord | None":
    """Return the best overlay to show for the given week.

    Lookup order:
      1. Exact NDVI overlay on `target_date`
      2. Exact RVI overlay on `target_date`
      3. Nearest NDVI overlay within ±fallback_window_days
      4. Nearest RVI overlay within ±fallback_window_days
    """
    exact_ndvi = get_overlay(conn, field_id, target_date, "ndvi_overlay", season_tag)
    if exact_ndvi is not None:
        return exact_ndvi
    exact_rvi = get_overlay(conn, field_id, target_date, "rvi_overlay", season_tag)
    if exact_rvi is not None:
        return exact_rvi

    all_overlays = list_overlays(conn, field_id, season_tag)
    if not all_overlays:
        return None

    target = datetime.strptime(target_date[:10], "%Y-%m-%d").date()
    max_gap = timedelta(days=fallback_window_days)

    def gap(rec: "ImageryRecord") -> timedelta:
        d = datetime.strptime(rec.image_date[:10], "%Y-%m-%d").date()
        return abs(d - target)

    # Prefer NDVI over RVI when gap is equal; among same-type, prefer smaller gap.
    sort_key = lambda rec: (0 if rec.image_type == "ndvi_overlay" else 1, gap(rec))
    candidates = sorted(
        (r for r in all_overlays if gap(r) <= max_gap),
        key=sort_key,
    )
    return candidates[0] if candidates else None


def build_image_overlay_kwargs(
    field: "FieldPolygon",
    overlay: "ImageryRecord",
    opacity: float = 0.75,
) -> dict | None:
    """Build the kwargs dict passed straight into `folium.raster_layers.ImageOverlay`.

    Returns None if the PNG file is missing on disk (e.g. cleaned up) so the
    caller can degrade gracefully to a polygon outline.
    """
    png_path = Path(overlay.file_path)
    if not png_path.exists():
        logger.warning("Overlay PNG missing on disk: %s", png_path)
        return None

    return {
        "image": str(png_path),
        "bounds": folium_bounds_for_field(field),
        "opacity": opacity,
        "name": f"{overlay.image_type} {overlay.image_date}",
        "interactive": False,
        "cross_origin": False,
    }
