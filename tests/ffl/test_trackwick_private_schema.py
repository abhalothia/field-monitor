from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "db" / "postgres" / "0009_agro_trackwick_private_spatial_evidence.sql"
CLASSIFICATION_MIGRATION = ROOT / "db" / "postgres" / "0023_agro_operating_classification_spine.sql"
PLACE_SUMMARIES_MIGRATION = ROOT / "db" / "postgres" / "0024_agro_place_operating_summaries.sql"


def test_private_spatial_migration_defines_the_typed_trackwick_graph():
    sql = MIGRATION.read_text(encoding="utf-8")

    for relation in (
        "agro_trackwick_parties",
        "agro_trackwick_contact_points",
        "agro_trackwick_tasks",
        "agro_trackwick_visits",
        "agro_trackwick_visit_findings",
        "agro_trackwick_crop_inputs",
        "agro_trackwick_registrations",
        "agro_trackwick_registration_plots",
        "agro_trackwick_location_observations",
        "agro_trackwick_media_references",
        "agro_trackwick_worker_days",
    ):
        assert "CREATE TABLE IF NOT EXISTS " + relation in sql

    assert "extensions.geography(POINT, 4326)" in sql
    assert "USING GIST (geog)" in sql
    assert "Aadhar" not in sql
    assert "Aadhaar" not in sql
    assert "REVOKE ALL ON TABLE agro_trackwick_parties" in sql


def test_sqlite_schema_has_private_trackwick_tables(ffl_db):
    relations = {
        row[0]
        for row in ffl_db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'trackwick_%'"
        ).fetchall()
    }

    assert {
        "trackwick_parties",
        "trackwick_contact_points",
        "trackwick_tasks",
        "trackwick_visits",
        "trackwick_location_observations",
        "trackwick_media_references",
    } <= relations


def test_operating_classification_migration_stays_private_and_additive(ffl_db):
    sql = CLASSIFICATION_MIGRATION.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS agro_place_catalog" in sql
    assert "CREATE TABLE IF NOT EXISTS agro_task_type_taxonomy" in sql
    assert "ADD COLUMN IF NOT EXISTS place_key" in sql
    assert "REVOKE ALL ON TABLE agro_place_catalog, agro_task_type_taxonomy" in sql
    assert "GRANT SELECT, INSERT, UPDATE ON TABLE agro_place_catalog, agro_task_type_taxonomy" in sql
    assert "anon" in sql and "authenticated" in sql
    assert "provider_address" not in sql
    assert "remote_url" not in sql

    relations = {
        row[0] for row in ffl_db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    assert {"place_catalog", "task_type_taxonomy"} <= relations


def test_place_summary_migration_stays_private_and_reported_only(ffl_db):
    sql = PLACE_SUMMARIES_MIGRATION.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS agro_place_operating_summaries" in sql
    assert "REFERENCES agro_place_catalog" in sql
    assert "REVOKE ALL ON TABLE agro_place_operating_summaries" in sql
    assert "GRANT SELECT, INSERT, UPDATE ON TABLE agro_place_operating_summaries" in sql
    assert "boundary" in sql.lower()
    assert "provider_address" not in sql
    assert "remote_url" not in sql

    relation = ffl_db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'place_operating_summaries'"
    ).fetchone()
    assert relation is not None
