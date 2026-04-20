"""Rule-based phenology event detection for PB1 paddy.

Three event types — transplanting, harvesting, stress — each detected via
two independent paths (optical S2 indices + SAR S1 VV/VH/RVI). When only
one path fires we emit a single-path event at moderate confidence; when
both fire within a ±7-day window we upgrade to a dual-path event at high
confidence and merge the evidence dicts.

The SAR path is the reason this module exists at all: monsoon weeks (Jun–Sep
in western UP) can produce weeks of zero valid S2 pixels. SAR backscatter
doesn't care about clouds, so transplant/stress detection keeps working when
the optical path is blind.

Public entry point: `detect_events(conn, field_id, season_tag="kharif_2025")`.
It loads all season readings, runs both paths for each event type, writes
deduplicated `PaddyEvent` rows, and returns them.
"""

import logging
import sqlite3
from datetime import date, datetime, timedelta

from src.models import IndexReading
from src.paddy_kharif import config as pk_config
from src.paddy_kharif.models_paddy import PaddyEvent
from src.paddy_kharif.repository_paddy import (
    get_season_readings,
    insert_paddy_event,
)


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse(d: str) -> date:
    return datetime.strptime(d[:10], "%Y-%m-%d").date()


def _by_date(readings: list[IndexReading]) -> dict[date, IndexReading]:
    return {_parse(r.reading_date): r for r in readings if r.mean_value is not None}


def _readings_in_window(
    by_date: dict[date, IndexReading],
    start: date,
    end: date,
) -> list[tuple[date, IndexReading]]:
    return sorted(
        (d, r) for d, r in by_date.items() if start <= d <= end
    )


def _preseason_baseline(
    by_date: dict[date, IndexReading],
) -> float | None:
    """Mean value across the pre-season May baseline window."""
    start, end = pk_config.PRESEASON_BASELINE_WINDOW
    vals = [
        r.mean_value for d, r in by_date.items()
        if start <= d <= end and r.mean_value is not None
    ]
    if not vals:
        return None
    return sum(vals) / len(vals)


# ---------------------------------------------------------------------------
# Transplanting
# ---------------------------------------------------------------------------

def _transplant_optical(
    ndvi_by_date: dict[date, IndexReading],
    lswi_by_date: dict[date, IndexReading],
    field_id: str,
) -> list[PaddyEvent]:
    """Xiao 2005/2006 flood signal: LSWI + 0.05 >= NDVI AND LSWI > 0 for
    2 consecutive weekly readings, inside the transplant window."""
    start, end = pk_config.TRANSPLANT_WINDOW
    events: list[PaddyEvent] = []

    shared_dates = sorted(set(ndvi_by_date.keys()) & set(lswi_by_date.keys()))
    shared_dates = [d for d in shared_dates if start <= d <= end]

    hits: list[date] = []
    for d in shared_dates:
        ndvi = ndvi_by_date[d].mean_value
        lswi = lswi_by_date[d].mean_value
        if ndvi is None or lswi is None:
            continue
        flooded = (
            lswi + pk_config.LSWI_NDVI_MARGIN >= ndvi
            and lswi > pk_config.LSWI_MIN_FLOOD
        )
        if flooded:
            hits.append(d)

    # Need 2 consecutive weekly hits (≤10 d apart to tolerate a missed week).
    for i in range(len(hits) - 1):
        if (hits[i + 1] - hits[i]).days <= 10:
            trigger = hits[i + 1]
            events.append(PaddyEvent(
                field_id=field_id,
                event_date=trigger.isoformat(),
                event_type="transplanting",
                confidence=0.6,
                evidence={
                    "path": "optical",
                    "rule": "xiao_lswi_ndvi_margin",
                    "lswi": round(lswi_by_date[trigger].mean_value, 4),
                    "ndvi": round(ndvi_by_date[trigger].mean_value, 4),
                    "margin": pk_config.LSWI_NDVI_MARGIN,
                },
            ))
            break  # only emit the first qualifying pair
    return events


def _transplant_sar(
    vv_by_date: dict[date, IndexReading],
    rvi_by_date: dict[date, IndexReading],
    field_id: str,
) -> list[PaddyEvent]:
    """VV drops >= 2.5 dB below May baseline for 2 consecutive weeks,
    AND RVI < 0.25 (bare/flooded canopy signature)."""
    baseline = _preseason_baseline(vv_by_date)
    if baseline is None:
        logger.debug("No S1_VV pre-season baseline for %s; skip SAR transplant", field_id)
        return []

    start, end = pk_config.TRANSPLANT_WINDOW
    events: list[PaddyEvent] = []

    hits: list[tuple[date, float, float]] = []
    for d, r in sorted(vv_by_date.items()):
        if not (start <= d <= end) or r.mean_value is None:
            continue
        drop_db = r.mean_value - baseline
        rvi_read = rvi_by_date.get(d)
        rvi_val = rvi_read.mean_value if rvi_read and rvi_read.mean_value is not None else None
        if (
            drop_db <= pk_config.S1_VV_DB_DROP_TRANSPLANT
            and rvi_val is not None
            and rvi_val < 0.25
        ):
            hits.append((d, drop_db, rvi_val))

    for i in range(len(hits) - 1):
        if (hits[i + 1][0] - hits[i][0]).days <= 10:
            trigger_d, drop_db, rvi_val = hits[i + 1]
            events.append(PaddyEvent(
                field_id=field_id,
                event_date=trigger_d.isoformat(),
                event_type="transplanting",
                confidence=0.7,
                evidence={
                    "path": "sar",
                    "rule": "vv_drop_plus_low_rvi",
                    "vv_drop_db": round(drop_db, 2),
                    "vv_baseline_db": round(baseline, 2),
                    "rvi": round(rvi_val, 3),
                },
            ))
            break
    return events


# ---------------------------------------------------------------------------
# Harvesting
# ---------------------------------------------------------------------------

def _harvest_optical(
    ndvi_by_date: dict[date, IndexReading],
    field_id: str,
) -> list[PaddyEvent]:
    """Emit one harvest event when NDVI shows a peak-then-decline signature.

    Two patterns qualify; the first to match wins.

    1. Sharp-drop rule (default): NDVI peak >= HARVEST_PEAK_MIN followed by
       a drop >= HARVEST_DROP_MIN within HARVEST_DROP_WINDOW_DAYS, with the
       drop endpoint inside the calendar HARVEST_WINDOW (+14 d buffer).
       Handles the classic sharp senescence-to-cutting transition.

    2. Gradual-senescence rule: NDVI peak >= HARVEST_PEAK_MIN followed by a
       near-zero reading (< HARVEST_STUBBLE_MAX) at any date up to
       HARVEST_STUBBLE_MAX_DAYS_POSTPEAK after the peak. This is the only
       path that fires for early-transplant PB1 whose decline is too slow
       to clear the 21-day 0.25 drop bar -- yet the crop IS harvested
       (the near-zero stubble signal is unambiguous). Drop endpoint is
       the first reading where NDVI dips below the stubble threshold.
    """
    start, end = pk_config.HARVEST_WINDOW

    # --- Pattern 1: sharp-drop rule (original) ---------------------------
    sharp_scan = sorted(
        (d, r) for d, r in ndvi_by_date.items()
        if r.mean_value is not None
        and start - timedelta(days=30) <= d <= end + timedelta(days=14)
    )
    for i, (d_peak, r_peak) in enumerate(sharp_scan):
        if r_peak.mean_value < pk_config.HARVEST_PEAK_MIN:
            continue
        for d_drop, r_drop in sharp_scan[i + 1:]:
            if (d_drop - d_peak).days > pk_config.HARVEST_DROP_WINDOW_DAYS:
                break
            if r_peak.mean_value - r_drop.mean_value >= pk_config.HARVEST_DROP_MIN:
                if not (start <= d_drop <= end + timedelta(days=14)):
                    continue
                return [PaddyEvent(
                    field_id=field_id,
                    event_date=d_drop.isoformat(),
                    event_type="harvesting",
                    confidence=0.6,
                    evidence={
                        "path": "optical",
                        "rule": "ndvi_peak_drop",
                        "peak_date": d_peak.isoformat(),
                        "peak_ndvi": round(r_peak.mean_value, 4),
                        "drop_ndvi": round(r_drop.mean_value, 4),
                        "drop": round(r_peak.mean_value - r_drop.mean_value, 4),
                    },
                )]

    # --- Pattern 2: gradual-senescence rule ------------------------------
    # Peak can be anywhere in the season; the stubble reading is the
    # diagnostic half.
    full_scan = sorted(
        (d, r) for d, r in ndvi_by_date.items()
        if r.mean_value is not None
    )
    for i, (d_peak, r_peak) in enumerate(full_scan):
        if r_peak.mean_value < pk_config.HARVEST_PEAK_MIN:
            continue
        for d_drop, r_drop in full_scan[i + 1:]:
            days_after_peak = (d_drop - d_peak).days
            if days_after_peak > pk_config.HARVEST_STUBBLE_MAX_DAYS_POSTPEAK:
                break
            if r_drop.mean_value < pk_config.HARVEST_STUBBLE_MAX:
                return [PaddyEvent(
                    field_id=field_id,
                    event_date=d_drop.isoformat(),
                    event_type="harvesting",
                    confidence=0.6,
                    evidence={
                        "path": "optical",
                        "rule": "ndvi_peak_to_stubble",
                        "peak_date": d_peak.isoformat(),
                        "peak_ndvi": round(r_peak.mean_value, 4),
                        "stubble_ndvi": round(r_drop.mean_value, 4),
                        "days_peak_to_stubble": days_after_peak,
                    },
                )]
    return []


def _harvest_sar(
    vv_by_date: dict[date, IndexReading],
    vh_by_date: dict[date, IndexReading],
    rvi_by_date: dict[date, IndexReading],
    field_id: str,
) -> list[PaddyEvent]:
    """VV rises >= 1.5 dB across 2 consecutive weeks AND VH drops >= 2 dB
    AND RVI drops below 0.35 — classic dry-stubble signature."""
    start, end = pk_config.HARVEST_WINDOW
    dates = sorted(
        d for d in set(vv_by_date) & set(vh_by_date) & set(rvi_by_date)
        if start - timedelta(days=7) <= d <= end + timedelta(days=14)
    )

    for i in range(1, len(dates)):
        d_prev, d_cur = dates[i - 1], dates[i]
        if (d_cur - d_prev).days > 10:
            continue
        vv_prev = vv_by_date[d_prev].mean_value
        vv_cur = vv_by_date[d_cur].mean_value
        vh_prev = vh_by_date[d_prev].mean_value
        vh_cur = vh_by_date[d_cur].mean_value
        rvi_cur = rvi_by_date[d_cur].mean_value
        if None in (vv_prev, vv_cur, vh_prev, vh_cur, rvi_cur):
            continue
        vv_rise = vv_cur - vv_prev
        vh_drop = vh_cur - vh_prev
        if (
            vv_rise >= pk_config.S1_VV_DB_RISE_HARVEST
            and vh_drop <= -2.0
            and rvi_cur < 0.35
            and start <= d_cur <= end + timedelta(days=14)
        ):
            return [PaddyEvent(
                field_id=field_id,
                event_date=d_cur.isoformat(),
                event_type="harvesting",
                confidence=0.7,
                evidence={
                    "path": "sar",
                    "rule": "vv_rise_vh_drop_low_rvi",
                    "vv_rise_db": round(vv_rise, 2),
                    "vh_drop_db": round(vh_drop, 2),
                    "rvi": round(rvi_cur, 3),
                },
            )]
    return []


# ---------------------------------------------------------------------------
# Stress
# ---------------------------------------------------------------------------

def _stress_optical(
    readings_by_index: dict[str, list[IndexReading]],
    field_id: str,
    reproductive_start: date,
    reproductive_end: date,
) -> list[PaddyEvent]:
    """Wrap the generic anomaly detector with PB1 thresholds, restricted to
    the reproductive window. Any medium+ alert becomes a stress event.

    Two extra gates guard against senescence masquerading as stress:
    (a) trend_decline is only stress-worthy when the *current* reading is
        already at or below the healthy threshold. A healthy reading that
        happens to be on a declining edge is ripening, not stress.
    (b) the caller is expected to pass a `reproductive_end` that already
        excludes the pre-harvest ripening window (see detect_events).
    """
    # Lazy import + monkey-patch avoids a config rewrite in the generic
    # anomaly_detector module.
    import config.settings as settings

    from src import anomaly_detector

    original = settings.INDEX_THRESHOLDS
    settings.INDEX_THRESHOLDS = pk_config.PADDY_THRESHOLDS
    anomaly_detector.INDEX_THRESHOLDS = pk_config.PADDY_THRESHOLDS

    events: list[PaddyEvent] = []
    try:
        for idx, readings in readings_by_index.items():
            thresholds = pk_config.PADDY_THRESHOLDS.get(idx)
            if thresholds is None:
                continue
            windowed = [
                r for r in readings
                if reproductive_start <= _parse(r.reading_date) <= reproductive_end
            ]
            if len(windowed) < 3:
                continue
            alerts = anomaly_detector.detect_anomalies(windowed, field_id, idx)
            for a in alerts:
                if a.severity not in ("medium", "high", "critical"):
                    continue
                # Gate (a): shape-based alerts (z-score rolling deviation,
                # linear trend projection) fire on *patterns*, not absolute
                # values. During normal grain-fill NDVI / NDRE wobble
                # through ranges that still sit comfortably above the
                # stress floor -- firing "stress" on a 0.72 -> 0.60 drop
                # buries the real signal (0.64 -> 0.21 crashes). Require
                # the current reading itself to be at or below the stress
                # threshold before admitting a shape-based alert.
                # `below_threshold` is not gated: it already has an
                # absolute-value bar built in.
                if (
                    a.alert_type in ("trend_decline", "sudden_drop")
                    and a.current_value is not None
                    and a.current_value > thresholds.stress
                ):
                    continue
                evidence: dict = {
                    "path": "optical",
                    "rule": a.alert_type,
                    "index": idx,
                    "severity": a.severity,
                    "current": a.current_value,
                }
                # trend_decline stores the *forward projection* in
                # baseline_value; label it so consumers aren't misled.
                if a.alert_type == "trend_decline":
                    evidence["projected"] = a.baseline_value
                else:
                    evidence["baseline"] = a.baseline_value
                events.append(PaddyEvent(
                    field_id=field_id,
                    event_date=a.alert_date,
                    event_type="stress",
                    confidence=0.6,
                    evidence=evidence,
                ))
    finally:
        settings.INDEX_THRESHOLDS = original
        anomaly_detector.INDEX_THRESHOLDS = original

    return events


def _stress_sar(
    vh_by_date: dict[date, IndexReading],
    field_id: str,
    reproductive_start: date,
    reproductive_end: date,
) -> list[PaddyEvent]:
    """VH drop >= S1_VH_STRESS_DROP_DB vs trailing 4-week mean, inside the
    reproductive window. Catches lodging / water stress under full cloud."""
    events: list[PaddyEvent] = []
    ordered = sorted(
        (d, r) for d, r in vh_by_date.items() if r.mean_value is not None
    )
    window_weeks = pk_config.S1_VH_TRAILING_WEEKS

    for i in range(window_weeks, len(ordered)):
        d_cur, r_cur = ordered[i]
        if not (reproductive_start <= d_cur <= reproductive_end):
            continue
        trailing_vals = [v.mean_value for _d, v in ordered[i - window_weeks:i]]
        trailing_mean = sum(trailing_vals) / len(trailing_vals)
        drop = r_cur.mean_value - trailing_mean
        if drop <= pk_config.S1_VH_STRESS_DROP_DB:
            events.append(PaddyEvent(
                field_id=field_id,
                event_date=d_cur.isoformat(),
                event_type="stress",
                confidence=0.7,
                evidence={
                    "path": "sar",
                    "rule": "vh_drop_vs_trailing",
                    "vh_current_db": round(r_cur.mean_value, 2),
                    "vh_trailing_mean_db": round(trailing_mean, 2),
                    "vh_drop_db": round(drop, 2),
                    "trailing_weeks": window_weeks,
                },
            ))
    return events


# ---------------------------------------------------------------------------
# Dual-path merge
# ---------------------------------------------------------------------------

def _merge_dual_path(
    optical: list[PaddyEvent],
    sar: list[PaddyEvent],
    match_window_days: int = 7,
) -> list[PaddyEvent]:
    """Pair up events from the two paths within ±match_window_days.

    A paired event keeps the optical date (it's usually more precise for the
    phenological transition), merges evidence from both, and boosts
    confidence to 0.95. Unpaired events from either path pass through
    unchanged.
    """
    merged: list[PaddyEvent] = []
    used_sar: set[int] = set()

    for opt in optical:
        opt_d = _parse(opt.event_date)
        match_idx = None
        for j, s in enumerate(sar):
            if j in used_sar or s.event_type != opt.event_type:
                continue
            if abs((_parse(s.event_date) - opt_d).days) <= match_window_days:
                match_idx = j
                break
        if match_idx is not None:
            s = sar[match_idx]
            used_sar.add(match_idx)
            merged.append(PaddyEvent(
                field_id=opt.field_id,
                event_date=opt.event_date,
                event_type=opt.event_type,
                confidence=0.95,
                evidence={
                    **opt.evidence,
                    **{f"sar_{k}": v for k, v in s.evidence.items()},
                    "path": "optical+sar",
                },
                season_tag=opt.season_tag,
            ))
        else:
            merged.append(opt)

    for j, s in enumerate(sar):
        if j not in used_sar:
            merged.append(s)
    return merged


def _stress_end_for_field(
    rep_end: date,
    harvest_events: list[PaddyEvent],
    ndvi_by_date: dict[date, IndexReading],
) -> date:
    """Return the latest date at which stress detection is still meaningful.

    Stress detection should stay live all the way to the detected harvest
    date (or the reproductive-window end, whichever is earlier). A crop
    that crashes hard in the final two weeks before cutting -- NDVI
    dropping from 0.64 to 0.21 in a week, say -- is a real stress signal
    that extension agents need to see. Ambiguous late-ripening moves
    (NDVI 0.60 -> 0.50 over three weeks) are handled by the per-rule
    gates in `_stress_optical` instead of being erased by this cutoff.

    A tiny buffer is applied when no harvest has been detected but the
    NDVI peak is in the very last 7 days of the reproductive window --
    that late peak is unambiguously ripening.
    """
    candidate = rep_end

    # Harvest fired -> stress may run all the way to the harvest date.
    for ev in harvest_events:
        try:
            h_date = _parse(ev.event_date)
        except (TypeError, ValueError):
            continue
        if h_date < candidate:
            candidate = h_date

    # Very-late-peak buffer (only when harvest hasn't fired): a peak in
    # the final week of the reproductive window is the "harvest detector
    # just hasn't seen the drop yet" case. Shave 7 days so we don't flag
    # the onset of senescence as stress.
    if not harvest_events:
        late_window_start = rep_end - timedelta(days=7)
        for d, r in ndvi_by_date.items():
            if r.mean_value is None or r.mean_value < pk_config.HARVEST_PEAK_MIN:
                continue
            if late_window_start <= d <= rep_end:
                cutoff = d - timedelta(days=7)
                if cutoff < candidate:
                    candidate = cutoff

    return candidate


def _detected_transplant_date(events: list[PaddyEvent]) -> date:
    """Pick the best transplant date for relative-window calculations.

    Prefer a dual-path event (confidence ≥ 0.9), then the earliest transplant,
    then fall back to DEFAULT_TRANSPLANT_PROXY.
    """
    tr = [e for e in events if e.event_type == "transplanting"]
    if not tr:
        return pk_config.DEFAULT_TRANSPLANT_PROXY
    tr.sort(key=lambda e: (-e.confidence, e.event_date))
    return _parse(tr[0].event_date)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_events(
    conn: sqlite3.Connection,
    field_id: str,
    season_tag: str = pk_config.SEASON_TAG,
) -> list[PaddyEvent]:
    """Run all three detectors (transplant / harvest / stress) for a field.

    Writes events to `paddy_events` (insert is idempotent + merges evidence
    on duplicates) and returns the full list.
    """
    readings = get_season_readings(conn, field_id, season_tag=season_tag)
    # Also pull pre-season May readings for the SAR baseline — they live
    # under the generic tag because they predate the kharif season.
    preseason = get_season_readings(conn, field_id, season_tag="generic")
    readings = readings + [
        r for r in preseason
        if pk_config.PRESEASON_BASELINE_WINDOW[0]
        <= _parse(r.reading_date)
        <= pk_config.PRESEASON_BASELINE_WINDOW[1]
    ]

    by_index: dict[str, list[IndexReading]] = {}
    for r in readings:
        by_index.setdefault(r.index_name, []).append(r)

    ndvi_bd = _by_date(by_index.get("NDVI", []))
    lswi_bd = _by_date(by_index.get("LSWI", []))
    vv_bd = _by_date(by_index.get("S1_VV", []))
    vh_bd = _by_date(by_index.get("S1_VH", []))
    rvi_bd = _by_date(by_index.get("S1_RVI", []))

    # --- Transplant ---
    transplant_opt = _transplant_optical(ndvi_bd, lswi_bd, field_id)
    transplant_sar = _transplant_sar(vv_bd, rvi_bd, field_id)
    transplant_events = _merge_dual_path(transplant_opt, transplant_sar)

    # --- Derive reproductive window from the detected transplant ---
    t_date = _detected_transplant_date(transplant_events)
    rep_off_start, rep_off_end = pk_config.REPRODUCTIVE_OFFSET_DAYS
    rep_start = t_date + timedelta(days=rep_off_start)
    rep_end = t_date + timedelta(days=rep_off_end)

    # --- Harvest (must run before stress so we can gate stress on it) ---
    harvest_opt = _harvest_optical(ndvi_bd, field_id)
    harvest_sar = _harvest_sar(vv_bd, vh_bd, rvi_bd, field_id)
    harvest_events = _merge_dual_path(harvest_opt, harvest_sar)

    # --- Stress (reproductive window, with a pre-harvest ripening cutoff) ---
    # Once harvest is detected (or detectable from the NDVI peak), the last
    # ~21 days of the reproductive window are dominated by ripening decline,
    # which trend_decline will misread as stress. Shrink rep_end to the
    # earliest pre-harvest cutoff when one is available.
    stress_rep_end = _stress_end_for_field(
        rep_end, harvest_events, ndvi_bd,
    )

    stress_opt = _stress_optical(by_index, field_id, rep_start, stress_rep_end)
    stress_sar = _stress_sar(vh_bd, field_id, rep_start, stress_rep_end)
    stress_events = _merge_dual_path(stress_opt, stress_sar)

    all_events = transplant_events + harvest_events + stress_events
    for e in all_events:
        # The dataclass is frozen, so rebuild with the correct season_tag if
        # a caller passed a non-default.
        to_insert = (
            e if e.season_tag == season_tag
            else PaddyEvent(
                field_id=e.field_id,
                event_date=e.event_date,
                event_type=e.event_type,
                confidence=e.confidence,
                evidence=e.evidence,
                season_tag=season_tag,
            )
        )
        insert_paddy_event(conn, to_insert)

    logger.info(
        "Paddy events for %s (%s): transplant=%d harvest=%d stress=%d",
        field_id, season_tag,
        len(transplant_events), len(harvest_events), len(stress_events),
    )
    return all_events
