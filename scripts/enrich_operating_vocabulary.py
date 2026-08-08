#!/usr/bin/env python3
"""Run one bounded, reviewable Gemini vocabulary pass against the private DB.

Normal imports already discover source vocabulary.  This command is the only
path that can call a model, and it stores suggestions rather than changing
operating facts or browser-visible filters.  It accepts no entity IDs and
prints only an aggregate receipt.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ffl.persistence import repository
from ffl.persistence.database import DatabaseConfigurationError, database_target, open_connection
from ffl.services import operating_vocabulary
from ffl.services.trackwick_ingest import SOURCE_KEY


def _database_url() -> str | None:
    return (
        os.environ.get("FFL_ENRICHMENT_DATABASE_URL")
        or os.environ.get("FFL_POSTGRES_DIRECT_URL")
        or os.environ.get("FFL_DATABASE_URL")
        or os.environ.get("FFL_POSTGRES_DATABASE_URL")
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Call Gemini and save reviewable suggestions")
    parser.add_argument("--limit", type=int, default=8, help="Maximum unresolved terms to consider (1-8)")
    args = parser.parse_args()
    try:
        target = database_target(database_url=_database_url())
        if target.dialect != "postgres":
            raise DatabaseConfigurationError("A private PostgreSQL connection is required")
        conn = open_connection(target)
    except DatabaseConfigurationError:
        print(json.dumps({"state": "database_unavailable"}, sort_keys=True))
        return 1
    try:
        source = repository.get_source_registry_by_key(conn, SOURCE_KEY)
        if source is None:
            print(json.dumps({"state": "no_source"}, sort_keys=True))
            return 0
        operating_vocabulary.refresh_source_vocabulary(conn, source.id, commit=False)
        before = operating_vocabulary.vocabulary_summary(conn, source.id)
        if not args.apply:
            conn.commit()
            print(json.dumps({"state": "discovered", "summary": before}, sort_keys=True))
            return 0
        result = operating_vocabulary.suggest_pending_terms(
            conn, source.id, limit=args.limit, commit=False,
        )
        conn.commit()
        print(json.dumps({"state": result["state"], "result": result,
                          "summary": operating_vocabulary.vocabulary_summary(conn, source.id)}, sort_keys=True))
        return 0 if result["state"] != "unavailable" else 2
    except Exception:
        conn.rollback()
        print(json.dumps({"state": "failed"}, sort_keys=True))
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
