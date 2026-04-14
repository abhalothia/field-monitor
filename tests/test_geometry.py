"""Tests for geometry utilities."""

import pytest

from src.geometry import build_field_polygon, get_bbox
from tests.conftest import UNTITLED_POLYGON_COORDS


class TestBuildFieldPolygon:
    def test_creates_polygon_with_correct_name(self):
        fp = build_field_polygon("Test field", UNTITLED_POLYGON_COORDS)

        assert fp.name == "Test field"

    def test_computes_centroid_in_field_region(self):
        fp = build_field_polygon("Test", UNTITLED_POLYGON_COORDS)

        assert 77.81 < fp.center_lon < 77.82
        assert 28.09 < fp.center_lat < 28.10

    def test_area_is_reasonable_for_small_field(self):
        fp = build_field_polygon("Test", UNTITLED_POLYGON_COORDS)

        # Field should be roughly 0.2-0.6 hectares
        assert 0.1 < fp.area_hectares < 1.0

    def test_generates_valid_geojson(self):
        fp = build_field_polygon("Test", UNTITLED_POLYGON_COORDS)

        assert fp.polygon_geojson["type"] == "Polygon"
        assert len(fp.polygon_geojson["coordinates"]) == 1
        ring = fp.polygon_geojson["coordinates"][0]
        assert len(ring) == 6

    def test_geojson_coordinates_are_lon_lat_order(self):
        fp = build_field_polygon("Test", UNTITLED_POLYGON_COORDS)

        first_point = fp.polygon_geojson["coordinates"][0][0]
        assert 77.0 < first_point[0] < 78.0, "First coord should be longitude"
        assert 28.0 < first_point[1] < 29.0, "Second coord should be latitude"

    def test_wkt_contains_polygon(self):
        fp = build_field_polygon("Test", UNTITLED_POLYGON_COORDS)

        assert fp.polygon_wkt.startswith("POLYGON")

    def test_preserves_coordinates(self):
        fp = build_field_polygon("Test", UNTITLED_POLYGON_COORDS)

        assert fp.coordinates == UNTITLED_POLYGON_COORDS

    def test_uses_provided_field_id(self):
        fp = build_field_polygon("Test", UNTITLED_POLYGON_COORDS, field_id="abc123")

        assert fp.field_id == "abc123"

    def test_generates_field_id_when_not_provided(self):
        fp = build_field_polygon("Test", UNTITLED_POLYGON_COORDS)

        assert len(fp.field_id) == 12


class TestGetBbox:
    def test_returns_correct_bounding_box(self):
        bbox = get_bbox(UNTITLED_POLYGON_COORDS)

        assert len(bbox) == 4
        min_lon, min_lat, max_lon, max_lat = bbox
        assert min_lon < max_lon
        assert min_lat < max_lat

    def test_bbox_contains_all_points(self):
        bbox = get_bbox(UNTITLED_POLYGON_COORDS)
        min_lon, min_lat, max_lon, max_lat = bbox

        for lon, lat in UNTITLED_POLYGON_COORDS:
            assert min_lon <= lon <= max_lon
            assert min_lat <= lat <= max_lat
