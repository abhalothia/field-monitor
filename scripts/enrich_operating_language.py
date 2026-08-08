#!/usr/bin/env python3
"""Build the bounded, review-first Hindi operating-language packs.

The command sees only controlled vocabulary display labels and place components.
It never receives people, contacts, source identifiers, coordinates, photos,
or complete source records.  Suggestions remain private until reviewed.
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
from ffl.services import operating_language
from ffl.services.trackwick_ingest import SOURCE_KEY


def _database_url() -> str | None:
    return (
        os.environ.get("FFL_ENRICHMENT_DATABASE_URL")
        or os.environ.get("FFL_POSTGRES_DIRECT_URL")
        or os.environ.get("FFL_DATABASE_URL")
        or os.environ.get("FFL_POSTGRES_DATABASE_URL")
    )


def _run_batches(callback, batches: int) -> list[dict]:
    results = []
    consecutive_invalid_results = 0
    for _ in range(batches):
        result = callback()
        results.append(result)
        if result["state"] in {"unavailable", "nothing_pending"}:
            break
        if result["state"] == "no_safe_suggestions":
            # A malformed model response must never be persisted. Retry the
            # same tiny fact pack a couple of times before leaving it for a
            # later explicit run; this prevents one transient response from
            # stopping a complete one-time pass.
            consecutive_invalid_results += 1
            if consecutive_invalid_results >= 3:
                break
        else:
            consecutive_invalid_results = 0
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Call Gemini and save private reviewable suggestions")
    parser.add_argument("--limit", type=int, default=8, help="Terms/places per Gemini request (1-8)")
    parser.add_argument("--batches", type=int, default=1, help="Batches per language pack (1-40)")
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
        if not operating_language.language_schema_available(conn):
            print(json.dumps({"state": "language_schema_unavailable"}, sort_keys=True))
            return 1
        batches = max(1, min(int(args.batches), 40))
        groups = operating_language.refresh_issue_group_proposals(conn, source.id)
        if not args.apply:
            print(json.dumps({
                "state": "discovered", "issue_groups_refreshed": groups,
                "summary": operating_language.language_summary(conn, source.id),
            }, sort_keys=True))
            return 0
        vocabulary = _run_batches(
            lambda: operating_language.suggest_hindi_vocabulary_localizations(
                conn, source.id, limit=args.limit,
            ),
            batches,
        )
        places = _run_batches(
            lambda: operating_language.suggest_hindi_place_localizations(
                conn, source.id, limit=args.limit,
            ),
            batches,
        )
        groups = operating_language.refresh_issue_group_proposals(conn, source.id)
        print(json.dumps({
            "state": "complete", "vocabulary_batches": len(vocabulary),
            "place_batches": len(places), "issue_groups_refreshed": groups,
            "summary": operating_language.language_summary(conn, source.id),
        }, sort_keys=True))
        return 0 if all(
            result["state"] != "unavailable" for result in [*vocabulary, *places]
        ) else 2
    except Exception:
        conn.rollback()
        print(json.dumps({"state": "failed"}, sort_keys=True))
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
