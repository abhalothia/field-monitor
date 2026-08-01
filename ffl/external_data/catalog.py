"""The deliberate three-phase external-data inventory.

The catalog is an admission-control list, not a promise to fetch every source.
An entry is only an implementation candidate until it has a provider-specific
adapter, licence review, coverage mapping, and owner approval.
"""

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class ExternalDataSource:
    source_key: str
    phase: int
    title: str
    source_kind: str
    authority: str
    purpose: str
    enabled_by_default: bool
    admission_gate: str


EXTERNAL_DATA_PHASES = (
    (1, "reference geography and first-party evidence"),
    (2, "official operational context"),
    (3, "reviewed contextual enrichment"),
)


_SOURCES: Tuple[ExternalDataSource, ...] = (
    ExternalDataSource(
        "village-finder-lgd", 1, "India Village Finder LGD reference pack", "reference_dataset",
        "lgd-derived", "verified village, district, PIN, and local-language location lookup", False,
        "pin a reviewed release, retain its hash and GODL-India attribution, then require human location binding",
    ),
    ExternalDataSource(
        "soil-lab-first-party", 1, "FFL soil laboratory evidence", "first_party_import",
        "first_party", "soil baseline and season/trial learning", False,
        "retain original report and require a reviewer to map sample, unit, depth, and parcel",
    ),
    ExternalDataSource(
        "imd-weather", 2, "India Meteorological Department", "official_context",
        "official", "district warnings, nowcasts, forecasts, and agromet references", False,
        "IMD access review, fixed egress/IP whitelisting, official endpoint allow-list, and district mapping",
    ),
    ExternalDataSource(
        "agmarknet-market-context", 3, "AGMARKNET mandi context", "official_context",
        "official", "daily mandi arrivals and price context", False,
        "approved programmatic route, commodity/market mapping, and no realised-price substitution",
    ),
    ExternalDataSource(
        "copernicus-sentinel", 3, "Copernicus Sentinel context", "remote_sensing",
        "official", "field-change corroboration", False,
        "private geometry model, access review, cloud/quality policy, and human-review workflow",
    ),
    ExternalDataSource(
        "bhuvan-groundwater", 3, "Bhuvan groundwater context", "remote_sensing",
        "official", "regional groundwater prospect context", False,
        "provider terms review, permitted coverage, and no parcel-level conclusion",
    ),
    ExternalDataSource(
        "soilgrids", 3, "ISRIC SoilGrids context", "model_context",
        "partner", "coarse soil-class context", False,
        "licence review and UI labels that make clear it is a model estimate, not soil truth",
    ),
    ExternalDataSource(
        "myscheme", 3, "myScheme reference", "official_context",
        "official", "programme discovery", False,
        "provider terms and link-only review; never infer eligibility or submit an application",
    ),
)


def external_data_sources(phase: Optional[int] = None) -> Tuple[ExternalDataSource, ...]:
    """Return sources known to FFL without enabling I/O or credentials."""
    if phase is None:
        return _SOURCES
    if phase not in {item[0] for item in EXTERNAL_DATA_PHASES}:
        raise ValueError("external-data phase must be 1, 2, or 3")
    return tuple(source for source in _SOURCES if source.phase == phase)
