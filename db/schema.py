"""SQLite schema creation."""

import sqlite3

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS fields (
    field_id        TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    polygon_wkt     TEXT NOT NULL,
    polygon_geojson TEXT NOT NULL,
    center_lat      REAL NOT NULL,
    center_lon      REAL NOT NULL,
    area_hectares   REAL NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS index_readings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    field_id        TEXT NOT NULL REFERENCES fields(field_id),
    index_name      TEXT NOT NULL,
    reading_date    TEXT NOT NULL,
    mean_value      REAL,
    min_value       REAL,
    max_value       REAL,
    stdev_value     REAL,
    sample_count    INTEGER,
    cloud_cover_pct REAL,
    season_tag      TEXT NOT NULL DEFAULT 'generic',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(field_id, index_name, reading_date, season_tag)
);

CREATE TABLE IF NOT EXISTS imagery (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    field_id        TEXT NOT NULL REFERENCES fields(field_id),
    image_date      TEXT NOT NULL,
    image_type      TEXT NOT NULL,
    file_path       TEXT NOT NULL,
    width_px        INTEGER,
    height_px       INTEGER,
    season_tag      TEXT NOT NULL DEFAULT 'generic',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(field_id, image_date, image_type, season_tag)
);

CREATE TABLE IF NOT EXISTS alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    field_id        TEXT NOT NULL REFERENCES fields(field_id),
    alert_date      TEXT NOT NULL,
    index_name      TEXT NOT NULL,
    alert_type      TEXT NOT NULL,
    severity        TEXT NOT NULL,
    current_value   REAL NOT NULL,
    baseline_value  REAL,
    deviation       REAL,
    message         TEXT NOT NULL,
    is_acknowledged INTEGER DEFAULT 0,
    season_tag      TEXT NOT NULL DEFAULT 'generic',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS risk_assessments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    field_id        TEXT NOT NULL REFERENCES fields(field_id),
    assessment_date TEXT NOT NULL,
    overall_score   REAL NOT NULL,
    pest_risk       REAL NOT NULL,
    disease_risk    REAL NOT NULL,
    water_stress    REAL NOT NULL,
    nutrient_stress REAL NOT NULL,
    contributing_factors TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(field_id, assessment_date)
);

CREATE TABLE IF NOT EXISTS observations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    field_id        TEXT NOT NULL REFERENCES fields(field_id),
    observation_date TEXT NOT NULL,
    category        TEXT NOT NULL,
    severity        TEXT NOT NULL,
    description     TEXT NOT NULL,
    affected_area_pct REAL,
    photo_path      TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS fetch_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    field_id        TEXT NOT NULL REFERENCES fields(field_id),
    fetch_type      TEXT NOT NULL,
    date_from       TEXT NOT NULL,
    date_to         TEXT NOT NULL,
    status          TEXT NOT NULL,
    error_message   TEXT,
    scenes_found    INTEGER,
    records_stored  INTEGER,
    duration_secs   REAL,
    season_tag      TEXT NOT NULL DEFAULT 'generic',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS paddy_events (
    event_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    field_id        TEXT NOT NULL REFERENCES fields(field_id),
    event_date      TEXT NOT NULL,
    event_type      TEXT NOT NULL CHECK(event_type IN
        ('transplanting','harvesting','stress','flood','drought')),
    confidence      REAL NOT NULL,
    evidence        TEXT,
    season_tag      TEXT NOT NULL DEFAULT 'kharif_2025',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(field_id, event_date, event_type, season_tag)
);

CREATE TABLE IF NOT EXISTS paddy_calibrated_thresholds (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    scope           TEXT NOT NULL,
    index_name      TEXT NOT NULL,
    season_tag      TEXT NOT NULL,
    healthy         REAL NOT NULL,
    stress          REAL NOT NULL,
    severe          REAL NOT NULL,
    sample_count    INTEGER NOT NULL,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(scope, index_name, season_tag)
);

CREATE TABLE IF NOT EXISTS crop_detections (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    field_id        TEXT NOT NULL REFERENCES fields(field_id),
    detection_date  TEXT NOT NULL,
    season_start    TEXT NOT NULL,
    season_end      TEXT NOT NULL,
    crop_type       TEXT NOT NULL,
    confidence      REAL,
    pixel_counts    TEXT,
    geotiff_path    TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_readings_field_date
    ON index_readings(field_id, reading_date);
CREATE INDEX IF NOT EXISTS idx_readings_field_index
    ON index_readings(field_id, index_name, reading_date);
CREATE INDEX IF NOT EXISTS idx_readings_season
    ON index_readings(field_id, season_tag, index_name, reading_date);
CREATE INDEX IF NOT EXISTS idx_alerts_field_date
    ON alerts(field_id, alert_date);
CREATE INDEX IF NOT EXISTS idx_imagery_field_date
    ON imagery(field_id, image_date);
CREATE INDEX IF NOT EXISTS idx_imagery_season
    ON imagery(field_id, season_tag, image_date);
CREATE INDEX IF NOT EXISTS idx_risk_field_date
    ON risk_assessments(field_id, assessment_date);
CREATE INDEX IF NOT EXISTS idx_paddy_events_field
    ON paddy_events(field_id, season_tag, event_date);
"""

MIGRATION_SQL = """
-- Add crop columns to fields if not present (safe to run multiple times)
ALTER TABLE fields ADD COLUMN crop_type TEXT;
ALTER TABLE fields ADD COLUMN crop_confidence REAL;
-- Add season_tag columns (default 'generic' so existing rows stay in the generic scope)
ALTER TABLE index_readings ADD COLUMN season_tag TEXT NOT NULL DEFAULT 'generic';
ALTER TABLE imagery ADD COLUMN season_tag TEXT NOT NULL DEFAULT 'generic';
ALTER TABLE alerts ADD COLUMN season_tag TEXT NOT NULL DEFAULT 'generic';
ALTER TABLE fetch_log ADD COLUMN season_tag TEXT NOT NULL DEFAULT 'generic';
"""


def _table_unique_includes_season_tag(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,),
    ).fetchone()
    if row is None or row[0] is None:
        return True  # table does not exist; nothing to migrate
    return "season_tag" in row[0] and "UNIQUE" in row[0].upper() and "season_tag)" in row[0]


def _rebuild_index_readings_unique(conn: sqlite3.Connection) -> None:
    """Rewrite UNIQUE(field_id, index_name, reading_date) ->
    UNIQUE(field_id, index_name, reading_date, season_tag)."""
    if _table_unique_includes_season_tag(conn, "index_readings"):
        return
    conn.executescript(
        """
        PRAGMA foreign_keys = OFF;
        BEGIN;
        CREATE TABLE index_readings_new (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            field_id        TEXT NOT NULL REFERENCES fields(field_id),
            index_name      TEXT NOT NULL,
            reading_date    TEXT NOT NULL,
            mean_value      REAL,
            min_value       REAL,
            max_value       REAL,
            stdev_value     REAL,
            sample_count    INTEGER,
            cloud_cover_pct REAL,
            season_tag      TEXT NOT NULL DEFAULT 'generic',
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(field_id, index_name, reading_date, season_tag)
        );
        INSERT INTO index_readings_new
            (id, field_id, index_name, reading_date, mean_value, min_value,
             max_value, stdev_value, sample_count, cloud_cover_pct,
             season_tag, created_at)
        SELECT id, field_id, index_name, reading_date, mean_value, min_value,
               max_value, stdev_value, sample_count, cloud_cover_pct,
               COALESCE(season_tag, 'generic'), created_at
        FROM index_readings;
        DROP TABLE index_readings;
        ALTER TABLE index_readings_new RENAME TO index_readings;
        COMMIT;
        PRAGMA foreign_keys = ON;
        """
    )


def _rebuild_imagery_unique(conn: sqlite3.Connection) -> None:
    """Rewrite UNIQUE(field_id, image_date, image_type) ->
    UNIQUE(field_id, image_date, image_type, season_tag)."""
    if _table_unique_includes_season_tag(conn, "imagery"):
        return
    conn.executescript(
        """
        PRAGMA foreign_keys = OFF;
        BEGIN;
        CREATE TABLE imagery_new (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            field_id        TEXT NOT NULL REFERENCES fields(field_id),
            image_date      TEXT NOT NULL,
            image_type      TEXT NOT NULL,
            file_path       TEXT NOT NULL,
            width_px        INTEGER,
            height_px       INTEGER,
            season_tag      TEXT NOT NULL DEFAULT 'generic',
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(field_id, image_date, image_type, season_tag)
        );
        INSERT INTO imagery_new
            (id, field_id, image_date, image_type, file_path,
             width_px, height_px, season_tag, created_at)
        SELECT id, field_id, image_date, image_type, file_path,
               width_px, height_px, COALESCE(season_tag, 'generic'), created_at
        FROM imagery;
        DROP TABLE imagery;
        ALTER TABLE imagery_new RENAME TO imagery;
        COMMIT;
        PRAGMA foreign_keys = ON;
        """
    )


def create_tables(conn: sqlite3.Connection) -> None:
    """Create all tables and indexes if they do not exist."""
    conn.executescript(SCHEMA_SQL)
    # Run ALTER-based migrations for existing databases (column adds)
    for stmt in MIGRATION_SQL.strip().split(";"):
        stmt = stmt.strip()
        if not stmt or stmt.startswith("--"):
            continue
        try:
            conn.execute(stmt)
        except Exception:
            pass  # Column already exists or other idempotent no-op
    # Rebuild tables whose UNIQUE constraint must now include season_tag.
    # These helpers are idempotent: they inspect sqlite_master and skip if
    # the constraint already includes season_tag.
    _rebuild_index_readings_unique(conn)
    _rebuild_imagery_unique(conn)
    # Re-run SCHEMA_SQL to re-create indexes that may have been dropped with
    # the old tables.
    conn.executescript(SCHEMA_SQL)
    conn.commit()
