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
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(field_id, index_name, reading_date)
);

CREATE TABLE IF NOT EXISTS imagery (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    field_id        TEXT NOT NULL REFERENCES fields(field_id),
    image_date      TEXT NOT NULL,
    image_type      TEXT NOT NULL,
    file_path       TEXT NOT NULL,
    width_px        INTEGER,
    height_px       INTEGER,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(field_id, image_date, image_type)
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
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
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
CREATE INDEX IF NOT EXISTS idx_alerts_field_date
    ON alerts(field_id, alert_date);
CREATE INDEX IF NOT EXISTS idx_imagery_field_date
    ON imagery(field_id, image_date);
CREATE INDEX IF NOT EXISTS idx_risk_field_date
    ON risk_assessments(field_id, assessment_date);
"""

MIGRATION_SQL = """
-- Add crop columns to fields if not present (safe to run multiple times)
ALTER TABLE fields ADD COLUMN crop_type TEXT;
ALTER TABLE fields ADD COLUMN crop_confidence REAL;
"""


def create_tables(conn: sqlite3.Connection) -> None:
    """Create all tables and indexes if they do not exist."""
    conn.executescript(SCHEMA_SQL)
    # Run migrations for existing databases
    for stmt in MIGRATION_SQL.strip().split(";"):
        stmt = stmt.strip()
        if not stmt or stmt.startswith("--"):
            continue
        try:
            conn.execute(stmt)
        except Exception:
            pass  # Column already exists
    conn.commit()
