"""Bounded, provenance-first external-data building blocks for FFL."""

from ffl.external_data.catalog import EXTERNAL_DATA_PHASES, external_data_sources
from ffl.external_data.geography import (
    VILLAGE_FINDER_REPOSITORY,
    GeographyDataset,
    GeographyImport,
    Place,
    fetch_village_finder_csv,
    parse_village_finder_csv,
)

__all__ = [
    "EXTERNAL_DATA_PHASES",
    "GeographyDataset",
    "GeographyImport",
    "Place",
    "VILLAGE_FINDER_REPOSITORY",
    "external_data_sources",
    "fetch_village_finder_csv",
    "parse_village_finder_csv",
]
