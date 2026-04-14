"""Parse KML files and extract named polygon placemarks."""

from pathlib import Path

from lxml import etree

KML_NS = "http://www.opengis.net/kml/2.2"
NSMAP = {"kml": KML_NS}


def parse_polygon_coordinates(
    kml_path: str | Path,
    placemark_name: str,
) -> list[tuple[float, float]]:
    """Extract polygon coordinates for a named placemark.

    Returns a list of (longitude, latitude) tuples forming the outer ring.
    Raises ValueError if the placemark is not found or has no polygon.
    """
    tree = etree.parse(str(kml_path))
    root = tree.getroot()

    placemarks = root.findall(".//kml:Placemark", NSMAP)
    for pm in placemarks:
        name_el = pm.find("kml:name", NSMAP)
        if name_el is None or name_el.text != placemark_name:
            continue

        coords_el = pm.find(
            ".//kml:Polygon/kml:outerBoundaryIs/kml:LinearRing/kml:coordinates",
            NSMAP,
        )
        if coords_el is None:
            raise ValueError(
                f"Placemark '{placemark_name}' exists but has no polygon."
            )

        return _parse_coordinate_string(coords_el.text)

    available = [
        pm.find("kml:name", NSMAP).text
        for pm in placemarks
        if pm.find("kml:name", NSMAP) is not None
    ]
    raise ValueError(
        f"Placemark '{placemark_name}' not found. "
        f"Available: {available}"
    )


def list_placemarks(kml_path: str | Path) -> list[str]:
    """Return all placemark names in the KML file."""
    tree = etree.parse(str(kml_path))
    root = tree.getroot()
    placemarks = root.findall(".//kml:Placemark", NSMAP)
    names = []
    for pm in placemarks:
        name_el = pm.find("kml:name", NSMAP)
        if name_el is not None and name_el.text:
            names.append(name_el.text)
    return names


def _parse_coordinate_string(raw: str) -> list[tuple[float, float]]:
    """Parse 'lon,lat,alt lon,lat,alt ...' into [(lon, lat), ...]."""
    coords = []
    for token in raw.strip().split():
        parts = token.split(",")
        if len(parts) < 2:
            continue
        lon = float(parts[0])
        lat = float(parts[1])
        coords.append((lon, lat))
    return coords
