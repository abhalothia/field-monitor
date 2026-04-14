"""Tests for risk scoring behavior."""

import pytest

from src.models import GroundObservation
from src.risk_scorer import score_risk


def _healthy_readings() -> dict[str, float]:
    return {
        "NDVI": 0.75, "NDRE": 0.40, "NDWI": 0.20,
        "EVI": 0.50, "SAVI": 0.60, "NDMI": 0.30,
    }


def _stressed_readings() -> dict[str, float]:
    return {
        "NDVI": 0.30, "NDRE": 0.12, "NDWI": -0.10,
        "EVI": 0.15, "SAVI": 0.20, "NDMI": 0.05,
    }


class TestHealthyField:
    def test_all_healthy_gives_low_overall_score(self):
        result = score_risk(_healthy_readings(), "f1", "2026-03-25")

        assert result.overall_score < 15.0

    def test_all_categories_low(self):
        result = score_risk(_healthy_readings(), "f1", "2026-03-25")

        assert result.pest_risk < 15.0
        assert result.disease_risk < 15.0
        assert result.water_stress < 15.0
        assert result.nutrient_stress < 15.0


class TestStressedField:
    def test_stressed_gives_high_overall_score(self):
        result = score_risk(_stressed_readings(), "f1", "2026-03-25")

        assert result.overall_score > 50.0

    def test_water_stress_highest_when_ndwi_low(self):
        readings = _healthy_readings()
        readings["NDWI"] = -0.20
        readings["NDMI"] = -0.05

        result = score_risk(readings, "f1", "2026-03-25")

        assert result.water_stress > result.pest_risk
        assert result.water_stress > result.nutrient_stress


class TestGroundObservationBoosts:
    def test_pest_observation_boosts_pest_risk(self):
        readings = _healthy_readings()
        base = score_risk(readings, "f1", "2026-03-25")

        obs = GroundObservation(
            field_id="f1", observation_date="2026-03-20",
            category="pest", severity="high",
            description="Heavy aphid infestation",
        )
        boosted = score_risk(readings, "f1", "2026-03-25", [obs])

        assert boosted.pest_risk > base.pest_risk
        assert boosted.pest_risk >= base.pest_risk + 40  # high = +50, on base ~0

    def test_observation_appears_in_factors(self):
        obs = GroundObservation(
            field_id="f1", observation_date="2026-03-20",
            category="disease", severity="medium",
            description="Powdery mildew on lower leaves",
        )
        result = score_risk(_healthy_readings(), "f1", "2026-03-25", [obs])

        factor_text = " ".join(result.contributing_factors)
        assert "Powdery mildew" in factor_text


class TestTrendAdjustment:
    def test_declining_trend_increases_scores(self):
        readings = _stressed_readings()
        base = score_risk(readings, "f1", "2026-03-25")
        adjusted = score_risk(readings, "f1", "2026-03-25", trend_declining=True)

        assert adjusted.overall_score >= base.overall_score

    def test_trend_factor_in_contributing_factors(self):
        result = score_risk(
            _stressed_readings(), "f1", "2026-03-25", trend_declining=True,
        )
        assert any("declining" in f.lower() for f in result.contributing_factors)


class TestOverallIsMax:
    def test_overall_equals_max_category(self):
        result = score_risk(_stressed_readings(), "f1", "2026-03-25")

        expected_max = max(
            result.pest_risk, result.disease_risk,
            result.water_stress, result.nutrient_stress,
        )
        assert result.overall_score == pytest.approx(expected_max, abs=0.1)
