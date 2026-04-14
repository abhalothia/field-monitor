"""Multi-index risk scoring for pest, disease, water, and nutrient stress."""

from config.settings import (
    DISEASE_WEIGHTS,
    INDEX_THRESHOLDS,
    NUTRIENT_WEIGHTS,
    OBSERVATION_BOOSTS,
    PEST_WEIGHTS,
    WATER_WEIGHTS,
)
from src.models import GroundObservation, IndexReading, RiskAssessment


def score_risk(
    latest_readings: dict[str, float],
    field_id: str,
    assessment_date: str,
    recent_observations: list[GroundObservation] | None = None,
    trend_declining: bool = False,
) -> RiskAssessment:
    """Compute composite risk scores from the latest index values.

    Args:
        latest_readings: dict mapping index name to mean value,
            e.g. {"NDVI": 0.65, "NDRE": 0.28, ...}
        field_id: field identifier
        assessment_date: ISO date string
        recent_observations: ground-truth observations from last 14 days
        trend_declining: whether the overall trend is worsening
    """
    stress_scores = {
        name: _index_to_stress(val, name)
        for name, val in latest_readings.items()
    }

    pest = _weighted_score(stress_scores, PEST_WEIGHTS)
    disease = _weighted_score(stress_scores, DISEASE_WEIGHTS)
    water = _weighted_score(stress_scores, WATER_WEIGHTS)
    nutrient = _weighted_score(stress_scores, NUTRIENT_WEIGHTS)

    factors: list[str] = []

    # Apply observation boosts
    if recent_observations:
        for obs in recent_observations:
            boost = OBSERVATION_BOOSTS.get(obs.severity, 0.0)
            if boost == 0.0:
                continue

            if obs.category in ("pest",):
                pest = min(100.0, pest + boost)
                factors.append(
                    f"Ground observation: {obs.description} ({obs.severity})"
                )
            elif obs.category in ("disease",):
                disease = min(100.0, disease + boost)
                factors.append(
                    f"Ground observation: {obs.description} ({obs.severity})"
                )
            elif obs.category in ("water",):
                water = min(100.0, water + boost)
                factors.append(
                    f"Ground observation: {obs.description} ({obs.severity})"
                )
            elif obs.category in ("nutrient",):
                nutrient = min(100.0, nutrient + boost)
                factors.append(
                    f"Ground observation: {obs.description} ({obs.severity})"
                )

    # Trend adjustment
    if trend_declining:
        multiplier = 1.15
        pest = min(100.0, pest * multiplier)
        disease = min(100.0, disease * multiplier)
        water = min(100.0, water * multiplier)
        nutrient = min(100.0, nutrient * multiplier)
        factors.append("Overall trend is declining")

    overall = max(pest, disease, water, nutrient)

    # Build contributing factors from top stress indices
    for name, stress in sorted(
        stress_scores.items(), key=lambda x: x[1], reverse=True,
    ):
        if stress > 20:
            val = latest_readings[name]
            thresh = INDEX_THRESHOLDS[name]
            factors.append(
                f"{name} at {val:.3f} "
                f"(healthy: >{thresh.healthy}, stress: <{thresh.stress})"
            )

    return RiskAssessment(
        field_id=field_id,
        assessment_date=assessment_date,
        overall_score=round(overall, 1),
        pest_risk=round(pest, 1),
        disease_risk=round(disease, 1),
        water_stress=round(water, 1),
        nutrient_stress=round(nutrient, 1),
        contributing_factors=factors,
    )


def _index_to_stress(value: float, index_name: str) -> float:
    """Convert an index value to 0-100 stress score.

    0 = healthy, 100 = severe stress.
    """
    thresholds = INDEX_THRESHOLDS.get(index_name)
    if thresholds is None:
        return 0.0

    if value >= thresholds.healthy:
        return 0.0
    if value <= thresholds.severe:
        return 100.0

    return (thresholds.healthy - value) / (thresholds.healthy - thresholds.severe) * 100.0


def _weighted_score(
    stress_scores: dict[str, float],
    weights: dict[str, float],
) -> float:
    """Compute weighted average of available stress scores."""
    total_weight = 0.0
    weighted_sum = 0.0
    for name, weight in weights.items():
        if name in stress_scores:
            weighted_sum += stress_scores[name] * weight
            total_weight += weight
    if total_weight == 0:
        return 0.0
    return weighted_sum / total_weight
