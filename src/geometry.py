"""Shapely geometry utilities and GeoJSON conversion."""

import uuid

from shapely.geometry import Polygon, mapping
from shapely.ops import transform

from src.models import FieldPolygon


def build_field_polygon(
    name: str,
    coordinates: list[tuple[float, float]],
    field_id: str | None = None,
) -> FieldPolygon:
    """Create a FieldPolygon from (lon, lat) coordinate pairs.

    Computes centroid, area, WKT, and GeoJSON for the polygon.
    """
    if field_id is None:
        field_id = uuid.uuid4().hex[:12]

    polygon = Polygon(coordinates)
    centroid = polygon.centroid
    area_ha = _approx_area_hectares(polygon)
    geojson = _to_geojson_geometry(polygon)

    return FieldPolygon(
        field_id=field_id,
        name=name,
        coordinates=coordinates,
        center_lon=centroid.x,
        center_lat=centroid.y,
        area_hectares=round(area_ha, 4),
        polygon_wkt=polygon.wkt,
        polygon_geojson=geojson,
    )


def _to_geojson_geometry(polygon: Polygon) -> dict:
    """Convert Shapely polygon to GeoJSON geometry dict.

    Returns the format Sentinel Hub expects:
    {"type": "Polygon", "coordinates": [[[lon, lat], ...]]}
    """
    return mapping(polygon)


def _approx_area_hectares(polygon: Polygon) -> float:
    """Approximate polygon area in hectares using a local projection.

    Uses a simple cos(lat) correction for longitude at the polygon's
    latitude. Good enough for small polygons near the equator to mid-latitudes.
    """
    import math

    centroid = polygon.centroid
    lat_rad = math.radians(centroid.y)
    cos_lat = math.cos(lat_rad)

    # Degrees to meters (approximate)
    deg_to_m_lat = 111_320.0
    deg_to_m_lon = 111_320.0 * cos_lat

    def project(lon: float, lat: float) -> tuple[float, float]:
        return (lon * deg_to_m_lon, lat * deg_to_m_lat)

    projected = transform(project, polygon)
    area_m2 = projected.area
    return area_m2 / 10_000.0


def get_bbox(coordinates: list[tuple[float, float]]) -> list[float]:
    """Return [min_lon, min_lat, max_lon, max_lat] bounding box."""
    lons = [c[0] for c in coordinates]
    lats = [c[1] for c in coordinates]
    return [min(lons), min(lats), max(lons), max(lats)]
