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


def session_secret(password: str) -> str:
    """Derive a cookie-signing secret without adding a second shared secret."""
    return hashlib.sha256(("ffl-launch-session-v1:" + password).encode("utf-8")).hexdigest()


def password_matches(expected: Optional[str], presented: str) -> bool:
    return bool(expected) and hmac.compare_digest(expected, presented)


def safe_next_path(value: Optional[str]) -> str:
    """Avoid turning the login form into an open redirect."""
    return value if value in {"/manager", "/field"} else "/manager"
