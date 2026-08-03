"""Provider-neutral field information request workflow.

This ledger creates a bounded request for a known allocation and person.  It
does not resolve work, create a field signal, retain communication content, or
send a message.  A future LoopMessage (or other) adapter may mark a request
``dispatched`` only after its independent endpoint, consent, template, and
provider-capability gates pass.
"""

from datetime import datetime
from typing import List, Optional

from ffl.domain.models import FieldInformationRequest
from ffl.persistence import repository


EXPIRY_SYSTEM_ACTOR = "system:field-information-expiry"


def create_information_request(
    conn, allocation_id: str, target_person_id: str, request_kind: str,
    evidence_required: bool, due_at: str, request_copy_en: str, request_copy_hi: str,
    idempotency_key: str, *, work_item_id: Optional[str] = None,
    initiated_by_person_id: Optional[str] = None, initiated_by_system_key: Optional[str] = None,
) -> FieldInformationRequest:
    """Create or replay the same logical draft request.

    ``request_copy_en`` and ``request_copy_hi`` are final, reviewed words for
    the recipient.  Creating a request neither sends it nor authorizes a
    delivery provider to send it later.
    """
    return repository.create_field_information_request(
        conn, allocation_id, target_person_id, request_kind, evidence_required, due_at,
        request_copy_en, request_copy_hi, idempotency_key, work_item_id=work_item_id,
        initiated_by_person_id=initiated_by_person_id,
        initiated_by_system_key=initiated_by_system_key,
    )


def ready_information_request(
    conn, request_id: str, *, actor_person_id: Optional[str] = None,
    actor_system_key: Optional[str] = None, reason: str = "reviewed_and_ready",
) -> FieldInformationRequest:
    """Make a reviewed request eligible for a future delivery adapter.

    ``ready`` is not a dispatch.  It leaves all endpoint, consent, template,
    language, and provider capability checks to the adapter that may later
    send it.
    """
    return repository.transition_field_information_request(
        conn, request_id, "ready", actor_person_id=actor_person_id,
        actor_system_key=actor_system_key, reason=reason,
    )


def mark_information_request_dispatched(
    conn, request_id: str, *, actor_system_key: str, reason: str = "provider_dispatch_accepted",
) -> FieldInformationRequest:
    """Record a future adapter's accepted dispatch; this function sends nothing.

    The caller is deliberately a system actor: it is the adapter's job to
    prove a selected endpoint, valid consent, approved template, and supported
    provider capability before this durable state change.
    """
    return repository.transition_field_information_request(
        conn, request_id, "dispatched", actor_system_key=actor_system_key, reason=reason,
    )


def mark_information_request_responded(
    conn, request_id: str, *, actor_system_key: str, reason: str = "response_received",
) -> FieldInformationRequest:
    """Record that a response arrived, without converting it into farm truth.

    Intake must still create a separately reviewable candidate/evidence record
    and use the canonical field workflow before any farm state changes.
    """
    return repository.transition_field_information_request(
        conn, request_id, "responded", actor_system_key=actor_system_key, reason=reason,
    )


def cancel_information_request(
    conn, request_id: str, *, actor_person_id: Optional[str] = None,
    actor_system_key: Optional[str] = None, reason: str,
) -> FieldInformationRequest:
    """Close an unanswered request; immutable copy is never edited in place."""
    return repository.transition_field_information_request(
        conn, request_id, "cancelled", actor_person_id=actor_person_id,
        actor_system_key=actor_system_key, reason=reason,
    )


def expire_due_information_requests(
    conn, as_of: str, *, system_actor_key: str = EXPIRY_SYSTEM_ACTOR,
) -> List[FieldInformationRequest]:
    """Deterministically expire unfulfilled requests due at or before ``as_of``.

    This worker-safe entry point is intentionally independent from message
    sending.  It can be scheduled even before any provider is enabled.
    """
    try:
        cutoff = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as error:
        raise ValueError("as_of must be an ISO-8601 timestamp") from error
    if cutoff.tzinfo is None:
        raise ValueError("as_of must include a timezone")
    expired = []
    for request in repository.list_field_information_requests(conn):
        if request.status not in {"draft", "ready", "dispatched"}:
            continue
        due_at = datetime.fromisoformat(request.due_at.replace("Z", "+00:00"))
        if due_at <= cutoff:
            try:
                expired.append(repository.transition_field_information_request(
                    conn, request.id, "expired", actor_system_key=system_actor_key,
                    reason="due_at_elapsed",
                ))
            except ValueError:
                # A competing worker may have closed the same request after we
                # listed it.  Treat an already-expired request as the same
                # deterministic outcome; any other state change stays visible.
                current = repository.get_field_information_request(conn, request.id)
                if current is None or current.status != "expired":
                    raise
    return expired
