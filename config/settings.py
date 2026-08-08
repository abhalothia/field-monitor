"""Configuration loaded from environment variables and sensible defaults."""

from dataclasses import dataclass, field
from pathlib import Path
import os

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "field_monitor.db"
IMAGES_DIR = PROJECT_ROOT / "images"
KML_PATH = Path(os.environ.get(
    "FIELD_KML_PATH",
    str(PROJECT_ROOT.parent / "mandi_field.kml"),
))
FIELD_NAME = os.environ.get("FIELD_NAME", "Untitled polygon")


@dataclass(frozen=True)
class SentinelHubConfig:
    client_id: str
    client_secret: str
    token_url: str = (
        "https://services.sentinel-hub.com/auth/realms/main/"
        "protocol/openid-connect/token"
    )
    base_url: str = "https://services.sentinel-hub.com/api/v1"


# Copernicus Data Space Ecosystem (CDSE) endpoints -- free tier
CDSE_TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/"
    "protocol/openid-connect/token"
)
CDSE_BASE_URL = "https://sh.dataspace.copernicus.eu/api/v1"


def get_sentinel_config() -> SentinelHubConfig:
    client_id = os.environ.get("SENTINEL_HUB_CLIENT_ID")
    client_secret = os.environ.get("SENTINEL_HUB_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise EnvironmentError(
            "SENTINEL_HUB_CLIENT_ID and SENTINEL_HUB_CLIENT_SECRET "
            "must be set as environment variables."
        )

    # Auto-detect endpoint: SENTINEL_HUB_ENDPOINT=cdse or sentinel-hub
    endpoint = os.environ.get("SENTINEL_HUB_ENDPOINT", "sentinel-hub")
    if endpoint == "cdse":
        return SentinelHubConfig(
            client_id=client_id,
            client_secret=client_secret,
            token_url=CDSE_TOKEN_URL,
            base_url=CDSE_BASE_URL,
        )

    return SentinelHubConfig(client_id=client_id, client_secret=client_secret)


# --- Index thresholds (healthy / stress / severe) ---
# Tuned for subtropical crops in the Delhi/NCR region.

@dataclass(frozen=True)
class IndexThresholds:
    healthy: float
    stress: float
    severe: float


INDEX_THRESHOLDS: dict[str, IndexThresholds] = {
    "NDVI": IndexThresholds(healthy=0.6, stress=0.4, severe=0.25),
    "NDRE": IndexThresholds(healthy=0.3, stress=0.2, severe=0.1),
    "NDWI": IndexThresholds(healthy=0.1, stress=-0.05, severe=-0.15),
    "EVI":  IndexThresholds(healthy=0.4, stress=0.2, severe=0.1),
    "SAVI": IndexThresholds(healthy=0.5, stress=0.3, severe=0.15),
    "NDMI": IndexThresholds(healthy=0.2, stress=0.1, severe=0.0),
}

# Anomaly detector parameters
ROLLING_WINDOW = 6          # readings for rolling baseline
Z_SCORE_MEDIUM = -2.0
Z_SCORE_HIGH = -3.0
Z_SCORE_CRITICAL = -4.0
TREND_WINDOW = 10           # readings for linear trend
TREND_SIGNIFICANCE = 0.05   # p-value threshold
TREND_PROJECTION_DAYS = 14

# Risk scorer weights
PEST_WEIGHTS = {"NDVI": 0.4, "NDRE": 0.3, "EVI": 0.2, "SAVI": 0.1}
DISEASE_WEIGHTS = {"NDRE": 0.35, "NDVI": 0.30, "NDMI": 0.20, "EVI": 0.15}
WATER_WEIGHTS = {"NDWI": 0.45, "NDMI": 0.35, "NDVI": 0.20}
NUTRIENT_WEIGHTS = {"NDRE": 0.50, "NDVI": 0.25, "EVI": 0.25}

# Observation severity boosts
OBSERVATION_BOOSTS = {"low": 10.0, "medium": 25.0, "high": 50.0}

# Data fetch defaults
DEFAULT_LOOKBACK_DAYS = 180
AGGREGATION_INTERVAL = "P5D"
MAX_CLOUD_COVER = 30
IMAGE_SIZE = 512

# Scheduler interval (seconds)
FETCH_INTERVAL_HOURS = 12
