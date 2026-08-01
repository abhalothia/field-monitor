from pathlib import Path

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
    target = database_target(database_url=dsn, postgres_schema="ffl")

    assert target.dialect == "postgres"
    assert target.schema == "ffl"
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


@pytest.mark.parametrize("schema", ["FFL", "ffl-app", "ffl schema", "1ffl"])
def test_private_schema_name_must_be_a_safe_identifier(schema):
    with pytest.raises(DatabaseConfigurationError, match="FFL_POSTGRES_SCHEMA"):
        database_target(database_url="postgresql://runtime@db.example.test/ffl", postgres_schema=schema)


def test_postgres_bootstrap_is_checked_in_private_schema_contract():
    assert POSTGRES_BOOTSTRAP_PATH == Path(__file__).resolve().parents[2] / "db/postgres/0001_ffl_private_schema.sql"
    sql = POSTGRES_BOOTSTRAP_PATH.read_text()

    assert "CREATE SCHEMA IF NOT EXISTS ffl" in sql
    assert "REVOKE ALL ON SCHEMA ffl FROM PUBLIC" in sql
    assert "CREATE TABLE IF NOT EXISTS communication_events" in sql
    assert "CREATE TABLE IF NOT EXISTS regional_signals" in sql
    assert "CREATE TABLE IF NOT EXISTS trial_conclusions" in sql
    assert "JSONB" in sql
    assert "SET LOCAL search_path = ffl, pg_catalog" in sql
