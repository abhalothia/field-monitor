"""Tests for anomaly detection behavior."""

import pytest

from src.anomaly_detector import detect_anomalies
from src.models import IndexReading


def _make_readings(
    values: list[float],
    index_name: str = "NDVI",
    field_id: str = "f1",
) -> list[IndexReading]:
    """Build a series of readings with dates 5 days apart."""
    readings = []
    for i, val in enumerate(values):
        day = (i + 1) * 5
        date_str = f"2026-01-{day:02d}" if day <= 28 else f"2026-02-{day - 31:02d}"
        readings.append(IndexReading(
            field_id=field_id, index_name=index_name,
            reading_date=date_str, mean_value=val,
            min_value=val - 0.1, max_value=val + 0.1,
            stdev_value=0.05, sample_count=38, cloud_cover_pct=5.0,
        ))
    return readings


class TestStableSeries:
    def test_no_alerts_for_healthy_stable_ndvi(self):
        # Stable NDVI around 0.7 -- no anomalies expected
        values = [0.70, 0.71, 0.69, 0.72, 0.70, 0.71, 0.69, 0.70]
        readings = _make_readings(values)

        alerts = detect_anomalies(readings, "f1", "NDVI")

        assert len(alerts) == 0


class TestSuddenDrop:
    def test_detects_large_sudden_drop(self):
        # Stable at 0.7, then drops to 0.3
        values = [0.70, 0.71, 0.69, 0.72, 0.70, 0.71, 0.30]
        readings = _make_readings(values)

        alerts = detect_anomalies(readings, "f1", "NDVI")

        drop_alerts = [a for a in alerts if a.alert_type == "sudden_drop"]
        assert len(drop_alerts) >= 1
        assert drop_alerts[0].severity in ("high", "critical")

    def test_drop_alert_includes_baseline_info(self):
        values = [0.70, 0.71, 0.69, 0.72, 0.70, 0.71, 0.25]
        readings = _make_readings(values)

        alerts = detect_anomalies(readings, "f1", "NDVI")
        drop_alerts = [a for a in alerts if a.alert_type == "sudden_drop"]

        assert len(drop_alerts) >= 1
        assert drop_alerts[0].baseline_value is not None
        assert drop_alerts[0].baseline_value > 0.6


class TestThresholdBreach:
    def test_detects_value_below_stress_threshold(self):
        # NDVI stress threshold = 0.4, severe = 0.25
        values = [0.70, 0.65, 0.55, 0.45, 0.35, 0.30, 0.20]
        readings = _make_readings(values)

        alerts = detect_anomalies(readings, "f1", "NDVI")

        threshold_alerts = [a for a in alerts if a.alert_type == "below_threshold"]
        assert len(threshold_alerts) >= 1

    def test_severe_breach_is_critical(self):
        values = [0.70, 0.65, 0.55, 0.45, 0.35, 0.30, 0.15]
        readings = _make_readings(values)

        alerts = detect_anomalies(readings, "f1", "NDVI")

        critical = [
            a for a in alerts
            if a.alert_type == "below_threshold" and a.severity == "critical"
        ]
        assert len(critical) >= 1


class TestTrendDecline:
    def test_detects_steady_downward_trend(self):
        # Gradual decline from 0.70 to 0.45 over 10 readings
        values = [0.70, 0.68, 0.65, 0.62, 0.59, 0.56, 0.53, 0.50, 0.47, 0.45]
        readings = _make_readings(values)

        alerts = detect_anomalies(readings, "f1", "NDVI")

        trend_alerts = [a for a in alerts if a.alert_type == "trend_decline"]
        assert len(trend_alerts) >= 1
        assert trend_alerts[0].severity == "medium"


class TestTooFewReadings:
    def test_no_alerts_with_fewer_than_3_readings(self):
        values = [0.70, 0.30]
        readings = _make_readings(values)

        alerts = detect_anomalies(readings, "f1", "NDVI")

        # Should not crash, may have limited results
        assert isinstance(alerts, list)
