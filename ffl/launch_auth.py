"""Small, fail-closed shared launch gate for the Fortune pilot.

This is intentionally a temporary access layer for a named internal pilot. It
is not a substitute for per-person identity, role management, or audit-grade
authorization; those remain the next access-control milestone.
"""

import hashlib
import hmac
import os
from typing import Optional


SESSION_FLAG = "ffl_launch_authenticated"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 12


def configured_launch_password() -> Optional[str]:
    value = os.environ.get("FFL_LAUNCH_PASSWORD")
    return value if value else None


def session_secret(
    password: str, manager_session_secret: Optional[str] = None, portal_session_secret: Optional[str] = None,
) -> str:
    """Derive the browser-cookie signing key from configured server secrets.

    A configured manager unlock secret participates in the cookie key so its
    rotation invalidates browser manager sessions.  The launch password still
    participates separately; it is never itself manager authority.
    """

    material = "\x00".join((
        "ffl-browser-session-v3", password, manager_session_secret or "", portal_session_secret or "",
    ))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def password_matches(expected: Optional[str], presented: str) -> bool:
    return bool(expected) and hmac.compare_digest(expected, presented)


def safe_next_path(value: Optional[str]) -> str:
    """Avoid turning the login form into an open redirect."""
    # These are fixed first-party Next.js command-centre routes. Keeping the
    # allow-list here preserves the original open-redirect protection while
    # letting the web shell complete the same signed launch flow as the legacy
    # FastAPI manager surface.
    return value if value in {
        "/manager", "/field", "/home", "/fields", "/farmers", "/actions", "/settings",
    } else "/home"
