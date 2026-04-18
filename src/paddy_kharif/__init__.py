"""Paddy kharif 2025 offshoot: PB1 in Aligarh/Bulandshahr, western UP.

Public surface:
  - fetch_kharif_season(conn, field, year=2025): full-season ingestion
  - detect_events(conn, field): run phenology rules, write paddy_events
  - PADDY_THRESHOLDS: starting threshold triplets per index
  - SEASON_TAG, SEASON_START, SEASON_END: season constants
"""

from src.paddy_kharif.config import (
    PADDY_THRESHOLDS,
    SEASON_END,
    SEASON_START,
    SEASON_TAG,
)
from src.paddy_kharif.models_paddy import PaddyEvent
from src.paddy_kharif.paddy_fetcher import fetch_kharif_season
from src.paddy_kharif.phenology import detect_events

__all__ = [
    "fetch_kharif_season",
    "detect_events",
    "PADDY_THRESHOLDS",
    "SEASON_TAG",
    "SEASON_START",
    "SEASON_END",
    "PaddyEvent",
]
