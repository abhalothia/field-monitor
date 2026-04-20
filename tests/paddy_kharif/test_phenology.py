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


def test_stress_suppressed_in_preharvest_ripening(paddy_db, test_field):
    """Ripening NDVI decline must not fire a stress event.

    Scenario replays the real plot_104902 curve: healthy transplant in late
    June, full canopy through September, peak NDVI early October, harvest
    early November. The 21-day ripening tail used to trip trend_decline on
    NDRE; after the fix, the harvest-aware gate should keep it quiet.
    """
    upsert_field(paddy_db, test_field)

    # Transplant: Xiao signal around 2025-06-29.
    for d, l, n in zip(
        _weekly(date(2025, 6, 22), 4),
        [0.08, 0.22, 0.26, 0.24],
        [0.10, 0.13, 0.14, 0.18],
    ):
        _store(paddy_db, test_field.field_id, "LSWI", d, l)
        _store(paddy_db, test_field.field_id, "NDVI", d, n)

    # Vegetative -> reproductive -> ripening NDVI, peak Oct 5 then drop.
    rep_ndvi = [
        (date(2025, 7, 27), 0.32),
        (date(2025, 8, 10), 0.55),
        (date(2025, 8, 24), 0.68),
        (date(2025, 9, 7),  0.78),
        (date(2025, 9, 14), 0.82),
        (date(2025, 9, 21), 0.80),
        (date(2025, 9, 28), 0.78),
        (date(2025, 10, 5), 0.76),  # peak
        (date(2025, 10, 12), 0.56),
        (date(2025, 10, 19), 0.32),
        (date(2025, 11, 2), 0.09),  # harvested
    ]
    for d, v in rep_ndvi:
        _store(paddy_db, test_field.field_id, "NDVI", d, v)

    # Same ripening pattern for NDRE (which is what actually tripped the
    # detector on the real plot).
    rep_ndre = [
        (date(2025, 8, 24), 0.28),
        (date(2025, 9, 7),  0.34),
        (date(2025, 9, 14), 0.36),
        (date(2025, 9, 21), 0.35),
        (date(2025, 9, 28), 0.34),
        (date(2025, 10, 5), 0.33),
        (date(2025, 10, 12), 0.31),
    ]
    for d, v in rep_ndre:
        _store(paddy_db, test_field.field_id, "NDRE", d, v)

    detect_events(paddy_db, test_field.field_id)

    # Harvest must still be detected (the fix must not suppress it).
    harvest = get_paddy_events(paddy_db, test_field.field_id, event_type="harvesting")
    assert len(harvest) >= 1, "harvest detection regressed"

    # But no stress: ripening is physiology, not stress.
    stress = get_paddy_events(paddy_db, test_field.field_id, event_type="stress")
    assert stress == [], (
        f"ripening curve produced a spurious stress event: "
        f"{[(e.event_date, e.evidence) for e in stress]}"
    )


def test_stress_trend_decline_requires_current_below_healthy(paddy_db, test_field):
    """trend_decline must not fire while the current reading is still healthy.

    Constructs a series where NDRE declines monotonically but stays above
    the healthy floor (0.30). The old detector would emit a medium-severity
    stress event via the forward-projection; the new gate suppresses it.
    """
    upsert_field(paddy_db, test_field)

    # Transplant late June so reproductive window ~Aug 18 - Oct 7.
    for d, l, n in zip(
        _weekly(date(2025, 6, 22), 4),
        [0.08, 0.22, 0.26, 0.24],
        [0.10, 0.13, 0.14, 0.18],
    ):
        _store(paddy_db, test_field.field_id, "LSWI", d, l)
        _store(paddy_db, test_field.field_id, "NDVI", d, n)

    # NDRE inside the reproductive window, healthy but slowly declining.
    for d, v in zip(
        _weekly(date(2025, 8, 20), 6),
        [0.50, 0.48, 0.45, 0.42, 0.39, 0.36],
    ):
        _store(paddy_db, test_field.field_id, "NDRE", d, v)
    # NDVI stays flat / healthy so no harvest gate kicks in either.
    for d, v in zip(
        _weekly(date(2025, 8, 20), 6),
        [0.48, 0.48, 0.48, 0.48, 0.48, 0.48],
    ):
        _store(paddy_db, test_field.field_id, "NDVI", d, v)

    detect_events(paddy_db, test_field.field_id)

    stress = get_paddy_events(paddy_db, test_field.field_id, event_type="stress")
    # All NDRE readings are > 0.30 (healthy) — trend_decline must stay quiet.
    trend_events = [s for s in stress if s.evidence.get("rule") == "trend_decline"]
    assert trend_events == [], (
        f"trend_decline fired while current > healthy: "
        f"{[(e.event_date, e.evidence) for e in trend_events]}"
    )


def test_stress_evidence_uses_projected_not_baseline_for_trend_decline(paddy_db, test_field):
    """trend_decline evidence must carry `projected`, not `baseline`.

    The AnomalyAlert.baseline_value field stores the *forward projection*
    for trend_decline alerts — labeling it `baseline` in the evidence dict
    misleads anyone reading the event.
    """
    upsert_field(paddy_db, test_field)

    # Transplant so reproductive window covers the stress signal below.
    for d, l, n in zip(
        _weekly(date(2025, 6, 22), 4),
        [0.08, 0.22, 0.26, 0.24],
        [0.10, 0.13, 0.14, 0.18],
    ):
        _store(paddy_db, test_field.field_id, "LSWI", d, l)
        _store(paddy_db, test_field.field_id, "NDVI", d, n)

    # NDVI drops from healthy to below stress floor inside reproductive
    # window -- triggers both below_threshold AND trend_decline.
    for d, v in zip(
        _weekly(date(2025, 8, 20), 7),
        [0.62, 0.55, 0.48, 0.38, 0.32, 0.28, 0.24],
    ):
        _store(paddy_db, test_field.field_id, "NDVI", d, v)

    detect_events(paddy_db, test_field.field_id)

    stress = get_paddy_events(paddy_db, test_field.field_id, event_type="stress")
    trend = [s for s in stress if s.evidence.get("rule") == "trend_decline"]
    assert len(trend) >= 1, "expected at least one trend_decline event"
    for ev in trend:
        # trend_decline must expose the forward projection under the key
        # `projected`; the legacy `baseline` name for it was misleading.
        # (Note: `baseline` may still appear in merged evidence when a
        # below_threshold alert contributes it — that one is a real
        # healthy-threshold baseline, not a projection.)
        assert "projected" in ev.evidence, (
            f"trend_decline evidence missing `projected`: {ev.evidence}"
        )


def test_harvest_gradual_senescence_path(paddy_db, test_field):
    """PB1 with a gradual NDVI decline still gets a harvest event.

    Scenario: early-transplant plot that peaks in late August and declines
    slowly through October, finally hitting near-zero stubble in early
    November. The sharp-drop rule never fires (each 21-day drop is < 0.25),
    but the peak-to-stubble rule catches it.
    """
    upsert_field(paddy_db, test_field)

    # Transplant around 2025-06-22 so rep window ~ Aug 11 - Sep 30.
    for d, l, n in zip(
        _weekly(date(2025, 6, 15), 4),
        [0.08, 0.22, 0.26, 0.24],
        [0.10, 0.13, 0.14, 0.18],
    ):
        _store(paddy_db, test_field.field_id, "LSWI", d, l)
        _store(paddy_db, test_field.field_id, "NDVI", d, n)

    # Gradual ramp, peak Aug 31, slow decline to stubble by Nov 9.
    ndvi_series = [
        (date(2025, 7, 20), 0.30),
        (date(2025, 8, 3),  0.50),
        (date(2025, 8, 17), 0.70),
        (date(2025, 8, 31), 0.77),  # peak
        (date(2025, 9, 7),  0.76),
        (date(2025, 10, 5), 0.53),
        (date(2025, 10, 12), 0.45),
        (date(2025, 10, 19), 0.34),
        (date(2025, 11, 2), 0.39),
        (date(2025, 11, 9), 0.10),  # stubble
    ]
    for d, v in ndvi_series:
        _store(paddy_db, test_field.field_id, "NDVI", d, v)

    detect_events(paddy_db, test_field.field_id)

    harvest = get_paddy_events(paddy_db, test_field.field_id, event_type="harvesting")
    assert len(harvest) == 1, (
        f"expected one harvest event, got {len(harvest)}: "
        f"{[(e.event_date, e.evidence) for e in harvest]}"
    )
    ev = harvest[0]
    # Either path is acceptable; verify the stubble rule specifically.
    if ev.evidence.get("rule") == "ndvi_peak_to_stubble":
        assert ev.evidence.get("stubble_ndvi", 1.0) < 0.20

    # No stress should be emitted on the ripening tail.
    stress = get_paddy_events(paddy_db, test_field.field_id, event_type="stress")
    assert stress == [], (
        f"gradual ripening curve produced spurious stress events: "
        f"{[(e.event_date, e.evidence) for e in stress]}"
    )


def test_stress_sudden_drop_requires_current_below_healthy(paddy_db, test_field):
    """sudden_drop on a still-healthy reading must not be classified as stress.

    Rolling z-score fires on small-variance baselines even when the current
    reading is well above the healthy floor. For NDRE with healthy=0.30,
    a reading of 0.58 is healthy — any z-score alert on that reading is
    measurement noise, not a real stress signal.
    """
    upsert_field(paddy_db, test_field)

    for d, l, n in zip(
        _weekly(date(2025, 6, 22), 4),
        [0.08, 0.22, 0.26, 0.24],
        [0.10, 0.13, 0.14, 0.18],
    ):
        _store(paddy_db, test_field.field_id, "LSWI", d, l)
        _store(paddy_db, test_field.field_id, "NDVI", d, n)

    # NDRE series: very stable ~0.65 with a single "dip" to 0.58 that's
    # still well above the healthy floor (0.30). Tight std -> large z,
    # but absolute value is fine -> must NOT fire stress.
    for d, v in zip(
        _weekly(date(2025, 8, 20), 8),
        [0.65, 0.66, 0.65, 0.67, 0.66, 0.65, 0.66, 0.58],
    ):
        _store(paddy_db, test_field.field_id, "NDRE", d, v)
    # Flat healthy NDVI so no harvest window kicks in.
    for d, v in zip(
        _weekly(date(2025, 8, 20), 8),
        [0.50] * 8,
    ):
        _store(paddy_db, test_field.field_id, "NDVI", d, v)

    detect_events(paddy_db, test_field.field_id)
    stress = get_paddy_events(paddy_db, test_field.field_id, event_type="stress")
    bad = [s for s in stress if s.evidence.get("rule") == "sudden_drop"]
    assert bad == [], (
        f"sudden_drop fired on still-healthy reading(s): "
        f"{[(e.event_date, e.evidence) for e in bad]}"
    )


def test_no_events_when_series_is_flat(paddy_db, test_field):
    upsert_field(paddy_db, test_field)
    for d in _weekly(date(2025, 6, 22), 20):
        _store(paddy_db, test_field.field_id, "NDVI", d, 0.55)
        _store(paddy_db, test_field.field_id, "LSWI", d, 0.15)
    detect_events(paddy_db, test_field.field_id)
    assert get_paddy_events(paddy_db, test_field.field_id) == []
