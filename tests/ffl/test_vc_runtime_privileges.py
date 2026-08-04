from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "db" / "postgres" / "0013_agro_vc_runtime_operating_reads.sql"


def test_vc_runtime_migration_repairs_only_the_existing_server_operating_lane():
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "GRANT SELECT, INSERT, UPDATE ON TABLE" in sql
    assert "agro_field_information_requests" in sql
    assert "agro_trackwick_parties" in sql
    assert "TO agro_vc_runtime" in sql
    assert "DELETE" in sql  # documented as intentionally absent authority
    assert "GRANT DELETE" not in sql
    assert "GRANT ALL" not in sql
