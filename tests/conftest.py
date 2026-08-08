"""Shared test fixtures and factory functions."""

import os
import sqlite3
import tempfile
from pathlib import Path

import pytest


# Ensure dotenv loads from project root
os.environ.setdefault("SENTINEL_HUB_CLIENT_ID", "test-client-id")
os.environ.setdefault("SENTINEL_HUB_CLIENT_SECRET", "test-client-secret")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
KML_PATH = PROJECT_ROOT / "tests" / "fixtures" / "legacy-fields.kml"


UNTITLED_POLYGON_COORDS = [
    (77.81393119925725, 28.09170424616262),
    (77.81400403886089, 28.09165679811246),
    (77.81441502722812, 28.09200071130502),
    (77.81382517591547, 28.09244514583643),
    (77.81351367346001, 28.09217715050744),
    (77.81393119925725, 28.09170424616262),
]


@pytest.fixture
def kml_path() -> Path:
    return KML_PATH


@pytest.fixture
def sample_coordinates() -> list[tuple[float, float]]:
    return UNTITLED_POLYGON_COORDS.copy()


@pytest.fixture
def in_memory_db():
    """Provide a fresh in-memory SQLite connection."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()
