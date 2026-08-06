"""Fail-closed named ID/password access for the private AGRO CEO pilot.

This intentionally does *not* make a source contact, an imported CRM person,
or an operational job title into a login.  A manager creates an account for a
real person; every use rechecks the live private identity row before granting
any authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import base64
import hashlib
import hmac
import re
import secrets
import sqlite3
import time
import uuid
from typing import Any, Optional

from ffl.launch_auth import SESSION_FLAG


PASSWORD_IDENTITY_SESSION_FLAG = "ffl_password_identity"
PASSWORD_IDENTITY_SESSION_SCOPE = "password-identity-v1"
PASSWORD_IDENTITY_ROLES = frozenset({"owner", "admin", "field_worker", "farmer"})
MANAGER_PASSWORD_ROLES = frozenset({"owner", "admin"})
DEFAULT_PASSWORD_SESSION_MAX_AGE_SECONDS = 8 * 60 * 60
_LOGIN_ID = re.compile(r"[a-z][a-z0-9._-]{2,63}")
_PBKDF2_ITERATIONS = 600_000
_PASSWORD_MIN_LENGTH = 12


class PasswordIdentityError(ValueError):
    """A safe identity/provisioning validation error."""


class PasswordIdentityUnavailable(RuntimeError):
    """The reviewed private migration has not been applied yet."""


@dataclass(frozen=True)
class PasswordPrincipal:
    identity_id: str
    person_id: str
    person_name: str
    access_role: str
    expires_at: int

    @property
    def is_manager(self) -> bool:
        return self.access_role in MANAGER_PASSWORD_ROLES


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connection(request):
    return getattr(request.state, "conn", request.app.state.conn)


def normalise_login_id(value: str) -> str:
    login_id = (value or "").strip().lower()
    if _LOGIN_ID.fullmatch(login_id) is None:
        raise PasswordIdentityError(
            "ID must be 3–64 lower-case letters, numbers, dots, underscores, or hyphens"
        )
    return login_id


def _validate_password(password: str) -> None:
    if not isinstance(password, str) or not _PASSWORD_MIN_LENGTH <= len(password) <= 256:
        raise PasswordIdentityError("password must be between 12 and 256 characters")


def password_hash(password: str) -> str:
    """Derive a non-reversible, salted password representation."""

    _validate_password(password)
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        _PBKDF2_ITERATIONS,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def password_matches(stored_hash: str, presented: str) -> bool:
    """Verify exactly the reviewed PBKDF2 format with a constant-time check."""

    try:
        algorithm, raw_iterations, raw_salt, raw_digest = stored_hash.split("$", 3)
        iterations = int(raw_iterations)
        salt = base64.urlsafe_b64decode(raw_salt.encode("ascii"))
        expected = base64.urlsafe_b64decode(raw_digest.encode("ascii"))
    except (AttributeError, TypeError, ValueError):
        return False
    if algorithm != "pbkdf2_sha256" or iterations < _PBKDF2_ITERATIONS or not salt or not expected:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", presented.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def password_identity_session_now(app: Any) -> int:
    return int(getattr(app.state, "password_identity_session_clock", time.time)())


def password_identity_session_max_age_seconds(app: Any) -> int:
    value = getattr(app.state, "password_identity_session_max_age_seconds", DEFAULT_PASSWORD_SESSION_MAX_AGE_SECONDS)
    return value if isinstance(value, int) and 300 <= value <= 12 * 60 * 60 else DEFAULT_PASSWORD_SESSION_MAX_AGE_SECONDS


def _session_key(app: Any) -> bytes:
    key = getattr(app.state, "password_identity_session_key", None)
    if not isinstance(key, str) or not key:
        raise PasswordIdentityUnavailable("password identity session configuration is unavailable")
    return key.encode("utf-8")


def _session_binding(app: Any, identity_id: str, password_version: int, expires_at: int) -> str:
    material = "\x1f".join((PASSWORD_IDENTITY_SESSION_SCOPE, identity_id, str(password_version), str(expires_at)))
    return hmac.new(_session_key(app), material.encode("utf-8"), hashlib.sha256).hexdigest()


def _schema_unavailable(error: Exception) -> bool:
    message = str(error).lower()
    return "password_identities" in message and (
        "no such table" in message or "does not exist" in message or "undefined table" in message
    )


def _identity_row(conn, identity_id: str):
    try:
        return conn.execute(
            """SELECT identity.id, identity.person_id, identity.login_id, identity.password_hash,
                      identity.access_role, identity.identity_status, identity.password_version,
                      person.name AS person_name
               FROM password_identities identity
               JOIN people person ON person.id = identity.person_id
               WHERE identity.id = ?""",
            (identity_id,),
        ).fetchone()
    except Exception as error:
        if _schema_unavailable(error):
            raise PasswordIdentityUnavailable("named ID sign-in is being enabled") from error
        raise


def begin_password_identity_session(app: Any, session: dict[str, Any], *, identity_id: str, password_version: int) -> int:
    expires_at = password_identity_session_now(app) + password_identity_session_max_age_seconds(app)
    session[PASSWORD_IDENTITY_SESSION_FLAG] = {
        "scope": PASSWORD_IDENTITY_SESSION_SCOPE,
        "identity_id": identity_id,
        "password_version": password_version,
        "expires_at": expires_at,
        "binding": _session_binding(app, identity_id, password_version, expires_at),
    }
    return expires_at


def active_password_principal(request) -> Optional[PasswordPrincipal]:
    """Resolve the signed identity session and recheck role/status in storage."""

    value = request.session.get(PASSWORD_IDENTITY_SESSION_FLAG)
    if not isinstance(value, dict):
        return None
    identity_id = value.get("identity_id")
    version = value.get("password_version")
    expires_at = value.get("expires_at")
    binding = value.get("binding")
    if (
        value.get("scope") != PASSWORD_IDENTITY_SESSION_SCOPE
        or not isinstance(identity_id, str)
        or isinstance(version, bool) or not isinstance(version, int) or version <= 0
        or isinstance(expires_at, bool) or not isinstance(expires_at, int)
        or not isinstance(binding, str)
        or expires_at <= password_identity_session_now(request.app)
    ):
        request.session.pop(PASSWORD_IDENTITY_SESSION_FLAG, None)
        request.session.pop(SESSION_FLAG, None)
        return None
    try:
        expected_binding = _session_binding(request.app, identity_id, version, expires_at)
        row = _identity_row(_connection(request), identity_id)
    except PasswordIdentityUnavailable:
        request.session.pop(PASSWORD_IDENTITY_SESSION_FLAG, None)
        request.session.pop(SESSION_FLAG, None)
        return None
    if (
        not hmac.compare_digest(binding, expected_binding)
        or row is None
        or row["identity_status"] != "active"
        or row["access_role"] not in PASSWORD_IDENTITY_ROLES
        or row["password_version"] != version
    ):
        request.session.pop(PASSWORD_IDENTITY_SESSION_FLAG, None)
        request.session.pop(SESSION_FLAG, None)
        return None
    return PasswordPrincipal(
        identity_id=row["id"], person_id=row["person_id"], person_name=row["person_name"],
        access_role=row["access_role"], expires_at=expires_at,
    )


def authenticate_password_identity(conn, *, login_id: str, password: str):
    """Return one active principal row or a generic failure without enumeration."""

    normalised = normalise_login_id(login_id)
    try:
        row = conn.execute(
            """SELECT identity.id, identity.person_id, identity.password_hash,
                      identity.access_role, identity.identity_status, identity.password_version,
                      person.name AS person_name
               FROM password_identities identity
               JOIN people person ON person.id = identity.person_id
               WHERE identity.login_id = ?""",
            (normalised,),
        ).fetchone()
    except Exception as error:
        if _schema_unavailable(error):
            raise PasswordIdentityUnavailable("named ID sign-in is being enabled") from error
        raise
    if (
        row is None
        or row["identity_status"] != "active"
        or row["access_role"] not in PASSWORD_IDENTITY_ROLES
        or not password_matches(row["password_hash"], password)
    ):
        return None
    now = _now_iso()
    conn.execute("UPDATE password_identities SET last_authenticated_at = ? WHERE id = ?", (now, row["id"]))
    conn.commit()
    return row


def change_password_identity(
    conn, *, identity_id: str, current_password: str, new_password: str,
) -> int:
    """Rotate one signed-in person's password and invalidate old sessions."""

    row = _identity_row(conn, identity_id)
    if (
        row is None
        or row["identity_status"] != "active"
        or not password_matches(row["password_hash"], current_password)
    ):
        raise PasswordIdentityError("current password was not accepted")
    replacement_hash = password_hash(new_password)
    next_version = row["password_version"] + 1
    conn.execute(
        """UPDATE password_identities
           SET password_hash = ?, password_version = ?, password_changed_at = ?
           WHERE id = ? AND password_version = ?""",
        (replacement_hash, next_version, _now_iso(), identity_id, row["password_version"]),
    )
    conn.commit()
    return next_version


def provision_password_identity(
    conn, *, actor_person_id: str, access_role: str, login_id: str, temporary_password: str,
    person_id: Optional[str] = None, person_name: Optional[str] = None, operational_role: Optional[str] = None,
) -> PasswordPrincipal:
    """Create one explicit account for a real person, never from an import.

    An existing person may be selected by its opaque internal id.  Otherwise a
    manager creates the person and account together.  This is intentionally a
    narrow admin action; it does not assert a farm relationship or assign work.
    """

    if access_role not in PASSWORD_IDENTITY_ROLES:
        raise PasswordIdentityError("access role is not supported")
    normalised_login = normalise_login_id(login_id)
    derived_hash = password_hash(temporary_password)
    now = _now_iso()
    if bool(person_id) == bool(person_name):
        raise PasswordIdentityError("provide either an existing person or a name for a new account")
    if person_id:
        person = conn.execute("SELECT id, name FROM people WHERE id = ?", (person_id,)).fetchone()
        if person is None:
            raise PasswordIdentityError("person was not found")
    else:
        clean_name = (person_name or "").strip()
        if not 2 <= len(clean_name) <= 160:
            raise PasswordIdentityError("name must be between 2 and 160 characters")
        role = (operational_role or "").strip().lower()
        allowed_roles = {"operations_lead", "farm_manager", "field_operator", "grower", "agronomist"}
        if role not in allowed_roles:
            raise PasswordIdentityError("select a supported operating role")
        person_id = "agro:person:" + uuid.uuid4().hex
        conn.execute(
            "INSERT INTO people (id, name, role, created_at) VALUES (?, ?, ?, ?)",
            (person_id, clean_name, role, now),
        )
        person = {"id": person_id, "name": clean_name}
    identity_id = "agro:password-identity:" + uuid.uuid4().hex
    try:
        conn.execute(
            """INSERT INTO password_identities
               (id, person_id, login_id, password_hash, access_role, identity_status,
                password_version, password_changed_at, last_authenticated_at, created_by_person_id, created_at)
               VALUES (?, ?, ?, ?, ?, 'active', 1, ?, NULL, ?, ?)""",
            (identity_id, person["id"], normalised_login, derived_hash, access_role, now, actor_person_id, now),
        )
        conn.commit()
    except sqlite3.IntegrityError as error:
        conn.rollback()
        raise PasswordIdentityError("that person or ID already has an account") from error
    return PasswordPrincipal(
        identity_id=identity_id, person_id=person["id"], person_name=person["name"],
        access_role=access_role, expires_at=0,
    )


def list_password_identities(conn) -> list[dict[str, str]]:
    """Admin-only safe account inventory: no hash or session identifiers."""

    try:
        rows = conn.execute(
            """SELECT identity.id, identity.person_id, identity.login_id, identity.access_role,
                      identity.identity_status, person.name AS person_name
               FROM password_identities identity
               JOIN people person ON person.id = identity.person_id
               ORDER BY person.name, identity.login_id"""
        ).fetchall()
    except Exception as error:
        if _schema_unavailable(error):
            raise PasswordIdentityUnavailable("named ID sign-in is being enabled") from error
        raise
    return [
        {
            "id": row["id"], "person_id": row["person_id"], "person_name": row["person_name"],
            "login_id": row["login_id"], "access_role": row["access_role"],
            "identity_status": row["identity_status"],
        }
        for row in rows
    ]
