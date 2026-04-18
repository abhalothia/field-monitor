#!/usr/bin/env python3
"""CLI: fetch the paddy kharif 2025 season for one field or all fields.

Usage:
  python -m scripts.fetch_paddy_kharif                    # all registered fields
  python -m scripts.fetch_paddy_kharif --field-id abc123  # one field
  python -m scripts.fetch_paddy_kharif --field-id abc123 --no-detect

This reuses the generic field registry (fields are shared between the generic
monitor and the paddy offshoot) and writes all paddy-specific rows with
`season_tag='kharif_2025'`.
"""

import argparse
import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import DB_PATH, get_sentinel_config
from db.repository import get_all_fields, get_field
from db.schema import create_tables
from src.paddy_kharif.paddy_fetcher import fetch_kharif_season


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch paddy kharif 2025 season data (full Jun 1 - Jan 15 window).",
    )
    parser.add_argument(
        "--field-id", default=None,
        help="Field ID to fetch. Omit to process every registered field.",
    )
    parser.add_argument(
        "--year", type=int, default=2025,
        help="Season year (only 2025 supported today).",
    )
    parser.add_argument(
        "--no-detect", action="store_true",
        help="Skip the phenology detection pass after ingestion.",
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

    if args.field_id:
        field = get_field(conn, args.field_id)
        if field is None:
            print(f"Field {args.field_id} not registered.", file=sys.stderr)
            return 2
        fields = [field]
    else:
        fields = get_all_fields(conn)
        if not fields:
            print(
                "No fields registered. Add fields via the dashboard first.",
                file=sys.stderr,
            )
            return 2

    exit_code = 0
    for field in fields:
        print(f"\n=== Paddy kharif {args.year}: {field.name} ({field.field_id}) ===")
        try:
            summary = fetch_kharif_season(
                conn, field, config,
                year=args.year, run_detect=not args.no_detect,
            )
        except Exception as exc:
            print(f"  FAILED: {exc}", file=sys.stderr)
            exit_code = 1
            continue

        print(f"  API requests:        {summary['api_requests']}")
        print(f"  Readings stored:     {summary['readings_stored']}")
        print(f"  NDVI overlays:       {summary['overlays_ndvi']}")
        print(f"  RVI overlays:        {summary['overlays_rvi']}")
        print(f"  CropSAR used:        {summary['cropsar_used']}")
        if summary.get("events_detected") is not None:
            print(f"  Events detected:     {summary['events_detected']}")
        if summary["errors"]:
            print(f"  Errors ({len(summary['errors'])}):")
            for err in summary["errors"][:10]:
                print(f"    - {err}")

    conn.close()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
