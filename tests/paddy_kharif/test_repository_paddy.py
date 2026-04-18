"""Tests for repository_paddy: event CRUD, season-scoped queries, overlay lookup."""

from db.repository import upsert_field, upsert_imagery, upsert_reading
from src.models import ImageryRecord, IndexReading
from src.paddy_kharif.models_paddy import PaddyEvent
from src.paddy_kharif.repository_paddy import (
    delete_paddy_events,
    get_calibrated_thresholds,
    get_existing_reading_dates,
    get_overlay,
    get_paddy_events,
    get_season_readings,
    insert_paddy_event,
    list_overlays,
    overlay_exists,
    reading_has_valid_samples,
    upsert_calibrated_thresholds,
)


def test_insert_paddy_event_is_idempotent_and_merges_evidence(paddy_db, test_field):
    upsert_field(paddy_db, test_field)

    ev1 = PaddyEvent(
        field_id=test_field.field_id,
        event_date="2025-07-05",
        event_type="transplanting",
        confidence=0.6,
        evidence={"path": "optical", "lswi": 0.25},
    )
    id1 = insert_paddy_event(paddy_db, ev1)
    assert id1 is not None

    # Duplicate event with higher confidence + extra evidence should merge.
    ev2 = PaddyEvent(
        field_id=test_field.field_id,
        event_date="2025-07-05",
        event_type="transplanting",
        confidence=0.95,
        evidence={"sar_vv_drop_db": -3.1},
    )
    id2 = insert_paddy_event(paddy_db, ev2)
    assert id2 == id1  # same row

    events = get_paddy_events(paddy_db, test_field.field_id)
    assert len(events) == 1
    assert events[0].confidence == 0.95
    assert events[0].evidence["lswi"] == 0.25
    assert events[0].evidence["sar_vv_drop_db"] == -3.1


def test_get_paddy_events_filters_by_type(paddy_db, test_field):
    upsert_field(paddy_db, test_field)
    insert_paddy_event(paddy_db, PaddyEvent(
        field_id=test_field.field_id, event_date="2025-07-05",
        event_type="transplanting", confidence=0.6, evidence={},
    ))
    insert_paddy_event(paddy_db, PaddyEvent(
        field_id=test_field.field_id, event_date="2025-11-10",
        event_type="harvesting", confidence=0.6, evidence={},
    ))
    ts = get_paddy_events(paddy_db, test_field.field_id, event_type="transplanting")
    assert len(ts) == 1 and ts[0].event_type == "transplanting"


def test_delete_paddy_events_removes_only_season(paddy_db, test_field):
    upsert_field(paddy_db, test_field)
    for season in ("kharif_2025", "kharif_2024"):
        insert_paddy_event(paddy_db, PaddyEvent(
            field_id=test_field.field_id, event_date="2025-07-05",
            event_type="transplanting", confidence=0.6, evidence={},
            season_tag=season,
        ))
    removed = delete_paddy_events(paddy_db, test_field.field_id, season_tag="kharif_2025")
    assert removed == 1
    remaining = get_paddy_events(paddy_db, test_field.field_id, season_tag="kharif_2024")
    assert len(remaining) == 1


def test_get_season_readings_is_season_scoped(paddy_db, test_field):
    upsert_field(paddy_db, test_field)
    r_generic = IndexReading(
        field_id=test_field.field_id, index_name="NDVI",
        reading_date="2025-07-01", mean_value=0.5,
        min_value=None, max_value=None, stdev_value=None,
        sample_count=10, cloud_cover_pct=0,
    )
    r_paddy = IndexReading(
        field_id=test_field.field_id, index_name="NDVI",
        reading_date="2025-07-01", mean_value=0.7,
        min_value=None, max_value=None, stdev_value=None,
        sample_count=10, cloud_cover_pct=0,
    )
    upsert_reading(paddy_db, r_generic, season_tag="generic")
    upsert_reading(paddy_db, r_paddy, season_tag="kharif_2025")

    paddy_readings = get_season_readings(
        paddy_db, test_field.field_id, season_tag="kharif_2025",
    )
    assert len(paddy_readings) == 1
    assert paddy_readings[0].mean_value == 0.7


def test_get_existing_reading_dates_and_valid_samples(paddy_db, test_field):
    upsert_field(paddy_db, test_field)
    upsert_reading(paddy_db, IndexReading(
        field_id=test_field.field_id, index_name="NDVI",
        reading_date="2025-07-01", mean_value=0.6,
        min_value=None, max_value=None, stdev_value=None,
        sample_count=42, cloud_cover_pct=0,
    ), season_tag="kharif_2025")
    upsert_reading(paddy_db, IndexReading(
        field_id=test_field.field_id, index_name="NDVI",
        reading_date="2025-07-08", mean_value=None,
        min_value=None, max_value=None, stdev_value=None,
        sample_count=0, cloud_cover_pct=None,
    ), season_tag="kharif_2025")

    dates = get_existing_reading_dates(
        paddy_db, test_field.field_id, "NDVI", season_tag="kharif_2025",
    )
    assert dates == {"2025-07-01", "2025-07-08"}
    # G1: zero-sample row still counts as "tried" so we don't re-fetch
    assert reading_has_valid_samples(
        paddy_db, test_field.field_id, "NDVI", "2025-07-01", "kharif_2025",
    )
    assert not reading_has_valid_samples(
        paddy_db, test_field.field_id, "NDVI", "2025-07-08", "kharif_2025",
    )


def test_overlay_helpers(paddy_db, test_field, tmp_path):
    upsert_field(paddy_db, test_field)
    fake_png = tmp_path / "x.png"
    fake_png.write_bytes(b"\x89PNG")
    upsert_imagery(paddy_db, ImageryRecord(
        field_id=test_field.field_id,
        image_date="2025-08-10",
        image_type="ndvi_overlay",
        file_path=str(fake_png),
        width_px=512, height_px=512,
    ), season_tag="kharif_2025")

    assert overlay_exists(paddy_db, test_field.field_id, "2025-08-10",
                          "ndvi_overlay", "kharif_2025")
    rec = get_overlay(paddy_db, test_field.field_id, "2025-08-10",
                      "ndvi_overlay", "kharif_2025")
    assert rec is not None and rec.image_type == "ndvi_overlay"
    assert len(list_overlays(paddy_db, test_field.field_id, "kharif_2025")) == 1


def test_calibrated_thresholds_roundtrip(paddy_db):
    upsert_calibrated_thresholds(
        paddy_db, scope="test_field", index_name="NDVI",
        healthy=0.62, stress=0.42, severe=0.23,
        sample_count=30, season_tag="kharif_2025",
    )
    got = get_calibrated_thresholds(paddy_db, "test_field", "NDVI", "kharif_2025")
    assert got == (0.62, 0.42, 0.23)
    # Overwrite should not raise
    upsert_calibrated_thresholds(
        paddy_db, scope="test_field", index_name="NDVI",
        healthy=0.60, stress=0.40, severe=0.25,
        sample_count=45, season_tag="kharif_2025",
    )
    got2 = get_calibrated_thresholds(paddy_db, "test_field", "NDVI", "kharif_2025")
    assert got2 == (0.60, 0.40, 0.25)
