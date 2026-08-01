from pathlib import Path
import re

import pytest

from ffl.persistence.database import (
    POSTGRES_BOOTSTRAP_PATH,
    DatabaseConfigurationError,
    database_target,
    open_connection,
)


def test_legacy_sqlite_paths_remain_the_default_target(monkeypatch):
    monkeypatch.delenv("FFL_DATABASE_URL", raising=False)

    target = database_target(sqlite_path=":memory:")

    assert target.dialect == "sqlite"
    assert target.sqlite_path == ":memory:"
    connection = open_connection(target)
    try:
        assert connection.execute("SELECT 1").fetchone()[0] == 1
    finally:
        connection.close()


def test_postgres_target_is_explicit_and_fails_closed_without_echoing_dsn():
    dsn = "postgresql://ffl_runtime:secret-never-logged@db.example.test:5432/ffl"
    target = database_target(database_url=dsn, postgres_schema="agro")

    assert target.dialect == "postgres"
    assert target.schema == "agro"
    with pytest.raises(DatabaseConfigurationError) as exc_info:
        open_connection(target)

    assert "PostgreSQL is configured" in str(exc_info.value)
    assert "secret-never-logged" not in str(exc_info.value)


def test_api_startup_never_falls_back_to_sqlite_when_a_postgres_url_is_set(monkeypatch, tmp_path):
    # Import here so module-level ``app`` was created before this test-specific
    # setting.  This only exercises target selection; it makes no network call.
    from ffl.app import create_app

    monkeypatch.setenv(
        "FFL_DATABASE_URL", "postgresql://ffl_runtime:secret-never-logged@db.example.test/ffl"
    )

    with pytest.raises(DatabaseConfigurationError) as exc_info:
        create_app(str(tmp_path / "must-not-be-created.db"))

    assert "PostgreSQL is configured" in str(exc_info.value)
    assert "secret-never-logged" not in str(exc_info.value)
    assert not (tmp_path / "must-not-be-created.db").exists()


@pytest.mark.parametrize("schema", ["AGRO", "agro-app", "agro schema", "1agro"])
def test_private_schema_name_must_be_a_safe_identifier(schema):
    with pytest.raises(DatabaseConfigurationError, match="FFL_POSTGRES_SCHEMA"):
        database_target(database_url="postgresql://runtime@db.example.test/ffl", postgres_schema=schema)


def test_postgres_bootstrap_is_checked_in_private_schema_contract():
    assert POSTGRES_BOOTSTRAP_PATH == Path(__file__).resolve().parents[2] / "db/postgres/0001_agro_private_schema.sql"
    sql = POSTGRES_BOOTSTRAP_PATH.read_text()

    assert "CREATE SCHEMA IF NOT EXISTS agro" in sql
    assert "REVOKE ALL ON SCHEMA agro FROM PUBLIC" in sql
    assert "CREATE TABLE IF NOT EXISTS agro_communication_events" in sql
    assert "CREATE TABLE IF NOT EXISTS agro_regional_signals" in sql
    assert "CREATE TABLE IF NOT EXISTS agro_trial_conclusions" in sql
    assert "JSONB" in sql
    assert "SET LOCAL search_path = agro, pg_catalog" in sql

    relation_names = re.findall(
        r"CREATE (?:TABLE|(?:UNIQUE )?INDEX) IF NOT EXISTS ([a-z0-9_]+)", sql
    )
    reference_targets = re.findall(r"REFERENCES ([a-z0-9_]+)\\(id\\)", sql)
    assert relation_names
    assert all(name.startswith("agro_") for name in relation_names)
    assert all(name.startswith("agro_") for name in reference_targets)


def test_postgres_bootstrap_indexes_every_foreign_key_reference():
    sql = POSTGRES_BOOTSTRAP_PATH.read_text()

    # The referencing side of a PostgreSQL FK is not indexed automatically.
    # These are deliberately the only exceptions: each is already the leading
    # column of a primary/unique key, which supplies the required B-tree index.
    composite_key_coverage = {
        ("agro_block_parcels", "operational_block_id"),
        ("agro_trial_allocations", "trial_id"),
        ("agro_communication_evidence_links", "attachment_id"),
        ("agro_communication_candidates", "event_id"),
        ("agro_communication_receipts", "event_id"),
    }
    # Index names can contain underscores, so infer coverage from the indexed
    # relation/first column, not from an index-name split.
    explicit_index_coverage = {
        (relation, first_column.strip())
        for relation, first_column in re.findall(
            r"CREATE (?:UNIQUE )?INDEX IF NOT EXISTS agro_[a-z0-9_]+ ON "
            r"(agro_[a-z0-9_]+) \(([^,)]+)",
            sql,
        )
    }

    table_definitions = re.findall(
        r"CREATE TABLE IF NOT EXISTS (agro_[a-z0-9_]+) \((.*?)(?=\n\);)", sql, re.DOTALL
    )
    foreign_keys = {
        (table, column)
        for table, definition in table_definitions
        for column in re.findall(
            r"(?:^|,)\s*([a-z_][a-z0-9_]*)\s+[^,\n]*?\s+REFERENCES\s+agro_[a-z0-9_]+\(id\)",
            definition,
        )
    }

    assert foreign_keys
    assert len(foreign_keys) == len(re.findall(r"REFERENCES\s+agro_[a-z0-9_]+\(id\)", sql))
    assert foreign_keys <= explicit_index_coverage | composite_key_coverage


def test_postgres_defaults_to_the_private_agro_schema():
    target = database_target(database_url="postgresql://runtime@db.example.test/ffl")

    assert target.schema == "agro"
