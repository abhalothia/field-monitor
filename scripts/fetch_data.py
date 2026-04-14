#!/usr/bin/env python3
"""CLI script for manual data fetch from Sentinel Hub."""

import argparse
import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import DB_PATH, DEFAULT_LOOKBACK_DAYS, FIELD_NAME, KML_PATH, get_sentinel_config
from db.schema import create_tables
from db.repository import get_all_fields, upsert_field
from src.data_fetcher import fetch_and_analyze
from src.geometry import build_field_polygon
from src.kml_parser import parse_polygon_coordinates


def main():
    parser = argparse.ArgumentParser(description="Fetch satellite data for field monitoring")
    parser.add_argument(
        "--lookback", type=int, default=DEFAULT_LOOKBACK_DAYS,
        help=f"Days of history to fetch (default: {DEFAULT_LOOKBACK_DAYS})",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = get_sentinel_config()

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    create_tables(conn)

    fields = get_all_fields(conn)
    if not fields:
        logging.info("No fields registered, loading from KML...")
        coords = parse_polygon_coordinates(KML_PATH, FIELD_NAME)
        field = build_field_polygon(FIELD_NAME, coords, field_id="mandi_field_01")
        upsert_field(conn, field)
        fields = [field]

    for field in fields:
        logging.info("Fetching data for: %s (%.2f ha)", field.name, field.area_hectares)
        summary = fetch_and_analyze(conn, field, config, lookback_days=args.lookback)
        print(f"\nResults for {field.name}:")
        print(f"  Readings stored: {summary['readings_stored']}")
        print(f"  Alerts generated: {summary['alerts_generated']}")
        print(f"  Images saved: {summary['images_saved']}")
        if summary["errors"]:
            print(f"  Errors: {len(summary['errors'])}")
            for err in summary["errors"]:
                print(f"    - {err}")

    conn.close()


if __name__ == "__main__":
    main()
