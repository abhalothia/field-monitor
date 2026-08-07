#!/usr/bin/env python3
"""Build the private operating snapshot once after its reviewed migration.

This is intentionally a local maintenance command, not an HTTP route.  It
accepts no entity identifiers, writes no canonical records, and prints only a
safe aggregate receipt.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ffl.persistence import repository
from ffl.persistence.database import DatabaseConfigurationError, database_target, open_connection
from ffl.services.operating_enrichment import refresh_source_snapshots
from ffl.services.trackwick_ingest import SOURCE_KEY


def _database_url() -> str | None:
    """Prefer the direct private connection for one bounded backfill."""
    return (
        os.environ.get("FFL_ENRICHMENT_DATABASE_URL")
        or os.environ.get("FFL_POSTGRES_DIRECT_URL")
        or os.environ.get("FFL_DATABASE_URL")
        or os.environ.get("FFL_POSTGRES_DATABASE_URL")
    )


def main() -> int:
    try:
        target = database_target(database_url=_database_url())
        if target.dialect != "postgres":
            raise DatabaseConfigurationError("A private PostgreSQL connection is required for this backfill")
        conn = open_connection(target)
    except DatabaseConfigurationError:
        print("operating snapshot backfill could not open the private database", file=sys.stderr)
        return 1

    try:
        source = repository.get_source_registry_by_key(conn, SOURCE_KEY)
        if source is None:
            print(json.dumps({"state": "no_source", "snapshots": 0}, sort_keys=True))
            return 0
        latest_run = conn.execute(
            "SELECT id FROM source_runs WHERE source_id = ? ORDER BY created_at DESC LIMIT 1",
            (source.id,),
        ).fetchone()
        snapshots = refresh_source_snapshots(
            conn,
            source.id,
            source_run_id=None if latest_run is None else str(latest_run["id"]),
        )
        print(json.dumps({"state": "refreshed", "snapshots": snapshots}, sort_keys=True))
        return 0
    except Exception:
        conn.rollback()
        print("operating snapshot backfill failed", file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
