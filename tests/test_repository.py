"""Tests for database repository operations."""

import sqlite3

import pytest

from db.schema import create_tables
from db.repository import (
    acknowledge_alert,
    get_alerts,
    get_field,
    get_latest_risk,
    get_observations,
    get_readings,
    insert_alert,
    insert_observation,
    upsert_field,
    upsert_reading,
    upsert_risk_assessment,
)
from src.models import (
    AnomalyAlert,
    FieldPolygon,
    GroundObservation,
    IndexReading,
    RiskAssessment,
)


def _make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_tables(conn)
    return conn


def _make_field(field_id: str = "f1") -> FieldPolygon:
    return FieldPolygon(
        field_id=field_id, name="Test field",
        coordinates=[(77.81, 28.09), (77.82, 28.09), (77.82, 28.10)],
        center_lon=77.815, center_lat=28.095,
        area_hectares=0.38,
        polygon_wkt="POLYGON((77.81 28.09, 77.82 28.09, 77.82 28.10))",
        polygon_geojson={"type": "Polygon", "coordinates": [[[77.81, 28.09]]]},
    )


def _make_reading(
    field_id: str = "f1",
    index_name: str = "NDVI",
    reading_date: str = "2026-03-01",
    mean_value: float = 0.65,
) -> IndexReading:
    return IndexReading(
        field_id=field_id, index_name=index_name,
        reading_date=reading_date, mean_value=mean_value,
        min_value=0.3, max_value=0.85, stdev_value=0.12,
        sample_count=38, cloud_cover_pct=5.0,
    )


class TestFieldOperations:
    def test_upsert_and_retrieve_field(self):
        conn = _make_db()
        fp = _make_field()
        upsert_field(conn, fp)

        result = get_field(conn, "f1")

        assert result is not None
        assert result.name == "Test field"
        assert result.area_hectares == 0.38

    def test_upsert_updates_existing_field(self):
        conn = _make_db()
        upsert_field(conn, _make_field())

        updated = FieldPolygon(
            field_id="f1", name="Updated name",
            coordinates=[], center_lon=77.0, center_lat=28.0,
            area_hectares=0.5, polygon_wkt="POLYGON(...)",
            polygon_geojson={"type": "Polygon", "coordinates": [[]]},
        )
        upsert_field(conn, updated)

        result = get_field(conn, "f1")
        assert result is not None
        assert result.name == "Updated name"

    def test_returns_none_for_missing_field(self):
        conn = _make_db()
        assert get_field(conn, "nonexistent") is None


class TestReadingOperations:
    def test_upsert_and_query_readings(self):
        conn = _make_db()
        upsert_field(conn, _make_field())
        upsert_reading(conn, _make_reading())

        readings = get_readings(conn, "f1")
        assert len(readings) == 1
        assert readings[0].mean_value == 0.65

    def test_filter_by_index_name(self):
        conn = _make_db()
        upsert_field(conn, _make_field())
        upsert_reading(conn, _make_reading(index_name="NDVI"))
        upsert_reading(conn, _make_reading(index_name="NDWI", mean_value=0.15))

        ndvi_only = get_readings(conn, "f1", index_name="NDVI")
        assert len(ndvi_only) == 1
        assert ndvi_only[0].index_name == "NDVI"

    def test_filter_by_date_range(self):
        conn = _make_db()
        upsert_field(conn, _make_field())
        upsert_reading(conn, _make_reading(reading_date="2026-01-01"))
        upsert_reading(conn, _make_reading(reading_date="2026-02-01"))
        upsert_reading(conn, _make_reading(reading_date="2026-03-01"))

        feb_only = get_readings(conn, "f1", date_from="2026-01-15", date_to="2026-02-15")
        assert len(feb_only) == 1

    def test_upsert_updates_existing_reading(self):
        conn = _make_db()
        upsert_field(conn, _make_field())
        upsert_reading(conn, _make_reading(mean_value=0.5))
        upsert_reading(conn, _make_reading(mean_value=0.7))

        readings = get_readings(conn, "f1")
        assert len(readings) == 1
        assert readings[0].mean_value == 0.7


class TestAlertOperations:
    def _make_alert(self, field_id: str = "f1") -> AnomalyAlert:
        return AnomalyAlert(
            field_id=field_id, alert_date="2026-03-20",
            index_name="NDVI", alert_type="sudden_drop",
            severity="high", current_value=0.35,
            baseline_value=0.65, deviation=-3.1,
            message="NDVI dropped significantly",
        )

    def test_insert_and_retrieve_alert(self):
        conn = _make_db()
        upsert_field(conn, _make_field())
        alert_id = insert_alert(conn, self._make_alert())

        alerts = get_alerts(conn, "f1")
        assert len(alerts) == 1
        assert alerts[0].severity == "high"

    def test_acknowledge_alert(self):
        conn = _make_db()
        upsert_field(conn, _make_field())
        alert_id = insert_alert(conn, self._make_alert())

        acknowledge_alert(conn, alert_id)
        alerts = get_alerts(conn, "f1", acknowledged=True)
        assert len(alerts) == 1
        assert alerts[0].is_acknowledged is True

    def test_filter_by_severity(self):
        conn = _make_db()
        upsert_field(conn, _make_field())
        insert_alert(conn, self._make_alert())

        high = get_alerts(conn, "f1", severity="high")
        low = get_alerts(conn, "f1", severity="low")
        assert len(high) == 1
        assert len(low) == 0


class TestObservationOperations:
    def test_insert_and_retrieve_observation(self):
        conn = _make_db()
        upsert_field(conn, _make_field())

        obs = GroundObservation(
            field_id="f1", observation_date="2026-03-18",
            category="pest", severity="medium",
            description="Aphid infestation on wheat",
            affected_area_pct=25.0,
        )
        insert_observation(conn, obs)

        results = get_observations(conn, "f1")
        assert len(results) == 1
        assert results[0].category == "pest"
        assert results[0].affected_area_pct == 25.0


class TestRiskAssessmentOperations:
    def test_upsert_and_get_latest(self):
        conn = _make_db()
        upsert_field(conn, _make_field())

        ra = RiskAssessment(
            field_id="f1", assessment_date="2026-03-25",
            overall_score=45.0, pest_risk=20.0, disease_risk=45.0,
            water_stress=10.0, nutrient_stress=30.0,
            contributing_factors=["NDRE below stress threshold"],
        )
        upsert_risk_assessment(conn, ra)

        latest = get_latest_risk(conn, "f1")
        assert latest is not None
        assert latest.overall_score == 45.0
        assert "NDRE below stress threshold" in latest.contributing_factors
