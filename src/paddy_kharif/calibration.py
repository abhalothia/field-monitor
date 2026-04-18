"""Adaptive threshold calibration from ground observations.

The default PB1 thresholds in `config.PADDY_THRESHOLDS` are literature-derived
heuristics. Once the user tags observations over a season, this module fits
the three-tier (healthy, stress, severe) triplet to their actual field data
and writes the calibrated values to `paddy_calibrated_thresholds`. The
phenology + anomaly detectors then prefer the calibrated row when one
exists, so thresholds get more accurate with every season of ground truth.

Methodology (deliberately simple, explicit, and reviewable):

  For each index that has PB1 defaults:
    1. Collect all season readings that coincide (±7 d) with an observation.
    2. Split by observation severity:
         healthy_samples ← severity in {'none'} or no observation for that week
         medium_samples  ← severity == 'medium'
         severe_samples  ← severity == 'high'
    3. Fit:
         healthy := 20th percentile of healthy_samples
                    (floor below which vigorous stands rarely sit)
         stress  := 50th percentile of medium_samples
         severe  := 50th percentile of severe_samples
    4. Require ≥MIN_SAMPLES_PER_TIER per tier, else fall back to the default.
    5. Enforce ordering healthy > stress > severe (reject otherwise).

The output is field-scoped so neighbours with different management regimes
don't contaminate each other's thresholds.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta
from statistics import quantiles

from src.paddy_kharif import config as pk_config
from src.paddy_kharif.repository_paddy import (
    get_season_readings,
    upsert_calibrated_thresholds,
)


logger = logging.getLogger(__name__)


MATCH_WINDOW_DAYS = 7
MIN_SAMPLES_PER_TIER = 3


def _percentile(values: list[float], pct: float) -> float:
    """Percentile without numpy (module already avoids heavy deps here)."""
    if not values:
        raise ValueError("empty values")
    if len(values) == 1:
        return values[0]
    # statistics.quantiles with n=100 gives 99 cut points at 1%-99%.
    cuts = quantiles(sorted(values), n=100, method="inclusive")
    idx = max(0, min(len(cuts) - 1, int(round(pct)) - 1))
    return cuts[idx]


def _load_observations(
    conn: sqlite3.Connection,
    field_id: str,
    season_start: str,
    season_end: str,
) -> list[dict]:
    rows = conn.execute(
        """SELECT observation_date, severity FROM observations
           WHERE field_id = ? AND observation_date >= ? AND observation_date <= ?""",
        (field_id, season_start, season_end),
    ).fetchall()
    return [
        {"date": r["observation_date"], "severity": r["severity"]}
        for r in rows
    ]


def _bucket_readings(
    readings: list,
    observations: list[dict],
) -> tuple[list[float], list[float], list[float]]:
    """Split reading values into (healthy, medium, severe) buckets.

    A reading matches an observation if their dates are within MATCH_WINDOW_DAYS.
    Readings with no matching observation are treated as 'healthy' on the
    assumption that unreported weeks are normal.
    """
    healthy_vals: list[float] = []
    medium_vals: list[float] = []
    severe_vals: list[float] = []

    obs_parsed = [
        (datetime.strptime(o["date"][:10], "%Y-%m-%d").date(), o["severity"])
        for o in observations
    ]
    window = timedelta(days=MATCH_WINDOW_DAYS)

    for r in readings:
        if r.mean_value is None:
            continue
        r_date = datetime.strptime(r.reading_date[:10], "%Y-%m-%d").date()
        matched_sev = None
        for obs_date, sev in obs_parsed:
            if abs(obs_date - r_date) <= window:
                # Pick the worst-severity observation that matches.
                rank = {"none": 0, "low": 1, "medium": 2, "high": 3}
                if matched_sev is None or rank.get(sev, 0) > rank.get(matched_sev, 0):
                    matched_sev = sev

        if matched_sev in (None, "none", "low"):
            healthy_vals.append(r.mean_value)
        elif matched_sev == "medium":
            medium_vals.append(r.mean_value)
        elif matched_sev == "high":
            severe_vals.append(r.mean_value)

    return healthy_vals, medium_vals, severe_vals


def calibrate_thresholds(
    conn: sqlite3.Connection,
    field_id: str,
    season_tag: str = pk_config.SEASON_TAG,
) -> dict[str, tuple[float, float, float]]:
    """Fit and persist calibrated thresholds for one field's season.

    Returns a dict of the indices that were successfully calibrated. Indices
    without enough labelled samples are skipped (the caller continues to use
    the literature default).
    """
    observations = _load_observations(
        conn, field_id,
        pk_config.SEASON_START, pk_config.SEASON_END,
    )
    if not observations:
        logger.info("No observations for %s in %s — skipping calibration",
                    field_id, season_tag)
        return {}

    calibrated: dict[str, tuple[float, float, float]] = {}

    for idx_name, defaults in pk_config.PADDY_THRESHOLDS.items():
        readings = get_season_readings(
            conn, field_id, season_tag=season_tag, index_name=idx_name,
        )
        if not readings:
            continue

        healthy_vals, medium_vals, severe_vals = _bucket_readings(
            readings, observations,
        )
        if (
            len(healthy_vals) < MIN_SAMPLES_PER_TIER
            or len(medium_vals) < MIN_SAMPLES_PER_TIER
            or len(severe_vals) < MIN_SAMPLES_PER_TIER
        ):
            logger.debug(
                "%s: not enough samples for %s (h=%d m=%d s=%d); keep defaults",
                field_id, idx_name,
                len(healthy_vals), len(medium_vals), len(severe_vals),
            )
            continue

        healthy = _percentile(healthy_vals, 20)
        stress = _percentile(medium_vals, 50)
        severe = _percentile(severe_vals, 50)

        if not (healthy > stress > severe):
            logger.warning(
                "%s: calibrated thresholds for %s not monotonic "
                "(h=%.3f s=%.3f sv=%.3f); keep defaults",
                field_id, idx_name, healthy, stress, severe,
            )
            continue

        upsert_calibrated_thresholds(
            conn,
            scope=field_id,
            index_name=idx_name,
            healthy=healthy,
            stress=stress,
            severe=severe,
            sample_count=len(healthy_vals) + len(medium_vals) + len(severe_vals),
            season_tag=season_tag,
        )
        calibrated[idx_name] = (healthy, stress, severe)
        logger.info(
            "%s: calibrated %s thresholds h=%.3f s=%.3f sv=%.3f (default %.3f/%.3f/%.3f)",
            field_id, idx_name, healthy, stress, severe,
            defaults.healthy, defaults.stress, defaults.severe,
        )

    return calibrated
