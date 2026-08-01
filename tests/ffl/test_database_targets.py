from pathlib import Path
import re

import pytest

from ffl.persistence.database import (
    POSTGRES_BOOTSTRAP_PATH,
    DatabaseConfigurationError,
    database_target,
    open_connection,
    translate_sqlite_sql,
)


class _FakeCursor:
    rowcount = 1

    def fetchone(self):
        return {"payload": {"stable": True}, "created_at": __import__("datetime").date(2026, 8, 1)}

    def fetchall(self):
        return [self.fetchone()]


class _FakeRawConnection:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params):
        self.calls.append((sql, params))
        return _FakeCursor()

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


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


def test_postgres_target_is_explicit_without_echoing_dsn():
    dsn = "postgresql://ffl_runtime:secret-never-logged@db.example.test:5432/ffl"
    target = database_target(database_url=dsn, postgres_schema="agro")

    assert target.dialect == "postgres"
    assert target.schema == "agro"
    assert target.dsn == dsn


def test_sqlite_sql_translation_keeps_values_safe_and_uses_private_relation_names():
    translated = translate_sqlite_sql(
        "INSERT OR IGNORE INTO evidence_artifacts VALUES (?, 'work_items ?')"
    )

    assert translated == "INSERT INTO agro_evidence_artifacts VALUES (%s, 'work_items ?') ON CONFLICT DO NOTHING"
    assert translate_sqlite_sql("SELECT * FROM work_items ORDER BY rowid") == (
        "SELECT * FROM agro_work_items ORDER BY created_at, id"
    )
    assert translate_sqlite_sql("BEGIN IMMEDIATE") == "SELECT 1"


def test_postgres_connection_preserves_repository_row_contract_without_a_network_call():
    from ffl.persistence.database import PostgresConnection

    raw = _FakeRawConnection()
    row = PostgresConnection(raw).execute("SELECT * FROM source_registry WHERE id = ?", ("source-1",)).fetchone()

    assert raw.calls == [("SELECT * FROM agro_source_registry WHERE id = %s", ("source-1",))]
    assert row["payload"] == '{"stable":true}'
    assert row[1] == "2026-08-01"


def test_postgres_private_table_probe_uses_to_regclass_without_public_catalog_access():
    from ffl.persistence.database import PostgresConnection
    from ffl.services.portfolio import _table_exists

    class _ProbeCursor:
        def fetchone(self):
            return {"relation_name": "agro_work_items"}

    class _ProbeRaw(_FakeRawConnection):
        def execute(self, sql, params):
            self.calls.append((sql, params))
            return _ProbeCursor()

    raw = _ProbeRaw()
    assert _table_exists(PostgresConnection(raw), "work_items") is True
    assert raw.calls == [("SELECT to_regclass(%s) AS relation_name", ("agro_work_items",))]


def test_api_startup_never_falls_back_to_sqlite_when_postgres_opening_fails(monkeypatch, tmp_path):
    # Import here so module-level ``app`` was created before this test-specific
    # setting.  This only exercises target selection; it makes no network call.
    from ffl.app import create_app

    monkeypatch.setenv(
        "FFL_DATABASE_URL", "postgresql://ffl_runtime:secret-never-logged@db.example.test/ffl"
    )

    def refusing_connect(_target):
        raise DatabaseConfigurationError("FFL could not open the configured private PostgreSQL target")

    monkeypatch.setattr("ffl.persistence.database._open_postgres_connection", refusing_connect)
    with pytest.raises(DatabaseConfigurationError) as exc_info:
        create_app(str(tmp_path / "must-not-be-created.db"))

    assert "could not open" in str(exc_info.value)
    assert "secret-never-logged" not in str(exc_info.value)
    assert not (tmp_path / "must-not-be-created.db").exists()


def test_postgres_requests_open_a_distinct_connection_without_changing_sqlite_preview(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from ffl.app import create_app

    opened = []

    class _Connection:
        def close(self):
            pass

        def rollback(self):
            pass

    def fake_open(target, **_kwargs):
        opened.append(target)
        return _Connection()

    monkeypatch.setenv("FFL_DATABASE_URL", "postgresql://runtime@example.test/ffl")
    monkeypatch.setattr("ffl.app.open_connection", fake_open)
    with TestClient(create_app(str(tmp_path / "must-not-be-created.db"))) as client:
        assert client.get("/health").status_code == 200

    # Bootstrap compatibility connection + a distinct request connection.
    assert len(opened) == 2
    assert all(target.dialect == "postgres" for target in opened)


def test_communications_worker_skips_sqlite_ddl_for_a_private_postgres_target(monkeypatch):
    from ffl.communications import worker

    class _Connection:
        def close(self):
            pass

    target = database_target(database_url="postgresql://runtime@example.test/ffl")
    monkeypatch.setattr(worker, "database_target", lambda **_kwargs: target)
    monkeypatch.setattr(worker, "open_connection", lambda _target: _Connection())
    monkeypatch.setattr(worker, "run_once", lambda *_args, **_kwargs: {"receipts_processed": 0})
    monkeypatch.setattr(worker, "create_schema", lambda _conn: (_ for _ in ()).throw(AssertionError("SQLite DDL")))
    monkeypatch.setattr(worker.persistence, "create_communications_schema", lambda _conn: (_ for _ in ()).throw(AssertionError("SQLite DDL")))

    assert worker.main(["--once"]) == 0


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
