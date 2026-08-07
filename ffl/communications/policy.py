"""Current-state policy gate for communications dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from typing import Optional, Tuple, Union
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ffl.communications.identity import CommunicationResolution
from ffl.communications.persistence import has_scoped_consent
from ffl.services.allocation_relationship_coverage import active_person_allocation_coverage


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    code: str


_ALLOWED = PolicyDecision(True, "allowed")


def may_dispatch(
    conn,
    resolution: CommunicationResolution,
    purpose: str,
    scope_type: str,
    scope_id: str,
    *,
    allocation_id: Optional[str] = None,
    channel: str = "whatsapp",
    dispatch_at: Optional[Union[datetime, str]] = None,
    quiet_hours: Optional[Tuple[str, str]] = None,
    messages_sent: int = 0,
    frequency_cap: Optional[int] = None,
) -> PolicyDecision:
    """Recheck the exact recipient and scope immediately before dispatch.

    ``resolution`` identifies the already resolved tenant/person/endpoint. The
    database remains authoritative: every mutable status and the exact scoped
    consent are read again here, so a stale audience or interaction snapshot
    cannot authorize a send.
    """
    if not isinstance(resolution, CommunicationResolution):
        return _deny("endpoint_not_verified")
    if not resolution.endpoint_id or not resolution.person_id or not resolution.portal_id:
        return _deny("endpoint_not_verified")

    try:
        authority = conn.execute(
            """SELECT profile.id AS profile_id, profile.status AS profile_status,
                      profile.time_zone, portal.status AS portal_status,
                      membership.portal_role, membership.membership_status
               FROM communication_profiles profile
               JOIN customer_portals portal ON portal.id = profile.portal_id
               LEFT JOIN portal_memberships membership
                 ON membership.portal_id = profile.portal_id
                AND membership.person_id = profile.person_id
               JOIN communication_endpoint_verifications verification
                 ON verification.profile_id = profile.id
                AND verification.endpoint_id = ?
                AND verification.status = 'active'
               JOIN communication_endpoints endpoint
                 ON endpoint.id = verification.endpoint_id
                AND endpoint.person_id = profile.person_id
                AND endpoint.status = 'active'
               WHERE profile.portal_id = ? AND profile.person_id = ?
               LIMIT 2""",
            (resolution.endpoint_id, resolution.portal_id, resolution.person_id),
        ).fetchall()
    except Exception:
        return _deny("endpoint_not_verified")
    if len(authority) != 1:
        return _deny("endpoint_not_verified")

    current = authority[0]
    if current["portal_status"] != "active" or current["membership_status"] != "active":
        return _deny("membership_inactive")
    if current["profile_status"] != "active":
        return _deny("profile_inactive")
    if resolution.state != "eligible_" + current["portal_role"]:
        if resolution.state == "ambiguous_scope":
            return _deny("scope_not_covered")
        return _deny("membership_inactive")

    effective_allocation_id = allocation_id
    if effective_allocation_id is None and scope_type == "crop_allocation":
        effective_allocation_id = scope_id
    if resolution.state in {"eligible_farmer", "eligible_field_worker"} and effective_allocation_id is None:
        return _deny("scope_not_covered")
    if (
        resolution.state in {"eligible_farmer", "eligible_field_worker"}
        and effective_allocation_id not in resolution.allocation_ids
    ):
        return _deny("scope_not_covered")
    if effective_allocation_id is not None:
        dispatch_date = _dispatch_time(dispatch_at)
        if dispatch_date is None:
            return _deny("scope_not_covered")
        coverage = active_person_allocation_coverage(
            conn,
            resolution.person_id,
            effective_allocation_id,
            on_date=dispatch_date.date().isoformat(),
        )
        if not coverage.eligible:
            return _deny("scope_not_covered")

    try:
        consent_active = has_scoped_consent(
            conn,
            current["profile_id"],
            resolution.endpoint_id,
            purpose,
            scope_type,
            scope_id,
            channel,
        )
    except Exception:
        consent_active = False
    if not consent_active:
        return _deny("consent_not_active")

    if quiet_hours is not None:
        at = _dispatch_time(dispatch_at)
        quiet = _quiet_window(quiet_hours)
        try:
            local_time = at.astimezone(ZoneInfo(current["time_zone"])).time() if at is not None else None
        except (ZoneInfoNotFoundError, ValueError, TypeError):
            local_time = None
        if local_time is None or quiet is None or _inside_quiet_hours(local_time, quiet):
            return _deny("quiet_hours")

    if (
        frequency_cap is not None
        and (not isinstance(frequency_cap, int) or isinstance(frequency_cap, bool) or frequency_cap < 1)
    ):
        return _deny("frequency_cap")
    if not isinstance(messages_sent, int) or isinstance(messages_sent, bool) or messages_sent < 0:
        return _deny("frequency_cap")
    if frequency_cap is not None and messages_sent >= frequency_cap:
        return _deny("frequency_cap")

    return _ALLOWED


def _deny(code: str) -> PolicyDecision:
    return PolicyDecision(False, code)


def _dispatch_time(value: Optional[Union[datetime, str]]) -> Optional[datetime]:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def _quiet_window(value: object) -> Optional[Tuple[time, time]]:
    if not isinstance(value, tuple) or len(value) != 2:
        return None
    try:
        return time.fromisoformat(value[0]), time.fromisoformat(value[1])
    except (TypeError, ValueError):
        return None


def _inside_quiet_hours(local_time: time, quiet_hours: Tuple[time, time]) -> bool:
    start, end = quiet_hours
    current = local_time.replace(tzinfo=None)
    if start == end:
        return True
    if start < end:
        return start <= current < end
    return current >= start or current < end
