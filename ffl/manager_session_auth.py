"""Short-lived, server-signed browser sessions for one configured manager.

The Fortune launch password only gates access to the pilot shell.  It must
never grant manager authority.  This module keeps that authority narrow: a
server-configured secret unlocks a signed browser session for the one
server-configured manager person for a short period.  No browser-provided
person, role, or bearer token participates in the decision.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Any, Optional


MANAGER_SESSION_FLAG = "ffl_manager_session"
MANAGER_SESSION_SCOPE = "manager-browser-v1"
DEFAULT_MANAGER_SESSION_MAX_AGE_SECONDS = 15 * 60
MIN_MANAGER_SESSION_MAX_AGE_SECONDS = 60
MAX_MANAGER_SESSION_MAX_AGE_SECONDS = 60 * 60


def configured_manager_session_secret() -> Optional[str]:
    """Read the manager unlock secret without ever returning it in an API."""

    value = os.environ.get("FFL_MANAGER_SESSION_SECRET")
    return value if value else None


def configured_manager_session_max_age_seconds() -> Optional[int]:
    """Return a bounded session duration, or ``None`` for an invalid config.

    Browser manager authority is deliberately short-lived.  An invalid value
    is a deployment error, not an opportunity to fall back to an unbounded
    session.
    """

    raw = os.environ.get("FFL_MANAGER_SESSION_MAX_AGE_SECONDS")
    if raw is None or raw == "":
        return DEFAULT_MANAGER_SESSION_MAX_AGE_SECONDS
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    if not MIN_MANAGER_SESSION_MAX_AGE_SECONDS <= value <= MAX_MANAGER_SESSION_MAX_AGE_SECONDS:
        return None
    return value


def manager_session_configuration_is_present(app: Any) -> bool:
    """Check only trusted deployment configuration, never a request payload."""

    return bool(
        getattr(app.state, "manager_session_secret", None)
        and getattr(app.state, "manager_person_id", None)
        and isinstance(getattr(app.state, "manager_session_max_age_seconds", None), int)
        and getattr(app.state, "manager_session_max_age_seconds") > 0
    )


def manager_session_matches_secret(expected: Optional[str], presented: str) -> bool:
    return bool(expected) and hmac.compare_digest(expected, presented)


def manager_session_now(app: Any) -> int:
    """Use a server-owned clock seam; tests can advance it without sleeps."""

    clock = getattr(app.state, "manager_session_clock", time.time)
    return int(clock())


def _configured_manager_subject(app: Any) -> str:
    """Bind the cookie to the configured person without exposing their id."""

    return hmac.new(
        app.state.manager_session_secret.encode("utf-8"),
        app.state.manager_person_id.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def begin_manager_session(app: Any, session: dict[str, Any]) -> int:
    """Replace only manager authority and return its expiry epoch.

    Starlette's SessionMiddleware signs the complete session cookie.  The
    purpose/version, opaque configured-person binding, and expiry below make a valid
    launch session insufficient to become a manager session.
    """

    if not manager_session_configuration_is_present(app):
        raise ValueError("manager browser access is not configured")
    issued_at = manager_session_now(app)
    expires_at = issued_at + app.state.manager_session_max_age_seconds
    session[MANAGER_SESSION_FLAG] = {
        "scope": MANAGER_SESSION_SCOPE,
        "subject": _configured_manager_subject(app),
        "issued_at": issued_at,
        "expires_at": expires_at,
    }
    return expires_at


def active_manager_session(app: Any, session: dict[str, Any]) -> Optional[dict[str, int | str]]:
    """Return a valid configured-manager session, clearing stale data.

    The caller never controls the manager id: it must be the configured value
    and the cookie itself must have been signed by SessionMiddleware.
    """

    value = session.get(MANAGER_SESSION_FLAG)
    if not isinstance(value, dict) or not manager_session_configuration_is_present(app):
        if value is not None:
            session.pop(MANAGER_SESSION_FLAG, None)
        return None

    subject = value.get("subject")
    scope = value.get("scope")
    issued_at = value.get("issued_at")
    expires_at = value.get("expires_at")
    if (
        not isinstance(subject, str)
        or not hmac.compare_digest(subject, _configured_manager_subject(app))
        or scope != MANAGER_SESSION_SCOPE
        or isinstance(issued_at, bool)
        or isinstance(expires_at, bool)
        or not isinstance(issued_at, int)
        or not isinstance(expires_at, int)
        or issued_at > expires_at
        or expires_at - issued_at > app.state.manager_session_max_age_seconds
        or expires_at <= manager_session_now(app)
    ):
        session.pop(MANAGER_SESSION_FLAG, None)
        return None
    return {
        "issued_at": issued_at,
        "expires_at": expires_at,
    }
