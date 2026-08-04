from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "db" / "postgres" / "0011_agro_trackwick_media_origin_check.sql"


def test_media_origin_repair_uses_one_exact_s3_prefix_after_dropping_the_bad_regex():
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "DROP CONSTRAINT IF EXISTS agro_trackwick_media_references_remote_url_check" in sql
    assert "remote_url LIKE 'https://trackolap-images-prod.s3.amazonaws.com/%'" in sql
    assert "REVOKE" not in sql
