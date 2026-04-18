"""Configuration for the paddy kharif 2025 offshoot.

Target crop: Pusa Basmati 1 (PB1), the IARI 1989 release (Khush, Singh et al.).
PB1 is long-duration (~135-140 day) semi-dwarf basmati - clearly longer than
PB 1509 (~120 d), slightly shorter than Pusa 1121 (~143 d), and shorter than
traditional Basmati 370 (~155 d).

Target region: Aligarh and Bulandshahr districts, western UP (upper Ganga doab).

Thresholds are heuristic starting values derived from:
  - Xiao et al. 2005/2006 (RSE) for the LSWI+0.05 >= NDVI flood signal
  - Mosleh et al. 2015 (Sensors) review of rice NDVI regimes
  - Son et al. 2014 (Remote Sensing) for phenology-window methodology
  - SAC/ISRO FASAL/CHAMAN rice inventory reference ranges for Indian basmati
  - IARI release notifications for PB1 (duration, plant height, tillering)

The triplet (healthy, stress, severe) for PB1 is NOT from a single paper;
it is fitted into the three-tier IndexThresholds schema used by the generic
monitor. Use `calibration.calibrate_thresholds(...)` to override these from
field observations after the first season.
"""

from dataclasses import dataclass
from datetime import date


SEASON_TAG = "kharif_2025"
SEASON_START = "2025-06-01"
SEASON_END = "2026-01-15"

# Weekly cadence for both optical and SAR - aligned so the UI slider snaps to
# the same week-centers used by the fetcher.
STATS_INTERVAL = "P7D"
SLIDER_STEP_DAYS = 7

# Cloud cover cap for Sentinel-2 Statistical requests. We keep this loose on
# purpose: heavy clouds are filtered pixel-by-pixel via SCL in the evalscript,
# and SAR fills in whatever S2 still misses.
MAX_CLOUD_COVER = 80

# Throttle between HTTP calls (seconds). _post_with_retry handles 429s on top.
REQUEST_THROTTLE_SECS = 0.5


@dataclass(frozen=True)
class IndexThresholds:
    healthy: float
    stress: float
    severe: float


# PB1 starting thresholds (western UP). See sources block in the module docstring.
PADDY_THRESHOLDS: dict[str, IndexThresholds] = {
    # Expected PB1 peak NDVI 0.68-0.72 at flowering (mid-Sep to early Oct).
    # 'healthy' is the reproductive-window floor below which a stand is
    # underperforming. Below 'stress' is clearly under-vigorous. Below 'severe'
    # is essentially failing.
    "NDVI": IndexThresholds(healthy=0.60, stress=0.40, severe=0.25),
    "NDRE": IndexThresholds(healthy=0.30, stress=0.18, severe=0.08),
    "NDWI": IndexThresholds(healthy=0.25, stress=0.05, severe=-0.10),
    # LSWI+0.05 >= NDVI (Xiao 2005/2006) is the transplant trigger, not a
    # stress cutoff. The triplet below is used only when LSWI falls below
    # expected wet-paddy levels outside the transplant window.
    "LSWI": IndexThresholds(healthy=0.20, stress=0.00, severe=-0.10),
    "NDMI": IndexThresholds(healthy=0.25, stress=0.10, severe=-0.05),
}

# --- Phenology-event thresholds ---

# Xiao 2006 flood signal: LSWI + LSWI_NDVI_MARGIN >= NDVI during transplant.
LSWI_NDVI_MARGIN = 0.05
LSWI_MIN_FLOOD = 0.0

# SAR VV delta (dB) vs pre-season May baseline for transplant confirmation.
# Slightly stronger drop threshold than generic paddy because aromatic growers
# typically maintain 5-10 cm standing water through tillering.
S1_VV_DB_DROP_TRANSPLANT = -2.5

# SAR VV delta (dB) over consecutive weekly readings for harvest confirmation.
S1_VV_DB_RISE_HARVEST = 1.5

# Harvest NDVI peak + drop criteria (PB1 senesces more gradually than HYVs).
HARVEST_PEAK_MIN = 0.55
HARVEST_DROP_MIN = 0.25
HARVEST_DROP_WINDOW_DAYS = 21

# Stress SAR rule: VH drop vs trailing 4-week mean, in dB.
S1_VH_STRESS_DROP_DB = -2.0
S1_VH_TRAILING_WEEKS = 4

# --- PB1 phenology calendar windows (for a late-June transplant in western UP) ---

TRANSPLANT_WINDOW = (date(2025, 6, 20), date(2025, 8, 15))
HARVEST_WINDOW = (date(2025, 11, 1), date(2025, 11, 25))

# Default transplant proxy when detection fails (mid-window default).
DEFAULT_TRANSPLANT_PROXY = date(2025, 7, 5)

# Days-after-transplant offsets for relative windows.
VEGETATIVE_OFFSET_DAYS = (15, 45)
REPRODUCTIVE_OFFSET_DAYS = (50, 100)


# Sentinel-1 evalscript parameters. Fixed descending orbit avoids
# incidence-angle drift across the time series.
S1_ACQUISITION_MODE = "IW"
S1_POLARIZATION = "DV"
S1_RESOLUTION = "HIGH"
S1_BACK_COEFF = "GAMMA0_ELLIPSOID"
S1_ORBIT_DIRECTION = "DESCENDING"


# Indices we pull in the optical backbone. Order matters: NDVI first so
# CropSAR-covered NDVI can short-circuit the rest.
OPTICAL_INDICES = ["NDVI", "LSWI", "NDWI", "NDRE"]
SAR_SIGNALS = ["S1_VV", "S1_VH", "S1_RVI"]

# Pre-season baseline window (used for VV transplant-drop comparison).
PRESEASON_BASELINE_WINDOW = (date(2025, 5, 1), date(2025, 5, 31))
