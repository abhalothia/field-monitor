"""Named AGRO CEO staff access, separate from field-operating roles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from typing import Optional


@dataclass(frozen=True)
class AccessMembership:
    person_id: str
    name: str
    operational_role: str
    access_role: str
    identity_status: str


_INITIAL_FORTUNE_TEAM = (
    ("Daksh Bhatia", "admin"),
    ("Aakash Bhalothia", "owner"),
    ("Ajay Bhalothia", "owner"),
)


def provision_initial_fortune_team(
    conn, *, observed_at: Optional[str] = None, commit: bool = True,
) -> tuple[AccessMembership, ...]:
    """Create the three explicitly approved staff records exactly once.

    These are durable people and app-access records, not fabricated Auth users:
    an email and verified Supabase subject are required later to activate a
    browser login. ``operations_lead`` is the narrow existing system role that
    permits accountable source operations; owner/admin remains in the separate
    membership table.
    """
    now = observed_at or datetime.now(timezone.utc).isoformat()
    memberships: list[AccessMembership] = []
    for name, access_role in _INITIAL_FORTUNE_TEAM:
        person_id = _stable_id("person", name)
        membership_id = _stable_id("membership", name)
        conn.execute(
            "INSERT OR IGNORE INTO people (id, name, role, created_at) VALUES (?, ?, ?, ?)",
            (person_id, name, "operations_lead", now),
        )
        conn.execute(
            """INSERT OR IGNORE INTO access_memberships
               (id, person_id, auth_subject, identity_email, access_role, identity_status,
                invited_at, activated_at, last_authenticated_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (membership_id, person_id, None, None, access_role, "identity_pending", None, None, None, now),
        )
        memberships.append(AccessMembership(
            person_id=person_id,
            name=name,
            operational_role="operations_lead",
            access_role=access_role,
            identity_status="identity_pending",
        ))
    if commit:
        conn.commit()
    return tuple(memberships)


def list_access_memberships(conn) -> list[AccessMembership]:
    rows = conn.execute(
        """SELECT p.id, p.name, p.role, m.access_role, m.identity_status
           FROM access_memberships m JOIN people p ON p.id = m.person_id
           ORDER BY CASE m.access_role WHEN 'owner' THEN 0 ELSE 1 END, p.name"""
    ).fetchall()
    return [
        AccessMembership(
            person_id=row["id"],
            name=row["name"],
            operational_role=row["role"],
            access_role=row["access_role"],
            identity_status=row["identity_status"],
        )
        for row in rows
    ]


def _stable_id(kind: str, value: str) -> str:
    digest = hashlib.sha256((kind + "\x1f" + value).encode("utf-8")).hexdigest()[:32]
    return "agro:" + kind + ":" + digest
