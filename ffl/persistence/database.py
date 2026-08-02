"""Database targets and the narrow FFL PostgreSQL compatibility boundary.

The operating services deliberately speak a small SQLite-shaped connection
protocol.  ``PostgresConnection`` translates that protocol to the reviewed,
private ``agro`` schema.  It is a transition boundary, not a public SQL API:
browser clients never receive this DSN and application startup never applies a
migration.
"""

from dataclasses import dataclass
import os
from pathlib import Path
import re
import sqlite3
from datetime import date, datetime
from typing import Any, Optional, Sequence, Union
from urllib.parse import parse_qsl, urlencode, urlparse, urlsplit, urlunsplit


POSTGRES_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "db" / "postgres"
POSTGRES_BOOTSTRAP_PATH = POSTGRES_MIGRATIONS_DIR / "0001_agro_private_schema.sql"
_SCHEMA_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,62}")


class DatabaseConfigurationError(RuntimeError):
    """A configured database target is unsafe or not implemented yet."""


def _postgres_relation_names() -> tuple[str, ...]:
    """Read every reviewed private migration, not just the bootstrap file.

    The compatibility facade must know tables added after the first live
    bootstrap.  Application startup still never applies a migration; this only
    keeps repository SQL in the private ``agro`` namespace once an operator has
    applied the reviewed migration separately.
    """
    names = set()
    for migration in sorted(POSTGRES_MIGRATIONS_DIR.glob("*.sql")):
        names.update(re.findall(
            r"CREATE TABLE IF NOT EXISTS (agro_[a-z0-9_]+)",
            migration.read_text(encoding="utf-8"),
        ))
    return tuple(sorted(names, key=len, reverse=True))


_CORE_RELATIONS = _postgres_relation_names()


def _outside_literals(sql: str, transform) -> str:
    """Apply a SQL-token transform without ever changing quoted data values."""
    result = []
    segment = []
    quote: Optional[str] = None
    index = 0
    while index < len(sql):
        character = sql[index]
        if quote is None and character in ("'", '"'):
            result.append(transform("".join(segment)))
            segment = []
            quote = character
            result.append(character)
        elif quote is not None:
            result.append(character)
            if character == quote:
                if index + 1 < len(sql) and sql[index + 1] == quote:
                    result.append(sql[index + 1])
                    index += 1
                else:
                    quote = None
        else:
            segment.append(character)
        index += 1
    if quote is not None:
        # Let PostgreSQL return the syntax error; a compatibility layer must
        # not attempt to repair malformed SQL.
        return sql
    result.append(transform("".join(segment)))
    return "".join(result)


def translate_sqlite_sql(sql: str) -> str:
    """Translate only the known FFL repository SQL dialect differences.

    The relation map is derived from the checked-in production migration.  It
    keeps every FFL table in the private schema while letting existing services
    retain their stable, unprefixed repository vocabulary.
    """
    stripped = sql.strip()
    if stripped.upper() == "BEGIN IMMEDIATE":
        # Psycopg starts a transaction on the first statement.  Starting a
        # second transaction here would fail; uniqueness constraints remain
        # the cross-process idempotency guard.
        return "SELECT 1"

    def replace_tokens(segment: str) -> str:
        translated = segment.replace("?", "%s")
        for relation in _CORE_RELATIONS:
            bare_name = relation[len("agro_"):]
            translated = re.sub(
                r"(?<![A-Za-z0-9_])" + re.escape(bare_name) + r"(?![A-Za-z0-9_])",
                relation,
                translated,
            )
        return re.sub(r"\browid\b", "created_at, id", translated, flags=re.IGNORECASE)

    translated = _outside_literals(sql, replace_tokens)
    if re.match(r"^\s*INSERT\s+OR\s+IGNORE\s+INTO\b", translated, flags=re.IGNORECASE):
        translated = re.sub(
            r"^\s*INSERT\s+OR\s+IGNORE\s+INTO\b", "INSERT INTO", translated,
            flags=re.IGNORECASE,
        )
        suffix = ";" if translated.rstrip().endswith(";") else ""
        translated = translated.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING" + suffix
    return translated


def _normalise_postgres_value(value: Any) -> Any:
    """Preserve the SQLite repository's stable primitive row contract."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (dict, list)):
        import json

        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return value


class PostgresCursor:
    """Cursor facade returning mapping rows compatible with ``sqlite3.Row``."""

    def __init__(self, cursor) -> None:
        self._cursor = cursor

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    def fetchone(self):
        row = self._cursor.fetchone()
        return self._row(row)

    def fetchall(self):
        return [self._row(row) for row in self._cursor.fetchall()]

    @staticmethod
    def _row(row):
        if row is None:
            return None
        if isinstance(row, dict):
            return PostgresRow({key: _normalise_postgres_value(value) for key, value in row.items()})
        return row


class PostgresRow(dict):
    """Mapping row with SQLite's small positional-access compatibility."""

    def __getitem__(self, key):
        if isinstance(key, int):
            return tuple(self.values())[key]
        return super().__getitem__(key)


class PostgresConnection:
    """Private, server-only connection for the checked-in ``agro_*`` tables."""

    dialect = "postgres"

    def __init__(self, raw_connection) -> None:
        self._connection = raw_connection

    def execute(self, sql: str, params: Sequence[Any] = ()) -> PostgresCursor:
        try:
            cursor = self._connection.execute(translate_sqlite_sql(sql), params)
        except Exception as error:
            # Existing domain services intentionally handle uniqueness races as
            # sqlite integrity errors.  Preserve that narrow public contract
            # while keeping the original PostgreSQL exception as the cause.
            try:
                from psycopg import IntegrityError as PostgresIntegrityError
            except ImportError:  # pragma: no cover - guarded at connect time
                PostgresIntegrityError = ()  # type: ignore[assignment]
            if isinstance(error, PostgresIntegrityError):
                raise sqlite3.IntegrityError(str(error)) from error
            raise
        return PostgresCursor(cursor)

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        return False


@dataclass(frozen=True)
class DatabaseTarget:
    """A validated database destination, without logging credentials."""

    dialect: str
    sqlite_path: Optional[str] = None
    dsn: Optional[str] = None
    schema: str = "agro"


def _private_schema(value: Optional[str]) -> str:
    schema = value or "agro"
    if _SCHEMA_PATTERN.fullmatch(schema) is None:
        raise DatabaseConfigurationError("FFL_POSTGRES_SCHEMA must be a lowercase SQL identifier")
    return schema


def _psycopg_compatible_dsn(dsn: str) -> str:
    """Drop client-library flags that libpq/psycopg deliberately reject.

    Supabase's serverless pooler connection string can include
    ``pgbouncer=true`` for Node clients.  psycopg passes URI query arguments to
    libpq, which does not recognise that flag.  FFL already disables prepared
    statements for the transaction pooler via ``prepare_threshold=None`` below,
    so removing only this client-specific flag preserves the connection's host,
    credentials, SSL options, and all supported query parameters.
    """

    parsed = urlsplit(dsn)
    filtered = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() != "pgbouncer"
    ]
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(filtered), parsed.fragment))


def _sqlite_path_from_url(url: str) -> str:
    if url == "sqlite:///:memory:":
        return ":memory:"
    if not url.startswith("sqlite:////"):
        raise DatabaseConfigurationError(
            "SQLite URLs must be sqlite:///:memory: or an absolute sqlite:////path URL"
        )
    path = url[len("sqlite:///") :]
    if not path.startswith("/"):
        raise DatabaseConfigurationError("SQLite database path must be absolute")
    return path


def database_target(
    *, database_url: Optional[str] = None, sqlite_path: Optional[str] = None,
    postgres_schema: Optional[str] = None,
) -> DatabaseTarget:
    """Resolve the explicit target without opening a network connection.

    ``FFL_DATABASE_URL`` wins over the legacy ``FFL_DATABASE_PATH``. A
    PostgreSQL target is always explicit and is opened only through the
    private-relation adapter below; it is never a browser-facing data API.
    """
    url = database_url if database_url is not None else os.environ.get("FFL_DATABASE_URL")
    schema = _private_schema(
        postgres_schema if postgres_schema is not None else os.environ.get("FFL_POSTGRES_SCHEMA")
    )
    if not url:
        return DatabaseTarget(dialect="sqlite", sqlite_path=sqlite_path or os.environ.get("FFL_DATABASE_PATH", "data/ffl.db"), schema=schema)
    parsed = urlparse(url)
    if parsed.scheme == "sqlite":
        return DatabaseTarget(dialect="sqlite", sqlite_path=_sqlite_path_from_url(url), schema=schema)
    if parsed.scheme in {"postgres", "postgresql"}:
        if not parsed.hostname or not parsed.path or parsed.path == "/":
            raise DatabaseConfigurationError("FFL_DATABASE_URL must include a PostgreSQL host and database")
        return DatabaseTarget(dialect="postgres", dsn=url, schema=schema)
    raise DatabaseConfigurationError("FFL_DATABASE_URL must use sqlite, postgres, or postgresql")


def _open_sqlite_connection(path: str, *, check_same_thread: bool = True) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=check_same_thread)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _open_postgres_connection(target: DatabaseTarget) -> PostgresConnection:
    if not target.dsn:
        raise DatabaseConfigurationError("PostgreSQL target is missing a DSN")
    try:
        from psycopg import connect
        from psycopg.rows import dict_row
    except ImportError as error:
        raise DatabaseConfigurationError(
            "PostgreSQL is configured but psycopg is not installed; install the reviewed server dependency"
        ) from error
    try:
        raw = connect(
            _psycopg_compatible_dsn(target.dsn),
            row_factory=dict_row,
            prepare_threshold=None,
            options="-c search_path={0},pg_catalog".format(target.schema),
        )
    except Exception as error:
        raise DatabaseConfigurationError(
            "FFL could not open the configured private PostgreSQL target"
        ) from error
    return PostgresConnection(raw)


def open_connection(
    target: Union[str, DatabaseTarget], *, check_same_thread: bool = True
) -> Union[sqlite3.Connection, PostgresConnection]:
    """Open the explicit SQLite or private PostgreSQL operating-record target."""
    resolved = DatabaseTarget(dialect="sqlite", sqlite_path=target) if isinstance(target, str) else target
    if resolved.dialect == "sqlite":
        if not resolved.sqlite_path:
            raise DatabaseConfigurationError("SQLite target is missing a database path")
        return _open_sqlite_connection(resolved.sqlite_path, check_same_thread=check_same_thread)
    if resolved.dialect == "postgres":
        return _open_postgres_connection(resolved)
    raise DatabaseConfigurationError("Unsupported FFL database dialect")
