from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "db" / "postgres" / "0009_agro_trackwick_private_spatial_evidence.sql"
CLASSIFICATION_MIGRATION = ROOT / "db" / "postgres" / "0023_agro_operating_classification_spine.sql"
PLACE_SUMMARIES_MIGRATION = ROOT / "db" / "postgres" / "0024_agro_place_operating_summaries.sql"
VOCABULARY_MIGRATION = ROOT / "db" / "postgres" / "0025_agro_operating_vocabulary_registry.sql"
LANGUAGE_MIGRATION = ROOT / "db" / "postgres" / "0029_agro_operating_language_packs.sql"
FIELD_CONTEXT_MIGRATION = ROOT / "db" / "postgres" / "0030_agro_field_context_enrichment.sql"


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


def test_vocabulary_migration_stays_private_and_reviewable(ffl_db):
    sql = VOCABULARY_MIGRATION.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS agro_operating_vocabulary_terms" in sql
    assert "'task_type', 'reported_issue', 'crop_product'" in sql
    assert "'pending', 'suggested', 'reviewed', 'rejected', 'unmapped', 'automatic'" in sql
    assert "REVOKE ALL ON TABLE agro_operating_vocabulary_terms" in sql
    assert "GRANT SELECT, INSERT, UPDATE ON TABLE agro_operating_vocabulary_terms" in sql
    assert "provider_identifier" not in sql
    assert "remote_url" not in sql

    relation = ffl_db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'operating_vocabulary_terms'"
    ).fetchone()
    assert relation is not None


def test_operating_language_packs_are_private_and_review_first(ffl_db):
    sql = LANGUAGE_MIGRATION.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS agro_operating_vocabulary_localizations" in sql
    assert "CREATE TABLE IF NOT EXISTS agro_operating_issue_group_proposals" in sql
    assert "CREATE TABLE IF NOT EXISTS agro_place_localizations" in sql
    assert "REFERENCES agro_operating_vocabulary_terms" in sql
    assert "REFERENCES agro_place_catalog" in sql
    assert "REVOKE ALL ON TABLE agro_operating_vocabulary_localizations FROM PUBLIC, anon, authenticated" in sql
    assert "REVOKE ALL ON TABLE agro_operating_issue_group_proposals FROM PUBLIC, anon, authenticated" in sql
    assert "REVOKE ALL ON TABLE agro_place_localizations FROM PUBLIC, anon, authenticated" in sql

    relations = {
        row[0] for row in ffl_db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    assert {
        "operating_vocabulary_localizations", "operating_issue_group_proposals", "place_localizations",
    } <= relations


def test_field_context_migration_is_private_and_never_claims_a_boundary(ffl_db):
    sql = FIELD_CONTEXT_MIGRATION.read_text(encoding="utf-8")

    for column in (
        "reported_plot_count", "latest_crop_stage", "latest_water_condition",
        "latest_kit_status", "latest_field_observed_at",
    ):
        assert "ADD COLUMN IF NOT EXISTS " + column in sql
    assert "REVOKE ALL ON TABLE agro_entity_operating_snapshots" in sql
    assert "GRANT SELECT, INSERT, UPDATE ON TABLE agro_entity_operating_snapshots" in sql
    assert "predicted" in sql.lower()
    assert "boundary" in sql.lower()
    assert "provider_identifier" not in sql
    assert "remote_url" not in sql

    columns = {
        row["name"] for row in ffl_db.execute(
            "PRAGMA table_info(entity_operating_snapshots)"
        ).fetchall()
    }
    assert {
        "reported_plot_count", "latest_crop_stage", "latest_water_condition",
        "latest_kit_status", "latest_field_observed_at",
    } <= columns
