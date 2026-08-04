"""Private customer-portal identity and membership primitives.

This module deliberately keeps three facts separate:

* a customer portal (for example ``fortune.agroceo.com``),
* a verified phone identity, and
* a person's role in that portal.

TrackWick source contacts are never consulted here.  Possessing an imported
mobile number must not make someone able to receive an authentication code.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import re
from typing import Optional


PORTAL_ROLES = frozenset({"owner", "admin", "field_worker", "farmer"})
MANAGER_PORTAL_ROLES = frozenset({"owner", "admin"})
_HOSTNAME = re.compile(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?")
_SLUG = re.compile(r"[a-z][a-z0-9-]{1,62}")
_PHONE_E164 = re.compile(r"\+[1-9][0-9]{7,14}")


@dataclass(frozen=True)
class CustomerPortal:
    id: str
    slug: str
    display_name: str
    hostname: str
    status: str


@dataclass(frozen=True)
class PortalPrincipal:
    portal_id: str
    portal_slug: str
    portal_name: str
    membership_id: str
    person_id: str
    person_name: str
    portal_role: str
    auth_subject: str

    @property
    def is_manager(self) -> bool:
        return self.portal_role in MANAGER_PORTAL_ROLES


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalise_hostname(value: str) -> str:
    """Accept one canonical DNS hostname, never a URL or arbitrary Host value."""

    candidate = (value or "").strip().lower().rstrip(".")
    if not candidate or len(candidate) > 253 or _HOSTNAME.fullmatch(candidate) is None:
        raise ValueError("portal hostname must be a lower-case hostname")
    if ".." in candidate or candidate.startswith(".") or candidate.endswith("."):
        raise ValueError("portal hostname must be a lower-case hostname")
    return candidate


def hostname_from_host_header(value: Optional[str]) -> Optional[str]:
    """Parse just a DNS Host header, rejecting paths, userinfo, and IPv6."""

    raw = (value or "").strip()
    if not raw or "/" in raw or "@" in raw or raw.startswith("["):
        return None
    host = raw.rsplit(":", 1)[0] if raw.count(":") == 1 else raw
    try:
        return normalise_hostname(host)
    except ValueError:
        return None


def normalise_phone_e164(value: str) -> str:
    """Keep phone identity input strict; formatting is a UI responsibility."""

    candidate = (value or "").strip().replace(" ", "")
    if _PHONE_E164.fullmatch(candidate) is None:
        raise ValueError("phone must be in E.164 format, for example +919876543210")
    return candidate


def portal_host_is_under_base(hostname: Optional[str], base_domain: str) -> bool:
    """Return true for exactly one customer label beneath the configured base."""

    if hostname is None:
        return False
    try:
        base = normalise_hostname(base_domain)
    except ValueError:
        return False
    suffix = "." + base
    if not hostname.endswith(suffix):
        return False
    customer_label = hostname[: -len(suffix)]
    return bool(_SLUG.fullmatch(customer_label))


def customer_portal_for_hostname(conn, hostname: Optional[str]) -> Optional[CustomerPortal]:
    if hostname is None:
        return None
    row = conn.execute(
        """SELECT id, slug, display_name, hostname, status
           FROM customer_portals WHERE hostname = ?""",
        (hostname,),
    ).fetchone()
    if row is None:
        return None
    return CustomerPortal(
        id=row["id"], slug=row["slug"], display_name=row["display_name"],
        hostname=row["hostname"], status=row["status"],
    )


def provision_fortune_portal(conn, *, observed_at: Optional[str] = None, commit: bool = True) -> CustomerPortal:
    """Provision Fortune's hostname and approved staff roles, never identities.

    The three named staff already exist as explicitly authorised access
    memberships.  They receive a customer membership in ``identity_pending``
    state; neither their name nor any TrackWick contact creates a login.
    """

    created_at = observed_at or now_iso()
    portal = CustomerPortal(
        id=_stable_id("portal", "fortune"), slug="fortune", display_name="Fortune Rice",
        hostname="fortune.agroceo.com", status="active",
    )
    conn.execute(
        """INSERT OR IGNORE INTO customer_portals
           (id, slug, display_name, hostname, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (portal.id, portal.slug, portal.display_name, portal.hostname, portal.status, created_at),
    )
    for name, role in (
        ("Aakash Bhalothia", "owner"),
        ("Ajay Bhalothia", "owner"),
        ("Daksh Bhatia", "admin"),
    ):
        person = conn.execute("SELECT id FROM people WHERE name = ?", (name,)).fetchone()
        if person is None:
            raise ValueError("initial Fortune access person is missing: " + name)
        conn.execute(
            """INSERT OR IGNORE INTO portal_memberships
               (id, portal_id, person_id, identity_id, portal_role, membership_status,
                invited_at, activated_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (_stable_id("portal-membership", portal.slug + "\x1f" + name), portal.id, person["id"],
             None, role, "identity_pending", None, None, created_at),
        )
    if commit:
        conn.commit()
    return portal


def invite_phone_identity(
    conn, *, portal_id: str, person_id: str, phone_e164: str, observed_at: Optional[str] = None,
    commit: bool = True,
) -> str:
    """Attach one explicitly collected phone to one existing portal member.

    This is an accountable provisioning primitive for a future admin surface.
    It must only be called after the person has supplied/confirmed their phone
    and agreed to receive an OTP.  It does not read or copy a TrackWick contact.
    """

    phone = normalise_phone_e164(phone_e164)
    created_at = observed_at or now_iso()
    membership = conn.execute(
        """SELECT id, membership_status FROM portal_memberships
           WHERE portal_id = ? AND person_id = ?""",
        (portal_id, person_id),
    ).fetchone()
    if membership is None or membership["membership_status"] == "suspended":
        raise ValueError("person is not an eligible member of this customer portal")
    existing = conn.execute(
        "SELECT id, person_id, identity_status FROM portal_identities WHERE person_id = ?",
        (person_id,),
    ).fetchone()
    identity_id = _stable_id("portal-identity", person_id)
    if existing is not None:
        if existing["identity_status"] == "active":
            raise ValueError("active identity phone cannot be replaced here")
        identity_id = existing["id"]
        conn.execute(
            """UPDATE portal_identities SET phone_e164 = ?, identity_status = 'invited',
               invited_at = ?, verified_at = NULL WHERE id = ?""",
            (phone, created_at, identity_id),
        )
    else:
        conn.execute(
            """INSERT INTO portal_identities
               (id, person_id, phone_e164, auth_subject, identity_status, invited_at,
                verified_at, last_authenticated_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (identity_id, person_id, phone, None, "invited", created_at, None, None, created_at),
        )
    conn.execute(
        """UPDATE portal_memberships
           SET identity_id = ?, membership_status = 'invited', invited_at = ?, activated_at = NULL
           WHERE id = ?""",
        (identity_id, created_at, membership["id"]),
    )
    access = conn.execute(
        "SELECT id, identity_status FROM access_memberships WHERE person_id = ?", (person_id,)
    ).fetchone()
    if access is not None and access["identity_status"] != "active":
        conn.execute(
            """UPDATE access_memberships
               SET identity_phone = ?, identity_email = NULL, identity_status = 'invited',
                   invited_at = ?, activated_at = NULL
               WHERE id = ?""",
            (phone, created_at, access["id"]),
        )
    if commit:
        conn.commit()
    return identity_id


def eligible_phone_identity(conn, *, portal_id: str, phone_e164: str):
    """Find a pre-provisioned login candidate without returning it to callers."""

    return conn.execute(
        """SELECT identity.id, identity.person_id, identity.phone_e164, identity.auth_subject,
                  identity.identity_status, membership.id AS membership_id, membership.portal_role,
                  membership.membership_status
           FROM portal_identities identity
           JOIN portal_memberships membership ON membership.identity_id = identity.id
           JOIN customer_portals portal ON portal.id = membership.portal_id
           WHERE membership.portal_id = ? AND identity.phone_e164 = ?
             AND portal.status = 'active'
             AND identity.identity_status IN ('invited', 'active')
             AND membership.membership_status IN ('invited', 'active')""",
        (portal_id, phone_e164),
    ).fetchone()


def activate_phone_identity(
    conn, *, portal_id: str, phone_e164: str, auth_subject: str, observed_at: Optional[str] = None,
    commit: bool = True,
) -> PortalPrincipal:
    """Bind a provider-verified phone to its pre-provisioned portal member."""

    if not auth_subject or len(auth_subject) > 200:
        raise ValueError("verified Auth subject is required")
    verified_at = observed_at or now_iso()
    candidate = eligible_phone_identity(conn, portal_id=portal_id, phone_e164=phone_e164)
    if candidate is None:
        raise ValueError("phone is not eligible for this customer portal")
    previous_subject = candidate["auth_subject"]
    if previous_subject is not None and previous_subject != auth_subject:
        raise ValueError("phone identity is already bound to another Auth subject")
    existing_subject = conn.execute(
        "SELECT id FROM portal_identities WHERE auth_subject = ? AND id <> ?",
        (auth_subject, candidate["id"]),
    ).fetchone()
    if existing_subject is not None:
        raise ValueError("Auth subject is already bound to another person")

    conn.execute(
        """UPDATE portal_identities
           SET auth_subject = ?, identity_status = 'active', verified_at = ?,
               last_authenticated_at = ? WHERE id = ?""",
        (auth_subject, verified_at, verified_at, candidate["id"]),
    )
    conn.execute(
        """UPDATE portal_memberships
           SET membership_status = 'active', activated_at = ? WHERE id = ?""",
        (verified_at, candidate["membership_id"]),
    )
    if candidate["portal_role"] in MANAGER_PORTAL_ROLES:
        conn.execute(
            """UPDATE access_memberships
               SET auth_subject = ?, identity_phone = ?, identity_email = NULL,
                   identity_status = 'active', activated_at = ?, last_authenticated_at = ?
               WHERE person_id = ?""",
            (auth_subject, phone_e164, verified_at, verified_at, candidate["person_id"]),
        )
    if commit:
        conn.commit()
    principal = portal_principal_for_membership(conn, portal_id=portal_id, membership_id=candidate["membership_id"])
    if principal is None:
        raise RuntimeError("activated portal identity could not be resolved")
    return principal


def portal_principal_for_membership(conn, *, portal_id: str, membership_id: str) -> Optional[PortalPrincipal]:
    """Revalidate every session against present membership and identity state."""

    row = conn.execute(
        """SELECT portal.id AS portal_id, portal.slug AS portal_slug, portal.display_name AS portal_name,
                  membership.id AS membership_id, person.id AS person_id, person.name AS person_name,
                  membership.portal_role, identity.auth_subject
           FROM portal_memberships membership
           JOIN customer_portals portal ON portal.id = membership.portal_id
           JOIN people person ON person.id = membership.person_id
           JOIN portal_identities identity ON identity.id = membership.identity_id
           WHERE membership.id = ? AND membership.portal_id = ?
             AND portal.status = 'active' AND membership.membership_status = 'active'
             AND identity.identity_status = 'active' AND identity.auth_subject IS NOT NULL""",
        (membership_id, portal_id),
    ).fetchone()
    if row is None:
        return None
    return PortalPrincipal(
        portal_id=row["portal_id"], portal_slug=row["portal_slug"], portal_name=row["portal_name"],
        membership_id=row["membership_id"], person_id=row["person_id"], person_name=row["person_name"],
        portal_role=row["portal_role"], auth_subject=row["auth_subject"],
    )


def _stable_id(kind: str, value: str) -> str:
    digest = hashlib.sha256((kind + "\x1f" + value).encode("utf-8")).hexdigest()[:32]
    return "agro:" + kind + ":" + digest
