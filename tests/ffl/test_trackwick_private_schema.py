from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "db" / "postgres" / "0009_agro_trackwick_private_spatial_evidence.sql"


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
