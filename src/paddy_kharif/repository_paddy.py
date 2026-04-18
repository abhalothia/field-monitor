"""DB helpers scoped to the paddy kharif offshoot.

All reads/writes here are filtered by `season_tag` (default `kharif_2025`) so
they never mix with the generic monitor's rows. Thin layer on top of the
shared `db.repository` functions — nothing here duplicates an upsert that the
generic module already owns.
"""

import json
import sqlite3

from src.models import ImageryRecord, IndexReading
from src.paddy_kharif.config import SEASON_TAG
from src.paddy_kharif.models_paddy import PaddyEvent


# ---------------------------------------------------------------------------
# Paddy events
# ---------------------------------------------------------------------------

def insert_paddy_event(
    conn: sqlite3.Connection, event: PaddyEvent,
) -> int | None:
    """Insert or upgrade a paddy event.

    The UNIQUE(field_id, event_date, event_type, season_tag) constraint makes
    re-runs of phenology detection idempotent. When a duplicate arrives, we
    keep the row but bump `confidence` to the max of old/new and merge
    evidence dicts (new keys win). Returns the event_id (or None if SQLite
    didn't surface one, e.g. on pure UPDATE).
    """
    row = conn.execute(
        """SELECT event_id, confidence, evidence FROM paddy_events
           WHERE field_id = ? AND event_date = ?
             AND event_type = ? AND season_tag = ?""",
        (event.field_id, event.event_date, event.event_type, event.season_tag),
    ).fetchone()

    if row is not None:
        old_conf = row["confidence"]
        old_evidence = json.loads(row["evidence"]) if row["evidence"] else {}
        merged_evidence = {**old_evidence, **event.evidence}
        new_conf = max(old_conf, event.confidence)
        conn.execute(
            """UPDATE paddy_events
               SET confidence = ?, evidence = ?
               WHERE event_id = ?""",
            (new_conf, json.dumps(merged_evidence), row["event_id"]),
        )
        conn.commit()
        return row["event_id"]

    cursor = conn.execute(
        """INSERT INTO paddy_events
           (field_id, event_date, event_type, confidence, evidence, season_tag)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            event.field_id, event.event_date, event.event_type,
            event.confidence, json.dumps(event.evidence), event.season_tag,
        ),
    )
    conn.commit()
    return cursor.lastrowid


def get_paddy_events(
    conn: sqlite3.Connection,
    field_id: str,
    event_type: str | None = None,
    season_tag: str = SEASON_TAG,
) -> list[PaddyEvent]:
    query = """SELECT * FROM paddy_events
               WHERE field_id = ? AND season_tag = ?"""
    params: list = [field_id, season_tag]
    if event_type:
        query += " AND event_type = ?"
        params.append(event_type)
    query += " ORDER BY event_date ASC"

    rows = conn.execute(query, params).fetchall()
    return [
        PaddyEvent(
            event_id=r["event_id"],
            field_id=r["field_id"],
            event_date=r["event_date"],
            event_type=r["event_type"],
            confidence=r["confidence"],
            evidence=json.loads(r["evidence"]) if r["evidence"] else {},
            season_tag=r["season_tag"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


def delete_paddy_events(
    conn: sqlite3.Connection,
    field_id: str,
    season_tag: str = SEASON_TAG,
) -> int:
    """Wipe a field's events for a season. Used before a full re-detect."""
    cursor = conn.execute(
        "DELETE FROM paddy_events WHERE field_id = ? AND season_tag = ?",
        (field_id, season_tag),
    )
    conn.commit()
    return cursor.rowcount


# ---------------------------------------------------------------------------
# Season-scoped reading queries
# ---------------------------------------------------------------------------

def get_season_readings(
    conn: sqlite3.Connection,
    field_id: str,
    season_tag: str = SEASON_TAG,
    index_name: str | None = None,
) -> list[IndexReading]:
    """All index readings for a field in one season, oldest first."""
    query = """SELECT * FROM index_readings
               WHERE field_id = ? AND season_tag = ?"""
    params: list = [field_id, season_tag]
    if index_name:
        query += " AND index_name = ?"
        params.append(index_name)
    query += " ORDER BY reading_date ASC"

    rows = conn.execute(query, params).fetchall()
    return [
        IndexReading(
            field_id=r["field_id"], index_name=r["index_name"],
            reading_date=r["reading_date"], mean_value=r["mean_value"],
            min_value=r["min_value"], max_value=r["max_value"],
            stdev_value=r["stdev_value"], sample_count=r["sample_count"],
            cloud_cover_pct=r["cloud_cover_pct"],
        )
        for r in rows
    ]


def get_existing_reading_dates(
    conn: sqlite3.Connection,
    field_id: str,
    index_name: str,
    season_tag: str = SEASON_TAG,
) -> set[str]:
    """Set of ISO dates already stored for (field, index, season).

    Used by the fetcher's pre-flight diff to skip weeks that are already in
    DB. Works independently of sampleCount: a zero-count row still counts as
    "we've tried this week" and we don't re-request.
    """
    rows = conn.execute(
        """SELECT reading_date FROM index_readings
           WHERE field_id = ? AND index_name = ? AND season_tag = ?""",
        (field_id, index_name, season_tag),
    ).fetchall()
    return {r["reading_date"] for r in rows}


def reading_has_valid_samples(
    conn: sqlite3.Connection,
    field_id: str,
    index_name: str,
    reading_date: str,
    season_tag: str = SEASON_TAG,
) -> bool:
    """True if a reading exists for that week AND has sampleCount > 0.

    Used by the overlay gate: no point fetching an NDVI overlay PNG for a
    week where the Statistical call already told us every pixel was clouded
    out.
    """
    row = conn.execute(
        """SELECT sample_count FROM index_readings
           WHERE field_id = ? AND index_name = ?
             AND reading_date = ? AND season_tag = ?""",
        (field_id, index_name, reading_date, season_tag),
    ).fetchone()
    return row is not None and (row["sample_count"] or 0) > 0


# ---------------------------------------------------------------------------
# Overlay imagery
# ---------------------------------------------------------------------------

def get_overlay(
    conn: sqlite3.Connection,
    field_id: str,
    image_date: str,
    image_type: str,
    season_tag: str = SEASON_TAG,
) -> ImageryRecord | None:
    row = conn.execute(
        """SELECT * FROM imagery
           WHERE field_id = ? AND image_date = ?
             AND image_type = ? AND season_tag = ?""",
        (field_id, image_date, image_type, season_tag),
    ).fetchone()
    if row is None:
        return None
    return ImageryRecord(
        field_id=row["field_id"], image_date=row["image_date"],
        image_type=row["image_type"], file_path=row["file_path"],
        width_px=row["width_px"], height_px=row["height_px"],
    )


def overlay_exists(
    conn: sqlite3.Connection,
    field_id: str,
    image_date: str,
    image_type: str,
    season_tag: str = SEASON_TAG,
) -> bool:
    return get_overlay(conn, field_id, image_date, image_type, season_tag) is not None


def list_overlays(
    conn: sqlite3.Connection,
    field_id: str,
    season_tag: str = SEASON_TAG,
) -> list[ImageryRecord]:
    """All overlay PNGs for a field in one season, ordered by date asc.

    Includes both ndvi_overlay and rvi_overlay so the timeline UI can mix
    optical and SAR fallback tiles on the same slider.
    """
    rows = conn.execute(
        """SELECT * FROM imagery
           WHERE field_id = ? AND season_tag = ?
             AND image_type IN ('ndvi_overlay', 'rvi_overlay')
           ORDER BY image_date ASC""",
        (field_id, season_tag),
    ).fetchall()
    return [
        ImageryRecord(
            field_id=r["field_id"], image_date=r["image_date"],
            image_type=r["image_type"], file_path=r["file_path"],
            width_px=r["width_px"], height_px=r["height_px"],
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Calibrated thresholds
# ---------------------------------------------------------------------------

def upsert_calibrated_thresholds(
    conn: sqlite3.Connection,
    scope: str,
    index_name: str,
    healthy: float,
    stress: float,
    severe: float,
    sample_count: int,
    season_tag: str = SEASON_TAG,
) -> None:
    """Write a calibrated (healthy, stress, severe) triplet.

    `scope` is either a field_id (per-field calibration) or a region tag
    (e.g. "western_up") when there aren't enough per-field samples.
    """
    conn.execute(
        """INSERT INTO paddy_calibrated_thresholds
           (scope, index_name, season_tag, healthy, stress, severe, sample_count)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(scope, index_name, season_tag) DO UPDATE SET
             healthy=excluded.healthy,
             stress=excluded.stress,
             severe=excluded.severe,
             sample_count=excluded.sample_count,
             updated_at=datetime('now')""",
        (scope, index_name, season_tag, healthy, stress, severe, sample_count),
    )
    conn.commit()


def get_calibrated_thresholds(
    conn: sqlite3.Connection,
    scope: str,
    index_name: str,
    season_tag: str = SEASON_TAG,
) -> tuple[float, float, float] | None:
    row = conn.execute(
        """SELECT healthy, stress, severe FROM paddy_calibrated_thresholds
           WHERE scope = ? AND index_name = ? AND season_tag = ?""",
        (scope, index_name, season_tag),
    ).fetchone()
    if row is None:
        return None
    return (row["healthy"], row["stress"], row["severe"])
