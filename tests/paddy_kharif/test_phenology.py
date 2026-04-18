"""Phenology detector tests: synthetic series → expected events."""

from datetime import date, timedelta

from db.repository import upsert_field, upsert_reading
from src.models import IndexReading
from src.paddy_kharif import config as pk_config
from src.paddy_kharif.phenology import detect_events
from src.paddy_kharif.repository_paddy import get_paddy_events


def _store(conn, field_id, index_name, reading_date, value, season="kharif_2025"):
    upsert_reading(conn, IndexReading(
        field_id=field_id, index_name=index_name,
        reading_date=reading_date.isoformat() if isinstance(reading_date, date) else reading_date,
        mean_value=value,
        min_value=None, max_value=None, stdev_value=None,
        sample_count=10, cloud_cover_pct=None,
    ), season_tag=season)


def _weekly(start: date, n: int):
    return [start + timedelta(days=7 * i) for i in range(n)]


def test_transplant_optical_fires_on_xiao_signal(paddy_db, test_field):
    upsert_field(paddy_db, test_field)
    weeks = _weekly(date(2025, 6, 22), 6)
    # LSWI climbs 0.05 → 0.25, NDVI stays low 0.10–0.15 → flooded signature.
    lswi_values = [0.05, 0.08, 0.22, 0.24, 0.26, 0.25]
    ndvi_values = [0.10, 0.12, 0.13, 0.14, 0.15, 0.18]
    for d, l, n in zip(weeks, lswi_values, ndvi_values):
        _store(paddy_db, test_field.field_id, "LSWI", d, l)
        _store(paddy_db, test_field.field_id, "NDVI", d, n)

    detect_events(paddy_db, test_field.field_id)

    events = get_paddy_events(paddy_db, test_field.field_id, event_type="transplanting")
    assert len(events) == 1
    ev = events[0]
    assert ev.confidence >= 0.6
    assert "optical" in (ev.evidence.get("path") or "")


def test_transplant_sar_only_path_fires_without_optical(paddy_db, test_field):
    upsert_field(paddy_db, test_field)

    # Pre-season May baseline (stored under 'generic' season tag).
    baseline_dates = [date(2025, 5, 7), date(2025, 5, 14), date(2025, 5, 21)]
    for d in baseline_dates:
        _store(paddy_db, test_field.field_id, "S1_VV", d, -8.0, season="generic")

    # Big VV drop for 2 consecutive weeks + low RVI = transplant.
    weeks = _weekly(date(2025, 6, 29), 4)
    for d in weeks:
        _store(paddy_db, test_field.field_id, "S1_VV", d, -14.0)
        _store(paddy_db, test_field.field_id, "S1_VH", d, -20.0)
        _store(paddy_db, test_field.field_id, "S1_RVI", d, 0.18)

    detect_events(paddy_db, test_field.field_id)

    events = get_paddy_events(paddy_db, test_field.field_id, event_type="transplanting")
    assert len(events) == 1
    ev = events[0]
    # SAR-only detection sits at 0.7
    assert ev.confidence >= 0.7
    assert ev.evidence.get("path") == "sar"


def test_harvest_optical_peak_drop(paddy_db, test_field):
    upsert_field(paddy_db, test_field)

    # Peak NDVI 0.78 on Oct 10, drop to 0.40 by Oct 31 (21 days, drop 0.38 ≥ 0.25).
    ndvi_series = [
        (date(2025, 10, 3),  0.70),
        (date(2025, 10, 10), 0.78),
        (date(2025, 10, 17), 0.65),
        (date(2025, 10, 24), 0.50),
        (date(2025, 11, 7),  0.40),
    ]
    for d, v in ndvi_series:
        _store(paddy_db, test_field.field_id, "NDVI", d, v)

    detect_events(paddy_db, test_field.field_id)
    events = get_paddy_events(paddy_db, test_field.field_id, event_type="harvesting")
    assert len(events) >= 1
    assert any(ev.evidence.get("path") == "optical" for ev in events)


def test_stress_optical_in_reproductive_window(paddy_db, test_field):
    upsert_field(paddy_db, test_field)

    # Force a transplant around 2025-06-29 so reproductive window =
    # +50..+100 = 2025-08-18 to 2025-10-07.
    for d, l, n in zip(
        _weekly(date(2025, 6, 22), 4),
        [0.06, 0.22, 0.26, 0.24],
        [0.10, 0.13, 0.14, 0.18],
    ):
        _store(paddy_db, test_field.field_id, "LSWI", d, l)
        _store(paddy_db, test_field.field_id, "NDVI", d, n)

    # Healthy ramp then sharp drop inside reproductive window.
    rep_weeks = _weekly(date(2025, 8, 20), 8)
    ndvi_vals = [0.62, 0.66, 0.70, 0.72, 0.35, 0.30, 0.32, 0.34]
    for d, v in zip(rep_weeks, ndvi_vals):
        _store(paddy_db, test_field.field_id, "NDVI", d, v)

    detect_events(paddy_db, test_field.field_id)
    stress = get_paddy_events(paddy_db, test_field.field_id, event_type="stress")
    assert len(stress) >= 1


def test_dual_path_transplant_merges_to_high_confidence(paddy_db, test_field):
    upsert_field(paddy_db, test_field)

    # Optical transplant signal around 2025-07-06.
    for d, l, n in zip(
        _weekly(date(2025, 6, 22), 5),
        [0.06, 0.08, 0.22, 0.26, 0.28],
        [0.10, 0.12, 0.13, 0.14, 0.18],
    ):
        _store(paddy_db, test_field.field_id, "LSWI", d, l)
        _store(paddy_db, test_field.field_id, "NDVI", d, n)

    # SAR transplant signal within ±7 days.
    for d in _weekly(date(2025, 5, 7), 3):
        _store(paddy_db, test_field.field_id, "S1_VV", d, -8.0, season="generic")
    for d in _weekly(date(2025, 6, 29), 3):
        _store(paddy_db, test_field.field_id, "S1_VV", d, -14.0)
        _store(paddy_db, test_field.field_id, "S1_RVI", d, 0.20)

    detect_events(paddy_db, test_field.field_id)
    events = get_paddy_events(paddy_db, test_field.field_id, event_type="transplanting")
    assert len(events) == 1
    assert events[0].confidence >= 0.9
    assert "optical+sar" in events[0].evidence.get("path", "")


def test_no_events_when_series_is_flat(paddy_db, test_field):
    upsert_field(paddy_db, test_field)
    for d in _weekly(date(2025, 6, 22), 20):
        _store(paddy_db, test_field.field_id, "NDVI", d, 0.55)
        _store(paddy_db, test_field.field_id, "LSWI", d, 0.15)
    detect_events(paddy_db, test_field.field_id)
    assert get_paddy_events(paddy_db, test_field.field_id) == []
