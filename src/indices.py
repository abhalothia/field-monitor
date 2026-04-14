"""Vegetation index metadata and display configuration."""

from dataclasses import dataclass

from config.settings import INDEX_THRESHOLDS, IndexThresholds


@dataclass(frozen=True)
class IndexInfo:
    name: str
    display_name: str
    formula: str
    bands: list[str]
    description: str
    color: str  # plotly color for charting
    thresholds: IndexThresholds


INDEX_CATALOG: dict[str, IndexInfo] = {
    "NDVI": IndexInfo(
        name="NDVI",
        display_name="Vegetation health (NDVI)",
        formula="(B08-B04)/(B08+B04)",
        bands=["B04", "B08"],
        description="General vegetation vigor and chlorophyll density",
        color="#2ca02c",
        thresholds=INDEX_THRESHOLDS["NDVI"],
    ),
    "NDRE": IndexInfo(
        name="NDRE",
        display_name="Red edge stress (NDRE)",
        formula="(B08-B05)/(B08+B05)",
        bands=["B05", "B08"],
        description="Chlorophyll and nitrogen content, early disease indicator",
        color="#d62728",
        thresholds=INDEX_THRESHOLDS["NDRE"],
    ),
    "NDWI": IndexInfo(
        name="NDWI",
        display_name="Water content (NDWI)",
        formula="(B08-B11)/(B08+B11)",
        bands=["B08", "B11"],
        description="Canopy water content and drought stress",
        color="#1f77b4",
        thresholds=INDEX_THRESHOLDS["NDWI"],
    ),
    "EVI": IndexInfo(
        name="EVI",
        display_name="Enhanced vegetation (EVI)",
        formula="2.5*((B08-B04)/(B08+6*B04-7.5*B02+1))",
        bands=["B02", "B04", "B08"],
        description="Canopy structure, corrected for atmosphere and soil",
        color="#9467bd",
        thresholds=INDEX_THRESHOLDS["EVI"],
    ),
    "SAVI": IndexInfo(
        name="SAVI",
        display_name="Soil-adjusted (SAVI)",
        formula="((B08-B04)/(B08+B04+0.428))*1.428",
        bands=["B04", "B08"],
        description="Vegetation health with soil brightness correction",
        color="#8c564b",
        thresholds=INDEX_THRESHOLDS["SAVI"],
    ),
    "NDMI": IndexInfo(
        name="NDMI",
        display_name="Leaf moisture (NDMI)",
        formula="(B8A-B11)/(B8A+B11)",
        bands=["B8A", "B11"],
        description="Leaf moisture content and irrigation effectiveness",
        color="#17becf",
        thresholds=INDEX_THRESHOLDS["NDMI"],
    ),
}

ALL_INDEX_NAMES = list(INDEX_CATALOG.keys())
