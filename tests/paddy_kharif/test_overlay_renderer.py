"""Overlay lookup/fallback logic and Folium bounds derivation."""

from db.repository import upsert_field, upsert_imagery
from src.geometry import get_bbox
from src.models import ImageryRecord
from src.paddy_kharif.overlay_renderer import (
    build_image_overlay_kwargs,
    folium_bounds_for_field,
    pick_overlay_for_week,
)


def test_folium_bounds_matches_get_bbox(test_field):
    bounds = folium_bounds_for_field(test_field)
    # [[south, west], [north, east]]
    min_lon, min_lat, max_lon, max_lat = get_bbox(test_field.coordinates)
    assert bounds == [[min_lat, min_lon], [max_lat, max_lon]]


def test_pick_overlay_prefers_exact_ndvi(paddy_db, test_field, tmp_path):
    upsert_field(paddy_db, test_field)
    ndvi = tmp_path / "ndvi.png"
    ndvi.write_bytes(b"ndvi")
    rvi = tmp_path / "rvi.png"
    rvi.write_bytes(b"rvi")
    upsert_imagery(paddy_db, ImageryRecord(
        field_id=test_field.field_id, image_date="2025-08-10",
        image_type="ndvi_overlay", file_path=str(ndvi),
        width_px=256, height_px=256,
    ), season_tag="kharif_2025")
    upsert_imagery(paddy_db, ImageryRecord(
        field_id=test_field.field_id, image_date="2025-08-10",
        image_type="rvi_overlay", file_path=str(rvi),
        width_px=256, height_px=256,
    ), season_tag="kharif_2025")

    chosen = pick_overlay_for_week(paddy_db, test_field.field_id, "2025-08-10")
    assert chosen is not None
    assert chosen.image_type == "ndvi_overlay"


def test_pick_overlay_falls_back_to_rvi_when_ndvi_missing(paddy_db, test_field, tmp_path):
    upsert_field(paddy_db, test_field)
    rvi = tmp_path / "rvi.png"
    rvi.write_bytes(b"rvi")
    upsert_imagery(paddy_db, ImageryRecord(
        field_id=test_field.field_id, image_date="2025-08-10",
        image_type="rvi_overlay", file_path=str(rvi),
        width_px=256, height_px=256,
    ), season_tag="kharif_2025")

    chosen = pick_overlay_for_week(paddy_db, test_field.field_id, "2025-08-10")
    assert chosen is not None
    assert chosen.image_type == "rvi_overlay"


def test_pick_overlay_nearest_within_window(paddy_db, test_field, tmp_path):
    upsert_field(paddy_db, test_field)
    ndvi = tmp_path / "ndvi.png"
    ndvi.write_bytes(b"ndvi")
    upsert_imagery(paddy_db, ImageryRecord(
        field_id=test_field.field_id, image_date="2025-08-07",
        image_type="ndvi_overlay", file_path=str(ndvi),
        width_px=256, height_px=256,
    ), season_tag="kharif_2025")

    # 3 days later; within ±7 day fallback window
    chosen = pick_overlay_for_week(paddy_db, test_field.field_id, "2025-08-10")
    assert chosen is not None
    assert chosen.image_date == "2025-08-07"


def test_build_overlay_kwargs_none_if_png_missing(paddy_db, test_field, tmp_path):
    rec = ImageryRecord(
        field_id=test_field.field_id, image_date="2025-08-10",
        image_type="ndvi_overlay", file_path=str(tmp_path / "does-not-exist.png"),
        width_px=256, height_px=256,
    )
    assert build_image_overlay_kwargs(test_field, rec) is None


def test_build_overlay_kwargs_shape(paddy_db, test_field, tmp_path):
    png = tmp_path / "x.png"
    png.write_bytes(b"\x89PNG")
    rec = ImageryRecord(
        field_id=test_field.field_id, image_date="2025-08-10",
        image_type="ndvi_overlay", file_path=str(png),
        width_px=256, height_px=256,
    )
    kw = build_image_overlay_kwargs(test_field, rec, opacity=0.5)
    assert kw["image"].endswith("x.png")
    assert kw["opacity"] == 0.5
    assert len(kw["bounds"]) == 2
    assert len(kw["bounds"][0]) == 2
