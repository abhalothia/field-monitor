"""Policy-controlled, exactly-once template dispatch for communications runs.

Only durable identifiers and lifecycle state enter the outbox.  The contact,
approved template parameters, and opaque context token are assembled in memory
for the one provider call, then discarded.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hmac
import json
from typing import Any, Dict, Optional, Tuple, Union

from ffl.communications import persistence
from ffl.communications.identity import resolve_communication_endpoint
from ffl.communications.interactions import (
    context_token_digest,
    context_token_for_run,
    interaction_run,
    record_interaction_dispatch,
    update_interaction_dispatch_status,
)
from ffl.communications.policy import may_dispatch
from ffl.communications.ports import (
    CommunicationsProvider,
    ProviderAmbiguousError,
    ProviderRejectedError,
)


@dataclass(frozen=True)
class DispatchResult:
    interaction_run_id: str
    status: str
    provider_message_id: Optional[str] = None
    reason: Optional[str] = None


def dispatch_ready_interaction(
    conn,
    provider: CommunicationsProvider,
    run_id: str,
    now: Union[datetime, str],
    *,
    context_token: Optional[str] = None,
) -> DispatchResult:
    """Dispatch one ready interaction, never blindly repeating a provider call."""
    return _dispatch_interaction(conn, provider, run_id, now, context_token=context_token)


def dispatch_due_workflows(
    conn,
    provider: CommunicationsProvider,
    now: Union[datetime, str],
) -> Tuple[DispatchResult, ...]:
    """Attempt each already-created weekly workflow interaction exactly once.

    Scheduling is intentionally separate from this worker entry point: Task 5
    creates the immutable workflow/interaction capture, and this function only
    consumes captures that are still ready.
    """
    rows = conn.execute(
        """SELECT interaction_run_id
           FROM communication_workflow_runs workflow_run
           JOIN communication_interaction_runs interaction
             ON interaction.id = workflow_run.interaction_run_id
           WHERE interaction.status = 'ready'
           ORDER BY workflow_run.created_at, workflow_run.id""",
    ).fetchall()
    return tuple(
        _dispatch_interaction(conn, provider, row["interaction_run_id"], now, context_token=None)
        for row in rows
    )


def reconcile_outbox_messages(conn, provider: CommunicationsProvider) -> int:
    """Reconcile an ambiguous dispatch by message ID; never retry the send."""
    reconciled = 0
    for entry in persistence.outbox_requiring_reconciliation(conn):
        if entry["status"] == "dispatching":
            # A process may have stopped after the durable pre-call transition.
            # Treat it as ambiguous: the next worker may reconcile callbacks,
            # but it must not issue another provider request.
            persisted = persistence.update_outbox_entry(conn, entry["interaction_run_id"], "unknown")
            _sync_legacy_prompt(conn, persisted, "unknown")
            continue
        message_id = entry["provider_message_id"]
        if not message_id:
            # Only a provider callback correlated by its message ID or the raw
            # token echoed by the provider can repair this state.
            continue
        try:
            status = provider.get_message_status(message_id)
        except Exception:
            continue
        if status is None:
            continue
        desired = {"processing": "accepted", "failed": "failed", "delivered": "delivered", "unknown": "unknown"}.get(status.status)
        if desired is None:
            continue
        try:
            update_interaction_dispatch_status(conn, entry["interaction_run_id"], desired)
        except ValueError:
            pass
        if desired in {"accepted", "delivered"}:
            persistence.update_outbox_entry(
                conn, entry["interaction_run_id"], "dispatched", provider_message_id=status.provider_message_id,
            )
        elif desired == "failed":
            persistence.update_outbox_entry(
                conn, entry["interaction_run_id"], "failed", provider_message_id=status.provider_message_id,
            )
        reconciled += 1
    return reconciled


def record_outbox_callback(
    conn,
    interaction_run_id: str,
    provider_message_id: Optional[str],
    status: str,
) -> None:
    """Apply a callback only after interaction correlation has proven its run."""
    entry = persistence.outbox_entry(conn, interaction_run_id)
    if entry is None:
        return
    if status in {"accepted", "scheduled", "delivered"}:
        next_status = "dispatched"
    elif status == "failed":
        next_status = "failed"
    else:
        next_status = "unknown"
    try:
        persistence.update_outbox_entry(
            conn, interaction_run_id, next_status, provider_message_id=provider_message_id,
        )
    except ValueError:
        # A duplicate/late callback is observational only; it cannot open a
        # new send opportunity or replace an established message binding.
        return


def _dispatch_interaction(
    conn,
    provider: CommunicationsProvider,
    run_id: str,
    now: Union[datetime, str],
    *,
    context_token: Optional[str],
) -> DispatchResult:
    instant = _instant(now)
    run = interaction_run(conn, run_id)
    entry, _created = persistence.create_outbox_entry(conn, run.id, run.legacy_prompt_id)
    if entry["status"] != "pending":
        return DispatchResult(run.id, entry["status"], entry["provider_message_id"], entry["policy_code"])
    details = _dispatch_details(conn, provider, run.id, instant)
    if details is None:
        persisted = persistence.update_outbox_entry(conn, run.id, "suppressed", policy_code="dispatch_not_allowed")
        _sync_legacy_prompt(conn, persisted, "failed")
        return DispatchResult(run.id, "suppressed", reason=persisted["policy_code"])
    policy, template, endpoint, parameters = details
    if not policy["allowed"]:
        persisted = persistence.update_outbox_entry(conn, run.id, "suppressed", policy_code=policy["code"])
        _sync_legacy_prompt(conn, persisted, "failed")
        return DispatchResult(run.id, "suppressed", reason=policy["code"])

    try:
        outbound_token = _context_token_for_dispatch(
            run.id, endpoint["context_token_hash"], context_token,
        )
    except ValueError:
        persisted = persistence.update_outbox_entry(conn, run.id, "suppressed", policy_code="context_token_invalid")
        _sync_legacy_prompt(conn, persisted, "failed")
        return DispatchResult(run.id, "suppressed", reason=persisted["policy_code"])
    # The conditional update is the durable worker claim. A losing worker
    # returns the established lifecycle and never reaches provider.send_template.
    if not persistence.claim_outbox_dispatch(conn, run.id):
        current = persistence.outbox_entry(conn, run.id)
        if current is None:
            raise RuntimeError("claimed communication outbox entry disappeared")
        return DispatchResult(run.id, current["status"], current["provider_message_id"], current["policy_code"])
    # A scoped opt-out can arrive while this worker owns a dispatching entry.
    # Re-read the complete mutable policy and the outbox state after the claim,
    # immediately before the irreversible provider call.  A suppressing
    # opt-out wins and no provider request is made.
    current = persistence.outbox_entry(conn, run.id)
    details = _dispatch_details(conn, provider, run.id, instant)
    if current is None or current["status"] != "dispatching" or details is None:
        if current is not None and current["status"] == "dispatching":
            persisted = persistence.update_outbox_entry(conn, run.id, "suppressed", policy_code="dispatch_not_allowed")
            _sync_legacy_prompt(conn, persisted, "failed")
            return DispatchResult(run.id, "suppressed", reason=persisted["policy_code"])
        return DispatchResult(
            run.id,
            "suppressed" if current is None else current["status"],
            None if current is None else current["provider_message_id"],
            None if current is None else current["policy_code"],
        )
    policy, template, endpoint, parameters = details
    if not policy["allowed"]:
        persisted = persistence.update_outbox_entry(conn, run.id, "suppressed", policy_code=policy["code"])
        _sync_legacy_prompt(conn, persisted, "failed")
        return DispatchResult(run.id, "suppressed", reason=policy["code"])
    try:
        sent = provider.send_template(
            endpoint["address"], provider.sender_id, template["provider_template_id"],
            template["locale"], parameters, outbound_token,
        )
    except ProviderRejectedError as error:
        persisted = persistence.update_outbox_entry(conn, run.id, "failed")
        if error.error_code == 500 and run.legacy_prompt_id:
            persistence.set_consent(
                conn, endpoint["endpoint_id"], template["purpose"], False,
                "LoopMessage synchronous error_code 500",
            )
        _sync_legacy_prompt(conn, persisted, "failed")
        return DispatchResult(run.id, "failed")
    except ProviderAmbiguousError:
        persisted = persistence.update_outbox_entry(conn, run.id, "unknown")
        _sync_legacy_prompt(conn, persisted, "unknown")
        return DispatchResult(run.id, "unknown")
    except Exception:
        # An unclassified provider failure may happen after acceptance.  Keep
        # this as unknown until a message-ID/token-correlated callback repairs it.
        persisted = persistence.update_outbox_entry(conn, run.id, "unknown")
        _sync_legacy_prompt(conn, persisted, "unknown")
        return DispatchResult(run.id, "unknown")

    dispatch_status = sent.status if sent.status in {"accepted", "scheduled", "delivered", "failed", "unknown"} else "accepted"
    record_interaction_dispatch(conn, run.id, sent.provider_message_id, status=dispatch_status)
    if dispatch_status == "unknown":
        persisted = persistence.update_outbox_entry(
            conn, run.id, "unknown", provider_message_id=sent.provider_message_id,
        )
        _sync_legacy_prompt(conn, persisted, "unknown")
        return DispatchResult(run.id, "unknown", sent.provider_message_id)
    if dispatch_status == "failed":
        persisted = persistence.update_outbox_entry(
            conn, run.id, "failed", provider_message_id=sent.provider_message_id,
        )
        _sync_legacy_prompt(conn, persisted, "failed")
        return DispatchResult(run.id, "failed", sent.provider_message_id)
    persisted = persistence.update_outbox_entry(
        conn, run.id, "dispatched", provider_message_id=sent.provider_message_id,
    )
    _sync_legacy_prompt(conn, persisted, dispatch_status)
    return DispatchResult(run.id, "dispatched", sent.provider_message_id)


def _dispatch_details(conn, provider: CommunicationsProvider, run_id: str, now: datetime):
    """Re-read all mutable policy/template state immediately before sending."""
    row = conn.execute(
        """SELECT interaction.*, endpoint.provider AS endpoint_provider, endpoint.address, endpoint.locale AS endpoint_locale,
                  profile.portal_id, profile.locale AS profile_locale,
                  workflow.status AS workflow_status, workflow.purpose AS workflow_purpose,
                  workflow.template_id AS workflow_template_id, workflow.quiet_hours_json,
                  workflow.frequency_cap, workflow_run.weekly_window,
                  prompt.template_id AS legacy_template_id
           FROM communication_interaction_runs interaction
           JOIN communication_endpoints endpoint ON endpoint.id = interaction.endpoint_id
           LEFT JOIN communication_profiles profile ON profile.id = interaction.profile_id
           LEFT JOIN communication_workflow_versions workflow ON workflow.id = interaction.workflow_version_id
           LEFT JOIN communication_workflow_runs workflow_run ON workflow_run.interaction_run_id = interaction.id
           LEFT JOIN communication_prompts prompt ON prompt.id = interaction.legacy_prompt_id
           WHERE interaction.id = ?""",
        (run_id,),
    ).fetchone()
    if row is None or row["endpoint_provider"] != getattr(provider, "name", None):
        return None
    template_id = row["workflow_template_id"] or row["legacy_template_id"]
    if not template_id:
        return None
    template = conn.execute("SELECT * FROM communication_templates WHERE id = ?", (template_id,)).fetchone()
    if not _approved_template(template, row, provider):
        return None
    parameters: Dict[str, str] = {}
    if not _valid_parameters(parameters):
        return None
    if row["profile_id"] is None:
        return {"allowed": False, "code": "profile_not_active"}, template, row, parameters
    if row["workflow_version_id"] is not None and (
        row["workflow_status"] != "published" or row["workflow_purpose"] != template["purpose"]
    ):
        return {"allowed": False, "code": "workflow_not_published"}, template, row, parameters
    if row["profile_locale"] != template["locale"]:
        return {"allowed": False, "code": "locale_mismatch"}, template, row, parameters
    resolution = resolve_communication_endpoint(
        conn, provider.name, row["address"], row["portal_id"],
        allocation_id=row["allocation_id"], received_at=now,
    )
    consents = conn.execute(
        """SELECT scope_type, scope_id FROM communication_scoped_consents
           WHERE profile_id = ? AND endpoint_id = ? AND purpose = ?
             AND channel = 'whatsapp' AND status = 'active'
           ORDER BY scope_type, scope_id""",
        (row["profile_id"], row["endpoint_id"], template["purpose"]),
    ).fetchall()
    quiet_hours = _quiet_hours(row["quiet_hours_json"])
    sent = (
        persistence.workflow_dispatch_count(
            conn, row["profile_id"], row["workflow_version_id"], row["weekly_window"],
        )
        if row["workflow_version_id"] is not None and row["weekly_window"] is not None
        else 0
    )
    last_code = "consent_not_active"
    for consent in consents:
        decision = may_dispatch(
            conn, resolution, template["purpose"], consent["scope_type"], consent["scope_id"],
            allocation_id=row["allocation_id"], dispatch_at=now, quiet_hours=quiet_hours,
            messages_sent=sent, frequency_cap=row["frequency_cap"],
        )
        if decision.allowed:
            return {"allowed": True, "code": "allowed"}, template, row, parameters
        last_code = decision.code
    return {"allowed": False, "code": last_code}, template, row, parameters


def _approved_template(template, row, provider: CommunicationsProvider) -> bool:
    return bool(
        template is not None
        and template["status"] == "published"
        and template["provider_template_id"]
        and template["provider_approval_state"] == "approved"
        and template["locale"] == row["endpoint_locale"]
        and getattr(provider, "whatsapp_capability_enabled", False)
        and getattr(provider, "sender_id", None)
    )


def _valid_parameters(parameters: Dict[str, str]) -> bool:
    # This task has no parameterized-template capture.  An explicit empty map
    # is the only approved parameter set until a later schema authorizes named
    # values and their permitted source fields.
    return isinstance(parameters, dict) and parameters == {}


def _context_token_for_dispatch(
    interaction_run_id: str, expected_digest: str, supplied: Optional[str],
) -> str:
    regenerated = context_token_for_run(interaction_run_id)
    if context_token_digest(regenerated) != expected_digest:
        raise ValueError("context token key does not match the interaction capture")
    if supplied is not None and (
        not isinstance(supplied, str) or not hmac.compare_digest(supplied, regenerated)
    ):
        raise ValueError("supplied context token does not match the interaction capture")
    return regenerated


def _quiet_hours(value: Optional[str]) -> Optional[Tuple[str, str]]:
    if value is None:
        return None
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, list) or len(parsed) != 2 or not all(isinstance(item, str) for item in parsed):
        return None
    return parsed[0], parsed[1]


def _sync_legacy_prompt(conn, entry: Dict[str, Any], status: str) -> None:
    prompt_id = entry.get("legacy_prompt_id")
    if not prompt_id:
        return
    prompt = conn.execute("SELECT status FROM communication_prompts WHERE id = ?", (prompt_id,)).fetchone()
    if prompt is None or prompt["status"] != "pending":
        return
    desired = status if status in {"accepted", "scheduled", "delivered", "failed", "unknown"} else "accepted"
    if desired == "accepted":
        persistence.create_delivery_attempt(conn, prompt_id, "accepted", entry.get("provider_message_id"))
    elif desired in {"failed", "unknown"}:
        persistence.create_delivery_attempt(conn, prompt_id, desired, entry.get("provider_message_id"))
    persistence.update_prompt(conn, prompt_id, desired, entry.get("provider_message_id"))


def _instant(value: Union[datetime, str]) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
        except ValueError as error:
            raise ValueError("dispatch time is invalid") from error
    else:
        raise ValueError("dispatch time is invalid")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("dispatch time is invalid")
    return parsed.astimezone(timezone.utc)
