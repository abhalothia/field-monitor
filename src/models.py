"""Domain dataclasses used across the application."""

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(frozen=True)
class FieldPolygon:
    field_id: str
    name: str
    coordinates: list[tuple[float, float]]  # [(lon, lat), ...]
    center_lon: float
    center_lat: float
    area_hectares: float
    polygon_wkt: str
    polygon_geojson: dict


@dataclass(frozen=True)
class IndexReading:
    field_id: str
    index_name: str
    reading_date: str  # ISO YYYY-MM-DD
    mean_value: float | None
    min_value: float | None
    max_value: float | None
    stdev_value: float | None
    sample_count: int | None
    cloud_cover_pct: float | None


@dataclass(frozen=True)
class ImageryRecord:
    field_id: str
    image_date: str
    image_type: str  # 'true_color', 'false_color', 'ndvi_map', etc.
    file_path: str
    width_px: int | None = None
    height_px: int | None = None


@dataclass(frozen=True)
class AnomalyAlert:
    field_id: str
    alert_date: str
    index_name: str
    alert_type: str  # 'sudden_drop', 'below_threshold', 'trend_decline'
    severity: str    # 'low', 'medium', 'high', 'critical'
    current_value: float
    baseline_value: float | None
    deviation: float | None
    message: str
    is_acknowledged: bool = False
    id: int | None = None


@dataclass(frozen=True)
class RiskAssessment:
    field_id: str
    assessment_date: str
    overall_score: float
    pest_risk: float
    disease_risk: float
    water_stress: float
    nutrient_stress: float
    contributing_factors: list[str]


@dataclass(frozen=True)
class GroundObservation:
    field_id: str
    observation_date: str
    category: str   # 'pest', 'disease', 'weed', 'nutrient', 'water', 'other'
    severity: str   # 'none', 'low', 'medium', 'high'
    description: str
    affected_area_pct: float | None = None
    photo_path: str | None = None
    id: int | None = None


@dataclass(frozen=True)
class FetchLogEntry:
    field_id: str
    fetch_type: str  # 'statistics', 'imagery', 'catalog'
    date_from: str
    date_to: str
    status: str      # 'success', 'partial', 'failed'
    error_message: str | None = None
    scenes_found: int | None = None
    records_stored: int | None = None
    duration_secs: float | None = None
