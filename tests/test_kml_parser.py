"""Tests for KML parsing behavior."""

import pytest

from src.kml_parser import list_placemarks, parse_polygon_coordinates
from tests.conftest import KML_PATH, UNTITLED_POLYGON_COORDS


class TestParsePolygonCoordinates:
    def test_extracts_untitled_polygon(self):
        coords = parse_polygon_coordinates(KML_PATH, "Untitled polygon")

        assert len(coords) == 6
        assert coords[0] == coords[-1], "Polygon should be closed"

    def test_coordinates_match_expected_values(self):
        coords = parse_polygon_coordinates(KML_PATH, "Untitled polygon")

        for actual, expected in zip(coords, UNTITLED_POLYGON_COORDS):
            assert actual[0] == pytest.approx(expected[0], abs=1e-10)
            assert actual[1] == pytest.approx(expected[1], abs=1e-10)

    def test_coordinates_are_in_delhi_ncr_region(self):
        coords = parse_polygon_coordinates(KML_PATH, "Untitled polygon")

        for lon, lat in coords:
            assert 77.0 < lon < 78.0, f"Longitude {lon} outside Delhi region"
            assert 28.0 < lat < 29.0, f"Latitude {lat} outside Delhi region"

    def test_extracts_other_polygon_by_name(self):
        coords = parse_polygon_coordinates(KML_PATH, "new option 10 acre farm")

        assert len(coords) > 3
        assert coords[0] == coords[-1], "Polygon should be closed"

    def test_raises_for_unknown_placemark(self):
        with pytest.raises(ValueError, match="not found"):
            parse_polygon_coordinates(KML_PATH, "Nonexistent field")

    def test_error_lists_available_placemarks(self):
        with pytest.raises(ValueError, match="Untitled polygon"):
            parse_polygon_coordinates(KML_PATH, "Nonexistent field")


class TestListPlacemarks:
    def test_returns_all_placemark_names(self):
        names = list_placemarks(KML_PATH)

        assert "Untitled polygon" in names
        assert "new option 10 acre farm" in names
        assert len(names) == 2
