"""Database target selection for the FFL operating kernel.

SQLite is deliberately the only runnable adapter today.  Postgres/Supabase is
configured as a separate target so a production URL can never silently open a
local SQLite file (or leave the application running on an ephemeral database).
The checked-in bootstrap migration is the contract for the eventual Postgres
adapter; it is not applied by application startup.
"""

from dataclasses import dataclass
import os
from pathlib import Path
import re
import sqlite3
from typing import Optional, Union
from urllib.parse import urlparse


POSTGRES_BOOTSTRAP_PATH = (
    Path(__file__).resolve().parents[2] / "db" / "postgres" / "0001_agro_private_schema.sql"
)
_SCHEMA_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,62}")


class DatabaseConfigurationError(RuntimeError):
    """A configured database target is unsafe or not implemented yet."""


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

    ``FFL_DATABASE_URL`` wins over the legacy ``FFL_DATABASE_PATH``.  A
    Postgres target is intentionally recognised but cannot be opened until the
    query/repository adapter is implemented and reviewed.
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


def open_connection(
    target: Union[str, DatabaseTarget], *, check_same_thread: bool = True
) -> sqlite3.Connection:
    """Open SQLite, or fail closed for a configured Postgres destination.

    The string form remains for the existing pilot/test callers.  Passing a
    Postgres target produces an actionable error before any state can be
    written to the wrong database and without echoing a credential-bearing DSN.
    """
    resolved = DatabaseTarget(dialect="sqlite", sqlite_path=target) if isinstance(target, str) else target
    if resolved.dialect == "sqlite":
        if not resolved.sqlite_path:
            raise DatabaseConfigurationError("SQLite target is missing a database path")
        return _open_sqlite_connection(resolved.sqlite_path, check_same_thread=check_same_thread)
    if resolved.dialect == "postgres":
        raise DatabaseConfigurationError(
            "PostgreSQL is configured but the FFL Postgres repository adapter is not enabled. "
            "Apply db/postgres/0001_agro_private_schema.sql only with a reviewed private role, "
            "then enable the adapter in a dedicated migration."
        )
    raise DatabaseConfigurationError("Unsupported FFL database dialect")
