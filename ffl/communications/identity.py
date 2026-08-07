"""Portal-scoped, non-inferential communications identity resolution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Optional, Tuple, Union

from ffl.services.allocation_relationship_coverage import (
    active_person_allocation_coverage,
    active_person_allocation_coverages,
)


ResolutionState = Literal[
    "unknown",
    "known_unverified",
    "known_ineligible",
    "ambiguous_scope",
    "eligible_owner",
    "eligible_admin",
    "eligible_farmer",
    "eligible_field_worker",
]


@dataclass(frozen=True)
class CommunicationResolution:
    state: ResolutionState
    person_id: Optional[str]
    portal_id: Optional[str]
    endpoint_id: Optional[str]
    allocation_ids: Tuple[str, ...]
    locale: Optional[str]


_FIELD_ROLES = frozenset({"farmer", "field_worker"})
_ELIGIBLE_STATES = {
    "owner": "eligible_owner",
    "admin": "eligible_admin",
    "farmer": "eligible_farmer",
    "field_worker": "eligible_field_worker",
}


def resolve_communication_endpoint(
    conn,
    provider: str,
    address: str,
    portal_id: str,
    allocation_id: Optional[str] = None,
    received_at: Optional[Union[datetime, str]] = None,
) -> CommunicationResolution:
    """Resolve one reviewed endpoint inside one explicitly supplied portal.

    Provider contact data is used only to locate the endpoint record.  Person,
    tenant, role, and operating scope all come from canonical profile,
    membership, and relationship records; no source-contact or name matching
    is performed.
    """
    normalized_provider = _identifier(provider)
    normalized_address = _address(address)
    normalized_portal_id = _identifier(portal_id)
    event_date = _event_date(received_at)
    if normalized_provider is None or normalized_address is None or normalized_portal_id is None:
        return _resolution("unknown")

    try:
        endpoint = conn.execute(
            """SELECT id, person_id, locale, status
               FROM communication_endpoints
               WHERE provider = ? AND address = ?""",
            (normalized_provider, normalized_address),
        ).fetchone()
    except Exception:
        return _resolution("unknown")
    if endpoint is None:
        return _resolution("unknown")

    base = {
        "person_id": endpoint["person_id"],
        "portal_id": normalized_portal_id,
        "endpoint_id": endpoint["id"],
        "locale": endpoint["locale"],
    }
    if received_at is not None and event_date is None:
        return _resolution("known_ineligible", **base)
    try:
        verified = conn.execute(
            """SELECT profile.id AS profile_id, profile.person_id, profile.status AS profile_status,
                      profile.locale, portal.status AS portal_status,
                      membership.portal_role, membership.membership_status
               FROM communication_endpoint_verifications verification
               JOIN communication_profiles profile ON profile.id = verification.profile_id
               JOIN customer_portals portal ON portal.id = profile.portal_id
               LEFT JOIN portal_memberships membership
                 ON membership.portal_id = profile.portal_id
                AND membership.person_id = profile.person_id
               WHERE verification.endpoint_id = ?
                 AND verification.status = 'active'
                 AND profile.portal_id = ?
                 AND profile.person_id = ?
               LIMIT 2""",
            (endpoint["id"], normalized_portal_id, endpoint["person_id"]),
        ).fetchall()
    except Exception:
        return _resolution("known_unverified", **base)
    if len(verified) != 1:
        return _resolution("known_unverified", **base)

    authority = verified[0]
    base["locale"] = authority["locale"]
    if (
        endpoint["status"] != "active"
        or authority["portal_status"] != "active"
        or authority["membership_status"] != "active"
        or authority["profile_status"] != "active"
        or authority["portal_role"] not in _ELIGIBLE_STATES
    ):
        return _resolution("known_ineligible", **base)

    role = authority["portal_role"]
    allocation_ids: Tuple[str, ...] = ()
    if allocation_id is not None:
        normalized_allocation_id = _identifier(allocation_id)
        if normalized_allocation_id is None:
            return _resolution("ambiguous_scope", **base)
        coverage = active_person_allocation_coverage(
            conn, authority["person_id"], normalized_allocation_id, on_date=event_date
        )
        if not coverage.eligible:
            return _resolution("ambiguous_scope", **base)
        allocation_ids = (normalized_allocation_id,)
    elif role in _FIELD_ROLES:
        coverages = active_person_allocation_coverages(
            conn, authority["person_id"], on_date=event_date
        )
        allocation_ids = tuple(coverage.allocation_id for coverage in coverages if coverage.allocation_id)
        if len(allocation_ids) != 1:
            return _resolution("ambiguous_scope", allocation_ids=allocation_ids, **base)

    return _resolution(
        _ELIGIBLE_STATES[role], allocation_ids=allocation_ids, **base
    )


def _resolution(
    state: ResolutionState,
    *,
    person_id: Optional[str] = None,
    portal_id: Optional[str] = None,
    endpoint_id: Optional[str] = None,
    allocation_ids: Tuple[str, ...] = (),
    locale: Optional[str] = None,
) -> CommunicationResolution:
    return CommunicationResolution(
        state=state,
        person_id=person_id,
        portal_id=portal_id,
        endpoint_id=endpoint_id,
        allocation_ids=allocation_ids,
        locale=locale,
    )


def _identifier(value: object) -> Optional[str]:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized if normalized and len(normalized) <= 128 else None


def _address(value: object) -> Optional[str]:
    if not isinstance(value, str):
        return None
    # Persistence owns E.164 validation. Resolution performs only the same
    # harmless formatting normalization and otherwise fails closed.
    normalized = "".join(character for character in value if character not in " -()")
    if not normalized.startswith("+") or not normalized[1:].isdigit():
        return None
    if not 8 <= len(normalized[1:]) <= 15 or normalized[1] == "0":
        return None
    return normalized


def _event_date(value: Optional[Union[datetime, str]]) -> Optional[str]:
    instant = _utc_instant(value)
    return instant.date().isoformat() if instant is not None else None


def _utc_instant(value: Optional[Union[datetime, str]]) -> Optional[datetime]:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)
