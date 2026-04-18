#!/usr/bin/env python3
"""Initialize the database and register the field from KML."""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import DB_PATH, FIELD_NAME, KML_PATH
from db.schema import create_tables
from db.repository import upsert_field
from src.kml_parser import parse_polygon_coordinates
from src.geometry import build_field_polygon


def main():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    create_tables(conn)

    # Optionally import the legacy KML field if the file is present.
    if KML_PATH.exists():
        print(f"KML file: {KML_PATH}")
        print(f"Field name: {FIELD_NAME}")
        coords = parse_polygon_coordinates(KML_PATH, FIELD_NAME)
        print(f"Parsed {len(coords)} coordinate pairs")
        field = build_field_polygon(FIELD_NAME, coords, field_id="mandi_field_01")
        print(f"Field area: {field.area_hectares} hectares")
        print(f"Center: {field.center_lat:.6f}N, {field.center_lon:.6f}E")
        upsert_field(conn, field)
        print("Legacy KML field registered.")
    else:
        print(f"No legacy KML at {KML_PATH} — skipping KML import.")
        print("You can create fields from the dashboard (Fields page).")

    conn.close()
    print(f"Database initialized at {DB_PATH}")


if __name__ == "__main__":
    main()
