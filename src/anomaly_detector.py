"""Time-series anomaly detection for vegetation indices."""

import numpy as np
from scipy import stats as sp_stats

from config.settings import (
    INDEX_THRESHOLDS,
    ROLLING_WINDOW,
    TREND_PROJECTION_DAYS,
    TREND_SIGNIFICANCE,
    TREND_WINDOW,
    Z_SCORE_CRITICAL,
    Z_SCORE_HIGH,
    Z_SCORE_MEDIUM,
)
from src.models import AnomalyAlert, IndexReading


def detect_anomalies(
    readings: list[IndexReading],
    field_id: str,
    index_name: str,
) -> list[AnomalyAlert]:
    """Run all anomaly detection methods on a time series of readings.

    Readings should be sorted by date ascending and filtered for
    the same field and index.
    """
    values = [r.mean_value for r in readings if r.mean_value is not None]
    dates = [r.reading_date for r in readings if r.mean_value is not None]

    if len(values) < 3:
        return []

    alerts: list[AnomalyAlert] = []
    alerts.extend(_detect_rolling_deviation(values, dates, field_id, index_name))
    alerts.extend(_detect_threshold_breach(values, dates, field_id, index_name))
    alerts.extend(_detect_trend_decline(values, dates, field_id, index_name))

    return _deduplicate(alerts)


def _detect_rolling_deviation(
    values: list[float],
    dates: list[str],
    field_id: str,
    index_name: str,
) -> list[AnomalyAlert]:
    """Flag readings that deviate significantly from the rolling baseline."""
    alerts = []
    window = min(ROLLING_WINDOW, len(values) - 1)
    if window < 3:
        return alerts

    for i in range(window, len(values)):
        baseline = values[i - window:i]
        mean = np.mean(baseline)
        std = np.std(baseline, ddof=1)
        if std < 0.01:
            continue

        z = (values[i] - mean) / std

        if z <= Z_SCORE_CRITICAL:
            severity = "critical"
        elif z <= Z_SCORE_HIGH:
            severity = "high"
        elif z <= Z_SCORE_MEDIUM:
            severity = "medium"
        else:
            continue

        alerts.append(AnomalyAlert(
            field_id=field_id,
            alert_date=dates[i],
            index_name=index_name,
            alert_type="sudden_drop",
            severity=severity,
            current_value=round(values[i], 4),
            baseline_value=round(mean, 4),
            deviation=round(z, 2),
            message=(
                f"{index_name} dropped to {values[i]:.3f} "
                f"(baseline {mean:.3f}, z={z:.1f})"
            ),
        ))

    return alerts


def _detect_threshold_breach(
    values: list[float],
    dates: list[str],
    field_id: str,
    index_name: str,
) -> list[AnomalyAlert]:
    """Flag readings below absolute stress/severe thresholds."""
    thresholds = INDEX_THRESHOLDS.get(index_name)
    if thresholds is None:
        return []

    alerts = []
    for i, val in enumerate(values):
        if val <= thresholds.severe:
            severity = "critical"
        elif val <= thresholds.stress:
            severity = "high"
        else:
            continue

        alerts.append(AnomalyAlert(
            field_id=field_id,
            alert_date=dates[i],
            index_name=index_name,
            alert_type="below_threshold",
            severity=severity,
            current_value=round(val, 4),
            baseline_value=thresholds.healthy,
            deviation=round(val - thresholds.healthy, 4),
            message=(
                f"{index_name} at {val:.3f}, below "
                f"{'severe' if val <= thresholds.severe else 'stress'} "
                f"threshold"
            ),
        ))

    return alerts


def _detect_trend_decline(
    values: list[float],
    dates: list[str],
    field_id: str,
    index_name: str,
) -> list[AnomalyAlert]:
    """Flag if a linear trend projects below stress threshold within 2 weeks."""
    thresholds = INDEX_THRESHOLDS.get(index_name)
    if thresholds is None:
        return []

    window = min(TREND_WINDOW, len(values))
    if window < 5:
        return []

    recent = values[-window:]
    x = np.arange(len(recent), dtype=float)
    slope, intercept, _r, p_value, _se = sp_stats.linregress(x, recent)

    if slope >= 0 or p_value > TREND_SIGNIFICANCE:
        return []

    # Project forward: assume 5-day intervals, project TREND_PROJECTION_DAYS
    steps_forward = TREND_PROJECTION_DAYS / 5.0
    projected = intercept + slope * (len(recent) - 1 + steps_forward)

    if projected >= thresholds.stress:
        return []

    return [AnomalyAlert(
        field_id=field_id,
        alert_date=dates[-1],
        index_name=index_name,
        alert_type="trend_decline",
        severity="medium",
        current_value=round(values[-1], 4),
        baseline_value=round(projected, 4),
        deviation=round(slope, 6),
        message=(
            f"{index_name} declining (slope={slope:.4f}/interval), "
            f"projected to reach {projected:.3f} in {TREND_PROJECTION_DAYS} days"
        ),
    )]


def _deduplicate(alerts: list[AnomalyAlert]) -> list[AnomalyAlert]:
    """Remove duplicate alerts for the same date/index/type."""
    seen: set[tuple[str, str, str]] = set()
    unique = []
    for a in alerts:
        key = (a.alert_date, a.index_name, a.alert_type)
        if key not in seen:
            seen.add(key)
            unique.append(a)
    return unique
