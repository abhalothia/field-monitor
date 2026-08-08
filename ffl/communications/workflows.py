"""Typed, versioned communications workflows.

This module deliberately supports one bounded automation: a weekly farmer
check-in for each currently eligible allocation.  It has no free-form audience
or query language.  Every target is re-resolved through the canonical portal,
profile, relationship, consent, locale, quiet-hours, and frequency gates just
before an immutable interaction capture is created.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import sqlite3
import uuid
from typing import Any, Mapping, Optional, Sequence, Tuple, Union

from ffl.communications.identity import resolve_communication_endpoint
from ffl.communications.interactions import create_interaction_run
from ffl.communications.policy import may_dispatch


_PURPOSE = "weekly_farmer_checkin"
_WORKFLOW_STATES = frozenset({"draft", "published", "paused"})
_AUDIENCE_KEYS = frozenset({"portal_id", "portal_role", "active_allocation"})
_TRIGGER_KEYS = frozenset({"kind", "day_of_week"})
_INTENTS = frozenset({
    "confirm", "decline", "report_deviation", "submit_evidence", "request_callback", "help", "opt_out",
})


@dataclass(frozen=True)
class WorkflowVersion:
    id: str
    workflow_id: str
    workflow_key: str
    version: int
    purpose: str
    owner_id: str
    status: str
    trigger: Mapping[str, Any]
    audience: Mapping[str, Any]
    template_id: str
    expected_intents: Tuple[str, ...]
    response_deadline_hours: int
    quiet_hours: Optional[Tuple[str, str]]
    frequency_cap: Optional[int]
    escalation_owner_id: Optional[str]
    created_at: str
    published_at: Optional[str]


@dataclass(frozen=True)
class WorkflowTarget:
    profile_id: str
    endpoint_id: str
    allocation_id: str
    portal_id: str
    locale: str


@dataclass(frozen=True)
class WorkflowRun:
    id: str
    profile_id: str
    endpoint_id: str
    allocation_id: str
    workflow_version_id: str
    interaction_run_id: str
    weekly_window: str
    context_token: str


def create_workflow_draft(
    conn,
    *,
    workflow_key: str,
    owner_id: str,
    purpose: str,
    trigger: Mapping[str, Any],
    audience: Mapping[str, Any],
    template_id: str,
    expected_intents: Sequence[str],
    response_deadline_hours: int,
    quiet_hours: Optional[Tuple[str, str]] = None,
    frequency_cap: Optional[int] = None,
    escalation_owner_id: Optional[str] = None,
) -> WorkflowVersion:
    """Append a new draft version; existing versions are never edited."""
    workflow_key = _identifier(workflow_key, "workflow_key")
    owner_id = _identifier(owner_id, "owner_id")
    template_id = _identifier(template_id, "template_id")
    escalation_owner_id = _optional_identifier(escalation_owner_id, "escalation_owner_id")
    normalized_trigger = _trigger(trigger)
    normalized_audience = _audience(conn, audience)
    normalized_intents = _intents(expected_intents)
    deadline = _positive_int(response_deadline_hours, "response_deadline_hours")
    normalized_quiet_hours = _quiet_hours(quiet_hours)
    normalized_frequency_cap = _optional_positive_int(frequency_cap, "frequency_cap")
    if purpose != _PURPOSE:
        raise ValueError("only weekly_farmer_checkin workflows are supported")
    _person_exists(conn, owner_id, "workflow owner")
    if escalation_owner_id is not None:
        _person_exists(conn, escalation_owner_id, "workflow escalation owner")
    _template(conn, template_id, purpose)

    workflow = conn.execute(
        "SELECT * FROM communication_workflows WHERE workflow_key = ?", (workflow_key,),
    ).fetchone()
    created_at = datetime.now(timezone.utc).isoformat()
    if workflow is None:
        workflow_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO communication_workflows (id, workflow_key, owner_id, created_at) VALUES (?, ?, ?, ?)",
            (workflow_id, workflow_key, owner_id, created_at),
        )
        version_number = 1
    else:
        if workflow["owner_id"] != owner_id:
            raise ValueError("workflow owner cannot change across versions")
        workflow_id = workflow["id"]
        version_number = int(conn.execute(
            "SELECT COALESCE(MAX(version), 0) AS maximum FROM communication_workflow_versions WHERE workflow_id = ?",
            (workflow_id,),
        ).fetchone()["maximum"]) + 1
    identifier = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO communication_workflow_versions
           (id, workflow_id, version, purpose, owner_id, status, trigger_json, audience_json,
            template_id, expected_intents_json, response_deadline_hours, quiet_hours_json,
            frequency_cap, escalation_owner_id, created_at, published_at)
           VALUES (?, ?, ?, ?, ?, 'draft', ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)""",
        (
            identifier, workflow_id, version_number, purpose, owner_id, _json(normalized_trigger),
            _json(normalized_audience), template_id, _json(list(normalized_intents)), deadline,
            _json(list(normalized_quiet_hours)) if normalized_quiet_hours is not None else None,
            normalized_frequency_cap, escalation_owner_id, created_at,
        ),
    )
    conn.commit()
    return workflow_version(conn, identifier)


def publish_workflow_version(conn, workflow_version_id: str) -> WorkflowVersion:
    """Publish exactly one validated draft version without modifying its capture."""
    version = workflow_version(conn, workflow_version_id)
    if version.status != "draft":
        raise ValueError("only draft workflow versions can be published")
    _validate_publishable(conn, version)
    published_at = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE communication_workflow_versions SET status = 'published', published_at = ? WHERE id = ?",
        (published_at, version.id),
    )
    conn.commit()
    return workflow_version(conn, version.id)


def publish_weekly_farmer_workflow(
    conn,
    *,
    owner_id: str,
    portal_id: Optional[str] = None,
    template_id: Optional[str] = None,
) -> WorkflowVersion:
    """Create and publish the bounded first workflow without guessing inputs.

    The convenience form is deliberately usable only when the database has one
    active portal and one published weekly template. Multi-portal or
    multi-template callers must explicitly supply the canonical identifiers.
    """
    if portal_id is None:
        portals = conn.execute(
            "SELECT id FROM customer_portals WHERE status = 'active' ORDER BY id",
        ).fetchall()
        if len(portals) != 1:
            raise ValueError("weekly workflow requires an explicit portal_id")
        portal_id = portals[0]["id"]
    if template_id is None:
        templates = conn.execute(
            """SELECT id FROM communication_templates
               WHERE purpose = ? AND status = 'published' ORDER BY id""",
            (_PURPOSE,),
        ).fetchall()
        if len(templates) != 1:
            raise ValueError("weekly workflow requires an explicit template_id")
        template_id = templates[0]["id"]
    draft = create_workflow_draft(
        conn,
        workflow_key="weekly-farmer-checkin",
        owner_id=owner_id,
        purpose=_PURPOSE,
        trigger={"kind": _PURPOSE},
        audience={"portal_id": portal_id, "portal_role": "farmer", "active_allocation": True},
        template_id=template_id,
        expected_intents=("confirm", "report_deviation", "submit_evidence", "request_callback", "help"),
        response_deadline_hours=72,
        quiet_hours=("22:00", "06:00"),
        frequency_cap=7,
        escalation_owner_id=owner_id,
    )
    return publish_workflow_version(conn, draft.id)


def pause_workflow_version(conn, workflow_version_id: str) -> WorkflowVersion:
    """Pause a published version; paused versions cannot produce new targets."""
    version = workflow_version(conn, workflow_version_id)
    if version.status != "published":
        raise ValueError("only published workflow versions can be paused")
    conn.execute("UPDATE communication_workflow_versions SET status = 'paused' WHERE id = ?", (version.id,))
    conn.commit()
    return workflow_version(conn, version.id)


def eligible_workflow_targets(
    conn,
    workflow_version_id: str,
    *,
    due_at: Union[datetime, str],
) -> Tuple[WorkflowTarget, ...]:
    """Return only current, exact farmer/allocation targets for one due instant."""
    version = workflow_version(conn, workflow_version_id)
    if version.status != "published":
        return ()
    _validate_publishable(conn, version)
    due = _instant(due_at, "due_at")
    if "day_of_week" in version.trigger and due.weekday() != version.trigger["day_of_week"]:
        return ()
    weekly_window = _weekly_window(due)
    template = _template(conn, version.template_id, version.purpose)
    candidates = conn.execute(
        """SELECT DISTINCT profile.id AS profile_id, profile.portal_id, profile.locale,
                          endpoint.id AS endpoint_id, endpoint.address, allocation.id AS allocation_id
           FROM communication_profiles profile
           JOIN customer_portals portal
             ON portal.id = profile.portal_id AND portal.status = 'active'
           JOIN portal_memberships membership
             ON membership.portal_id = profile.portal_id
            AND membership.person_id = profile.person_id
            AND membership.portal_role = 'farmer'
            AND membership.membership_status = 'active'
           JOIN communication_endpoint_verifications verification
             ON verification.profile_id = profile.id AND verification.status = 'active'
           JOIN communication_endpoints endpoint
             ON endpoint.id = verification.endpoint_id
            AND endpoint.person_id = profile.person_id AND endpoint.status = 'active'
           JOIN crop_allocations allocation ON allocation.status = 'active'
           WHERE profile.status = 'active' AND profile.portal_id = ?""",
        (version.audience["portal_id"],),
    ).fetchall()
    by_target = {}
    for row in candidates:
        key = (row["profile_id"], row["allocation_id"])
        by_target.setdefault(key, []).append(row)

    eligible = []
    for key in sorted(by_target):
        rows = by_target[key]
        endpoint_ids = {row["endpoint_id"] for row in rows}
        # A profile with several active endpoints has no selected endpoint
        # policy in this task. Do not guess.
        if len(endpoint_ids) != 1:
            continue
        row = rows[0]
        if template["locale"] != row["locale"]:
            continue
        resolution = resolve_communication_endpoint(
            conn, "loopmessage", row["address"], row["portal_id"],
            allocation_id=row["allocation_id"], received_at=due,
        )
        if resolution.state != "eligible_farmer" or resolution.endpoint_id != row["endpoint_id"]:
            continue
        sent = conn.execute(
            """SELECT COUNT(*) AS count FROM communication_workflow_runs
               WHERE profile_id = ? AND workflow_version_id = ? AND weekly_window = ?""",
            (row["profile_id"], version.id, weekly_window),
        ).fetchone()["count"]
        if not _has_dispatchable_consent(
            conn, version, resolution, row["profile_id"], row["endpoint_id"],
            row["allocation_id"], due, int(sent),
        ):
            continue
        eligible.append(WorkflowTarget(
            profile_id=row["profile_id"], endpoint_id=row["endpoint_id"],
            allocation_id=row["allocation_id"], portal_id=row["portal_id"], locale=row["locale"],
        ))
    return tuple(eligible)


def create_workflow_runs(
    conn,
    workflow_version_id: str,
    *,
    due_at: Union[datetime, str],
    now: Optional[Union[datetime, str]] = None,
) -> Tuple[WorkflowRun, ...]:
    """Create at most one immutable interaction per target/version/week.

    The returned opaque token is a transient scheduler-to-outbox value.  It is
    not copied into the workflow-run table; interaction persistence retains
    only its digest.
    """
    version = workflow_version(conn, workflow_version_id)
    due = _instant(due_at, "due_at")
    created_at = _instant(now, "now") if now is not None else datetime.now(timezone.utc)
    weekly_window = _weekly_window(due)
    expiry = created_at + timedelta(hours=version.response_deadline_hours)
    created = []
    for target in eligible_workflow_targets(conn, version.id, due_at=due):
        try:
            # The interaction and its unique weekly run are one transaction.
            # A competing scheduler can win the uniqueness race, but it cannot
            # leave this transaction's ready interaction behind.
            conn.execute("BEGIN IMMEDIATE")
            sent = conn.execute(
                """SELECT COUNT(*) AS count FROM communication_workflow_runs
                   WHERE profile_id = ? AND workflow_version_id = ? AND weekly_window = ?""",
                (target.profile_id, version.id, weekly_window),
            ).fetchone()["count"]
            existing = conn.execute(
                """SELECT 1 FROM communication_workflow_runs
                   WHERE profile_id = ? AND allocation_id = ? AND workflow_version_id = ? AND weekly_window = ?""",
                (target.profile_id, target.allocation_id, version.id, weekly_window),
            ).fetchone()
            if existing is not None or (
                version.frequency_cap is not None and int(sent) >= version.frequency_cap
            ):
                conn.rollback()
                continue
            interaction = create_interaction_run(
                conn, target.profile_id, target.endpoint_id, allocation_id=target.allocation_id,
                workflow_version_id=version.id, expected_intents=version.expected_intents,
                expires_at=expiry, created_at=created_at, commit=False,
            )
            workflow_run_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO communication_workflow_runs
                   (id, profile_id, endpoint_id, allocation_id, workflow_version_id,
                    interaction_run_id, weekly_window, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    workflow_run_id, target.profile_id, target.endpoint_id, target.allocation_id,
                    version.id, interaction.id, weekly_window, created_at.isoformat(),
                ),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            # The unique key guarantees that a competing scheduler has already
            # created the logical weekly run. Its token is intentionally never
            # recoverable here.
            continue
        except Exception:
            conn.rollback()
            raise
        created.append(WorkflowRun(
            id=workflow_run_id, profile_id=target.profile_id, endpoint_id=target.endpoint_id,
            allocation_id=target.allocation_id, workflow_version_id=version.id,
            interaction_run_id=interaction.id, weekly_window=weekly_window,
            context_token=interaction.context_token or "",
        ))
    return tuple(created)


def workflow_version(conn, workflow_version_id: str) -> WorkflowVersion:
    row = conn.execute(
        """SELECT version.*, workflow.workflow_key
           FROM communication_workflow_versions version
           JOIN communication_workflows workflow ON workflow.id = version.workflow_id
           WHERE version.id = ?""",
        (_identifier(workflow_version_id, "workflow_version_id"),),
    ).fetchone()
    if row is None:
        raise ValueError("workflow version does not exist")
    return WorkflowVersion(
        id=row["id"], workflow_id=row["workflow_id"], workflow_key=row["workflow_key"],
        version=int(row["version"]), purpose=row["purpose"], owner_id=row["owner_id"],
        status=row["status"], trigger=_json_object(row["trigger_json"], "workflow trigger"),
        audience=_json_object(row["audience_json"], "workflow audience"), template_id=row["template_id"],
        expected_intents=tuple(_json_array(row["expected_intents_json"], "workflow expected intents")),
        response_deadline_hours=int(row["response_deadline_hours"]),
        quiet_hours=_stored_quiet_hours(row["quiet_hours_json"]), frequency_cap=row["frequency_cap"],
        escalation_owner_id=row["escalation_owner_id"], created_at=row["created_at"],
        published_at=row["published_at"],
    )


def _validate_publishable(conn, version: WorkflowVersion) -> None:
    if version.purpose != _PURPOSE:
        raise ValueError("unsupported workflow purpose")
    _trigger(version.trigger)
    _audience(conn, version.audience)
    _intents(version.expected_intents)
    _positive_int(version.response_deadline_hours, "response_deadline_hours")
    _quiet_hours(version.quiet_hours)
    _optional_positive_int(version.frequency_cap, "frequency_cap")
    _template(conn, version.template_id, version.purpose, published=True)


def _has_dispatchable_consent(conn, version, resolution, profile_id, endpoint_id, allocation_id, due, messages_sent):
    consents = conn.execute(
        """SELECT scope_type, scope_id FROM communication_scoped_consents
           WHERE profile_id = ? AND endpoint_id = ? AND purpose = ?
             AND channel = 'whatsapp' AND status = 'active'
           ORDER BY scope_type, scope_id""",
        (profile_id, endpoint_id, version.purpose),
    ).fetchall()
    for consent in consents:
        decision = may_dispatch(
            conn, resolution, version.purpose, consent["scope_type"], consent["scope_id"],
            allocation_id=allocation_id, dispatch_at=due, quiet_hours=version.quiet_hours,
            messages_sent=messages_sent, frequency_cap=version.frequency_cap,
        )
        if decision.allowed:
            return True
    return False


def _template(conn, template_id: str, purpose: str, *, published: bool = False):
    row = conn.execute("SELECT * FROM communication_templates WHERE id = ?", (template_id,)).fetchone()
    if row is None or row["purpose"] != purpose:
        raise ValueError("workflow template does not match its purpose")
    if published and row["status"] != "published":
        raise ValueError("workflow requires a published template")
    return row


def _audience(conn, value: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("workflow audience must be a typed descriptor")
    keys = set(value)
    unknown = keys - _AUDIENCE_KEYS
    if unknown:
        raise ValueError("unknown workflow audience keys")
    if keys != _AUDIENCE_KEYS:
        raise ValueError("weekly farmer audience requires portal_id, portal_role, and active_allocation")
    portal_id = _identifier(value.get("portal_id"), "workflow audience portal_id")
    if value.get("portal_role") != "farmer" or value.get("active_allocation") is not True:
        raise ValueError("weekly farmer audience must select active farmer allocations")
    portal = conn.execute("SELECT status FROM customer_portals WHERE id = ?", (portal_id,)).fetchone()
    if portal is None or portal["status"] != "active":
        raise ValueError("workflow audience requires an active portal")
    return {"portal_id": portal_id, "portal_role": "farmer", "active_allocation": True}


def _trigger(value: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("workflow trigger must be a typed descriptor")
    unknown = set(value) - _TRIGGER_KEYS
    if unknown or value.get("kind") != _PURPOSE:
        raise ValueError("unsupported workflow trigger")
    day = value.get("day_of_week")
    if day is not None and (not isinstance(day, int) or isinstance(day, bool) or not 0 <= day <= 6):
        raise ValueError("workflow trigger day_of_week is invalid")
    result = {"kind": _PURPOSE}
    if day is not None:
        result["day_of_week"] = day
    return result


def _intents(value: Sequence[str]) -> Tuple[str, ...]:
    if isinstance(value, (str, bytes)):
        raise ValueError("workflow expected intents are invalid")
    try:
        normalized = tuple(value)
    except TypeError as error:
        raise ValueError("workflow expected intents are invalid") from error
    if not normalized or len(set(normalized)) != len(normalized) or any(intent not in _INTENTS for intent in normalized):
        raise ValueError("workflow expected intents are invalid")
    return normalized


def _quiet_hours(value: Optional[Tuple[str, str]]) -> Optional[Tuple[str, str]]:
    if value is None:
        return None
    if not isinstance(value, tuple) or len(value) != 2 or not all(isinstance(item, str) for item in value):
        raise ValueError("workflow quiet hours are invalid")
    try:
        datetime.strptime(value[0], "%H:%M")
        datetime.strptime(value[1], "%H:%M")
    except ValueError as error:
        raise ValueError("workflow quiet hours are invalid") from error
    return value


def _stored_quiet_hours(value: Optional[str]) -> Optional[Tuple[str, str]]:
    if value is None:
        return None
    values = _json_array(value, "workflow quiet hours")
    return _quiet_hours(tuple(values))


def _json_object(value: Any, label: str) -> Mapping[str, Any]:
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError) as error:
        raise ValueError(label + " is invalid") from error
    if not isinstance(parsed, dict):
        raise ValueError(label + " is invalid")
    return parsed


def _json_array(value: Any, label: str) -> list[Any]:
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError) as error:
        raise ValueError(label + " is invalid") from error
    if not isinstance(parsed, list):
        raise ValueError(label + " is invalid")
    return parsed


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 128:
        raise ValueError(label + " is required")
    return value.strip()


def _optional_identifier(value: object, label: str) -> Optional[str]:
    return None if value is None else _identifier(value, label)


def _positive_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(label + " must be positive")
    return value


def _optional_positive_int(value: object, label: str) -> Optional[int]:
    return None if value is None else _positive_int(value, label)


def _person_exists(conn, person_id: str, label: str) -> None:
    if conn.execute("SELECT 1 FROM people WHERE id = ?", (person_id,)).fetchone() is None:
        raise ValueError(label + " does not exist")


def _instant(value: Union[datetime, str], label: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
        except ValueError as error:
            raise ValueError(label + " must be timezone-aware") from error
    else:
        raise ValueError(label + " must be timezone-aware")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(label + " must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _weekly_window(due: datetime) -> str:
    year, week, _weekday = due.date().isocalendar()
    return "{0}-W{1:02d}".format(year, week)


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
