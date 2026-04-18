"""Dataclasses specific to paddy kharif monitoring."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PaddyEvent:
    """A phenology or stress event detected from index time series.

    event_type:
        'transplanting' | 'harvesting' | 'stress' | 'flood' | 'drought'
    confidence:
        0.6 for a single-path detection (optical OR SAR alone)
        0.7 for a single-path SAR detection (SAR has fewer false positives)
        0.9-0.95 for dual-path confirmed detections
    evidence:
        JSON-serialisable dict describing the numeric signal(s) that triggered
        the event. E.g. {"lswi": 0.22, "ndvi": 0.15, "vv_drop_db": -3.1,
        "path": "optical+sar"}.
    """
    field_id: str
    event_date: str  # ISO YYYY-MM-DD
    event_type: str
    confidence: float
    evidence: dict = field(default_factory=dict)
    season_tag: str = "kharif_2025"
    event_id: int | None = None
    created_at: str | None = None
