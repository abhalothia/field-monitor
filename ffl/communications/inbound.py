"""Exact, review-only routing for private WhatsApp inbound events.

Inbound contact data is deliberately not an authority.  A known endpoint is
useful only after it has been bound to the exact dispatched interaction through
the provider reply ID or the one-way context-token digest.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Dict, Optional

from ffl.communications import persistence
from ffl.communications.interactions import (
    find_interaction_for_inbound,
    mark_interaction_responded,
)


_INTENTS = frozenset({
    "confirm", "decline", "report_deviation", "submit_evidence",
    "request_callback", "help", "opt_out",
})
_EXACT_TEXT_INTENTS = {
    "confirm": "confirm",
    "decline": "decline",
    "report_deviation": "report_deviation",
    "submit_evidence": "submit_evidence",
    "request_callback": "request_callback",
    "help": "help",
    "stop": "opt_out",
    "opt_out": "opt_out",
}
_REDACTED_SUMMARIES = {
    "report_deviation": "field_deviation_reported",
    "submit_evidence": "evidence_submitted",
}


@dataclass(frozen=True)
class InboundOutcome:
    event_id: str
    kind: str
    interaction_run_id: Optional[str] = None
    candidate_id: Optional[str] = None


def process_inbound_event(conn, provider, event: Dict[str, Any], stored_event: Dict[str, Any]) -> InboundOutcome:
    """Route one normalized inbound event without inferring identity or farm scope.

    This function deliberately recognizes only exact, approved intent tokens;
    ordinary prose is retained only in the protected receipt and gets a
    redacted context-review record.  No branch accepts work, evidence, a
    diagnosis, or a request automatically.
    """
    event_id = stored_event["id"]
    previous = persistence.get_inbound_outcome_for_event(conn, event_id)
    if previous is not None:
        return _outcome(previous)
    existing_candidate = persistence.get_candidate_for_event(conn, event_id)
    if existing_candidate is not None:
        interaction_run_id = _recover_candidate_lifecycle(conn, existing_candidate)
        return _persist_outcome(
            conn, event_id, "review_candidate",
            interaction_run_id=interaction_run_id,
            candidate_id=existing_candidate["id"],
        )
    existing_review = persistence.get_inbound_review_for_event(conn, event_id)
    if existing_review is not None:
        return _persist_outcome(conn, event_id, existing_review["state"])

    endpoint = _endpoint_for_stored_event(conn, provider, stored_event)
    attachments = [
        persistence.add_attachment(conn, event_id, source, event["message_type"])
        for source in event.get("attachments", [])
    ]
    if endpoint is None:
        return _review(conn, event_id, "identity_review", "endpoint_unresolved")

    interaction = find_interaction_for_inbound(
        conn,
        provider.name,
        endpoint["id"],
        event.get("reply_to_message_id"),
        event.get("passthrough"),
        context_token_hash=event.get("_ffl_context_token_hash"),
    )
    if interaction is None:
        return _review(conn, event_id, "context_review", "interaction_unresolved")

    intent = _intent(event)
    if intent is None:
        return _review(conn, event_id, "context_review", "intent_unrecognized")
    # An opt-out must always be honored once the interaction itself is exact;
    # a workflow cannot remove a recipient's ability to revoke that scope.
    if intent != "opt_out" and intent not in interaction.expected_intents:
        return _review(conn, event_id, "context_review", "intent_not_expected")

    if intent == "opt_out":
        _revoke_interaction_scope(conn, interaction)
        _mark_responded(conn, interaction.id)
        return _persist_outcome(conn, event_id, "opt_out", interaction_run_id=interaction.id)

    prompt_id = interaction.legacy_prompt_id
    if intent not in {"report_deviation", "submit_evidence"}:
        # Confirmation, decline, help, and callback requests are meaningful
        # replies, but not field signals or exceptions.  Keep them out of the
        # canonical acceptance APIs until a separately approved handler exists.
        _mark_responded(conn, interaction.id)
        if prompt_id is not None:
            _mark_prompt_responded(conn, prompt_id)
        return _review(
            conn, event_id, "context_review", "intent_requires_human_handling",
            interaction_run_id=interaction.id,
        )

    kind = "exception" if intent == "report_deviation" else "signal"
    candidate = persistence.create_candidate(
        conn,
        event_id,
        prompt_id,
        interaction.allocation_id,
        interaction.work_item_id,
        endpoint["id"],
        kind,
        {
            # A review candidate is bounded to one report, not an endpoint
            # conversation archive.  Acceptance remains a separate canonical
            # signal/exception operation.
            "intent": intent,
            "redacted_summary": _REDACTED_SUMMARIES[intent],
            "message_type": event["message_type"],
            "attachment_ids": [attachment["id"] for attachment in attachments],
            "context_resolved": True,
            "interaction_run_id": interaction.id,
            "observed_at": event.get("raw", {}).get("observed_at"),
        },
    )
    _mark_responded(conn, interaction.id)
    if prompt_id is not None:
        _mark_prompt_responded(conn, prompt_id)
    return _persist_outcome(
        conn, event_id, "review_candidate", interaction_run_id=interaction.id,
        candidate_id=candidate["id"],
    )


def _endpoint_for_stored_event(conn, provider, stored_event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    endpoint_id = stored_event.get("endpoint_id")
    if not endpoint_id:
        return None
    row = conn.execute(
        "SELECT * FROM communication_endpoints WHERE id = ? AND provider = ? AND status = 'active'",
        (endpoint_id, provider.name),
    ).fetchone()
    return dict(row) if row is not None else None


def _intent(event: Dict[str, Any]) -> Optional[str]:
    provided = event.get("intent")
    if isinstance(provided, str) and provided in _INTENTS:
        return provided
    text = event.get("text")
    if not isinstance(text, str):
        return None
    return _EXACT_TEXT_INTENTS.get(text.strip().casefold())


def _review(conn, event_id: str, state: str, reason: str, **references: Optional[str]) -> InboundOutcome:
    persistence.create_inbound_review(conn, event_id, state, reason)
    return _persist_outcome(conn, event_id, state, **references)


def _persist_outcome(conn, event_id: str, kind: str, **references: Optional[str]) -> InboundOutcome:
    stored = persistence.create_inbound_outcome(conn, event_id, kind, **references)
    persistence.update_event_status(conn, event_id, "review_required" if kind != "opt_out" else "processed")
    return _outcome(stored)


def _outcome(row: Dict[str, Any]) -> InboundOutcome:
    return InboundOutcome(
        event_id=row["event_id"], kind=row["kind"],
        interaction_run_id=row.get("interaction_run_id"), candidate_id=row.get("candidate_id"),
    )


def _mark_responded(conn, interaction_run_id: str) -> None:
    try:
        mark_interaction_responded(conn, interaction_run_id)
    except ValueError:
        # A duplicate/recovery may observe the run after it has already closed.
        pass


def _mark_prompt_responded(conn, prompt_id: str) -> None:
    prompt = conn.execute("SELECT status FROM communication_prompts WHERE id = ?", (prompt_id,)).fetchone()
    if prompt is not None and prompt["status"] in {"accepted", "scheduled", "delivered"}:
        persistence.update_prompt(conn, prompt_id, "responded")


def _recover_candidate_lifecycle(conn, candidate: Dict[str, Any]) -> Optional[str]:
    """Finish local lifecycle bookkeeping after a crash before receipt completion."""
    if candidate.get("prompt_id"):
        _mark_prompt_responded(conn, candidate["prompt_id"])
    # Drafts were created by the pre-existing review-candidate API.  They may
    # be malformed historical rows, so no recovery path is allowed to infer a
    # run from endpoint history.
    try:
        interaction_run_id = json.loads(candidate["draft_json"]).get("interaction_run_id")
    except (TypeError, ValueError):
        interaction_run_id = None
    if isinstance(interaction_run_id, str):
        _mark_responded(conn, interaction_run_id)
        return interaction_run_id
    return None


def _revoke_interaction_scope(conn, interaction) -> None:
    """Atomically revoke exact scope and arbitrate every matching future send.

    Suppression takes the durable outbox row lock first, then consent/audit are
    mutated in the same transaction.  A final-send gate therefore either wins
    before this transaction (and the opt-out never claims suppression) or is
    blocked until the committed suppression makes its conditional gate fail.
    """
    if interaction.profile_id is None or interaction.allocation_id is None:
        return
    purpose = _interaction_purpose(conn, interaction.id)
    if purpose is None:
        return
    endpoint = conn.execute(
        "SELECT person_id FROM communication_endpoints WHERE id = ?", (interaction.endpoint_id,),
    ).fetchone()
    if endpoint is None:
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        active = conn.execute(
            """SELECT 1 FROM communication_scoped_consents
               WHERE profile_id = ? AND endpoint_id = ? AND purpose = ?
                 AND scope_type = 'crop_allocation' AND scope_id = ?
                 AND channel = 'whatsapp' AND status = 'active'""",
            (interaction.profile_id, interaction.endpoint_id, purpose, interaction.allocation_id),
        ).fetchone()
        if active is None:
            conn.commit()
            return
        _suppress_future_runs(conn, interaction, commit=False)
        persistence.set_scoped_consent(
            conn, interaction.profile_id, interaction.endpoint_id, purpose,
            "crop_allocation", interaction.allocation_id, False,
            "exact inbound interaction opt-out", endpoint["person_id"], commit=False,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _suppress_future_runs(conn, interaction, *, commit: bool = True) -> None:
    if interaction.allocation_id is None:
        return
    purpose = _interaction_purpose(conn, interaction.id)
    if purpose is None:
        return
    rows = conn.execute(
        """SELECT run.id, run.legacy_prompt_id
           FROM communication_interaction_runs run
           LEFT JOIN communication_workflow_versions workflow ON workflow.id = run.workflow_version_id
           LEFT JOIN communication_prompts prompt ON prompt.id = run.legacy_prompt_id
           LEFT JOIN communication_templates legacy_template ON legacy_template.id = prompt.template_id
           WHERE run.endpoint_id = ?
             AND ((? IS NULL AND run.profile_id IS NULL) OR run.profile_id = ?)
             AND run.allocation_id = ? AND run.status IN ('ready', 'dispatching')
             AND COALESCE(workflow.purpose, legacy_template.purpose) = ?""",
        (
            interaction.endpoint_id, interaction.profile_id, interaction.profile_id,
            interaction.allocation_id, purpose,
        ),
    ).fetchall()
    for row in rows:
        entry, _created = persistence.create_outbox_entry(
            conn, row["id"], row["legacy_prompt_id"], commit=commit,
        )
        if entry["status"] in {"pending", "dispatching"} and persistence.suppress_outbox_if_unreserved(
            conn, row["id"], "scoped_opt_out", commit=commit,
        ):
            conn.execute(
                "UPDATE communication_interaction_runs SET status = 'cancelled' "
                "WHERE id = ? AND status IN ('ready', 'dispatching')",
                (row["id"],),
            )
            if commit:
                conn.commit()


def _interaction_purpose(conn, interaction_run_id: str) -> Optional[str]:
    row = conn.execute(
        """SELECT COALESCE(workflow.purpose, legacy_template.purpose) AS purpose
           FROM communication_interaction_runs run
           LEFT JOIN communication_workflow_versions workflow ON workflow.id = run.workflow_version_id
           LEFT JOIN communication_prompts prompt ON prompt.id = run.legacy_prompt_id
           LEFT JOIN communication_templates legacy_template ON legacy_template.id = prompt.template_id
           WHERE run.id = ?""",
        (interaction_run_id,),
    ).fetchone()
    return row["purpose"] if row is not None and isinstance(row["purpose"], str) else None
