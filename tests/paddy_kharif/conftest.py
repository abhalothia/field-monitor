"""Fixtures shared by paddy_kharif tests."""

import sqlite3

import pytest

from db.schema import create_tables
from src.models import FieldPolygon


FIELD_ID = "test_pb1"


@pytest.fixture
def paddy_db():
    """Fresh in-memory SQLite with the full schema (including season_tag)."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_tables(conn)
    yield conn
    conn.close()


@pytest.fixture
def test_field():
    # Small synthetic polygon somewhere in Bulandshahr, UP.
    coords = [
        (77.85, 28.40), (77.86, 28.40),
        (77.86, 28.41), (77.85, 28.41),
        (77.85, 28.40),
    ]
    geojson = {"type": "Polygon", "coordinates": [[list(c) for c in coords]]}
    return FieldPolygon(
        field_id=FIELD_ID,
        name="PB1 test plot",
        coordinates=coords,
        center_lat=28.405,
        center_lon=77.855,
        area_hectares=1.0,
        polygon_wkt="POLYGON((...))",
        polygon_geojson=geojson,
    )
