"""Governed trial and playbook workflows.

This module deliberately records a human-designed protocol, its evidence, and
the review path that may turn a learning into a standard playbook.  It does not
recommend treatments, infer agronomy, or alter crop allocations and work.
"""

from dataclasses import asdict
from datetime import date, datetime, timezone
import json
import sqlite3
import uuid
from typing import Any, Dict, List, Optional

from ffl.domain.models import Person, Playbook, Trial, TrialAllocation, TrialConclusion, TrialConfounder
from ffl.persistence import repository


_PLAYBOOK_TRANSITIONS = {
    "draft": {"review"},
    "review": {"draft", "published"},
    "published": {"retired"},
    "retired": set(),
}
_TRIAL_TRANSITIONS = {
    "draft": {"active", "stopped"},
    "active": {"paused", "stopped", "completed"},
    "paused": {"active", "stopped"},
    "stopped": set(),
    "completed": set(),
}
_TRIAL_ALLOCATION_TRANSITIONS = {
    "eligible": {"enrolled", "excluded"},
    "enrolled": {"withdrawn"},
    "excluded": set(),
    "withdrawn": set(),
}
_CONCLUSION_TRANSITIONS = {
    "draft": {"review"},
    "review": {"approved", "rejected"},
    "approved": set(),
    "rejected": set(),
}
_REVIEWER_ROLES = {"agronomist", "operations_lead"}
_TRIAL_MANAGER_ROLES = _REVIEWER_ROLES | {"farm_manager"}
_PLAYBOOK_DECISIONS = {"none", "create", "revise", "promote", "retire"}
_CLAIM_TYPES = {"descriptive", "associative", "causal"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _nonempty(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("{0} is required".format(field_name))
    return value.strip()


def _parse_time(value: str, field_name: str) -> str:
    _nonempty(value, field_name)
    try:
        if len(value) == 10:
            date.fromisoformat(value)
        else:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("{0} must be an ISO-8601 date or timestamp".format(field_name)) from error
    return value


def _require_object(value: Any, field_name: str) -> Dict[str, Any]:
    if not isinstance(value, dict) or not value:
        raise ValueError("{0} must be a non-empty object".format(field_name))
    try:
        # Detect non-finite values before the persistence layer does, so API
        # callers get a domain-level explanation instead of an implementation detail.
        json.dumps(value, allow_nan=False)
    except ValueError as error:
        raise ValueError("{0} must contain valid JSON values".format(field_name)) from error
    return value


def _require_list(value: Any, field_name: str) -> List[Any]:
    if not isinstance(value, list) or not value:
        raise ValueError("{0} must be a non-empty list".format(field_name))
    try:
        json.dumps(value, allow_nan=False)
    except ValueError as error:
        raise ValueError("{0} must contain valid JSON values".format(field_name)) from error
    return value


def _person(conn: sqlite3.Connection, person_id: str, field_name: str) -> Person:
    _nonempty(person_id, field_name)
    row = conn.execute("SELECT * FROM people WHERE id = ?", (person_id,)).fetchone()
    if row is None:
        raise ValueError("{0} does not exist".format(field_name))
    return Person(row["id"], row["name"], row["role"], row["created_at"])


def _require_role(person: Person, allowed_roles: set, purpose: str) -> None:
    if person.role not in allowed_roles:
        raise ValueError("{0} must be performed by an agronomist, operations lead, or authorised manager".format(purpose))


def _require_owner_or_manager(conn: sqlite3.Connection, actor_id: str, owner_id: str, purpose: str) -> Person:
    actor = _person(conn, actor_id, "actor_id")
    if actor.id != owner_id and actor.role not in _TRIAL_MANAGER_ROLES:
        raise ValueError("{0} must be performed by the accountable owner or an authorised manager".format(purpose))
    return actor


def _require_owner(conn: sqlite3.Connection, actor_id: str, owner_id: str, purpose: str) -> Person:
    actor = _person(conn, actor_id, "actor_id")
    if actor.id != owner_id:
        raise ValueError("{0} must be performed by the accountable owner".format(purpose))
    return actor


def _audit(conn: sqlite3.Connection, entity_type: str, entity_id: str, from_status: str, to_status: str,
           actor_id: str, reason: str) -> None:
    conn.execute(
        "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), entity_type, entity_id, from_status, to_status, actor_id, reason, _now()),
    )


def _latest_playbook_version(conn: sqlite3.Connection, name: str) -> int:
    row = conn.execute("SELECT MAX(version) AS version FROM playbooks WHERE name = ?", (name,)).fetchone()
    return int(row["version"] or 0)


def _validate_protocol(protocol: Any) -> Dict[str, Any]:
    protocol = _require_object(protocol, "protocol")
    for key in ("summary", "work_instructions", "evidence_requirements"):
        if key not in protocol:
            raise ValueError("protocol must include {0}".format(key))
    _nonempty(protocol["summary"], "protocol.summary")
    _require_list(protocol["work_instructions"], "protocol.work_instructions")
    _require_list(protocol["evidence_requirements"], "protocol.evidence_requirements")
    return protocol


def create_playbook(
    conn: sqlite3.Connection, name: str, version: int, owner_id: str, protocol: Any,
    effective_from: Optional[str] = None,
) -> Playbook:
    """Create a new immutable draft version. Standardisation happens only later."""
    name = _nonempty(name, "name")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise ValueError("version must be a positive integer")
    owner = _person(conn, owner_id, "owner_id")
    _validate_protocol(protocol)
    if effective_from is not None:
        _parse_time(effective_from, "effective_from")
    if version != _latest_playbook_version(conn, name) + 1:
        raise ValueError("playbook version must be the next version for this name")
    # Drafts never carry an approver.  The repository is intentionally simple;
    # this service is the authority for lifecycle guardrails.
    return repository.create_playbook(
        conn, name, version, owner.id, protocol, status="draft", effective_from=effective_from,
    )


def _supporting_conclusion(
    conn: sqlite3.Connection, conclusion_id: Optional[str], playbook_id: str, decision: str
) -> TrialConclusion:
    if not isinstance(conclusion_id, str) or not conclusion_id.strip():
        raise ValueError("supporting conclusion is required")
    conclusion = repository.get_trial_conclusion(conn, conclusion_id or "")
    if conclusion is None:
        raise ValueError("supporting conclusion does not exist")
    if conclusion.status != "approved" or conclusion.approved_at is None:
        raise ValueError("supporting conclusion must be approved")
    if conclusion.playbook_id != playbook_id or conclusion.playbook_decision != decision:
        raise ValueError("supporting conclusion must be linked to this playbook with decision {0}".format(decision))
    return conclusion


def transition_playbook(
    conn: sqlite3.Connection, playbook_id: str, target_status: str, actor_id: str, reason: str,
    effective_from: Optional[str] = None, supporting_conclusion_id: Optional[str] = None,
) -> Playbook:
    playbook = repository.get_playbook(conn, playbook_id)
    if playbook is None or target_status not in _PLAYBOOK_TRANSITIONS.get(playbook.status, set()):
        raise ValueError("invalid playbook transition")
    reason = _nonempty(reason, "reason")
    if target_status in {"review", "draft"}:
        _require_owner(conn, actor_id, playbook.owner_id, "playbook transition")
    elif target_status == "published":
        reviewer = _person(conn, actor_id, "actor_id")
        _require_role(reviewer, _REVIEWER_ROLES, "playbook publication")
        _supporting_conclusion(conn, supporting_conclusion_id, playbook.id, "promote")
        if effective_from is None:
            effective_from = playbook.effective_from
        _parse_time(effective_from or "", "effective_from")
    elif target_status == "retired":
        _require_owner_or_manager(conn, actor_id, playbook.owner_id, "playbook retirement")
        _supporting_conclusion(conn, supporting_conclusion_id, playbook.id, "retire")

    approved_at = _now() if target_status == "published" else playbook.approved_at
    approved_by = actor_id if target_status == "published" else playbook.approved_by_person_id
    with conn:
        conn.execute(
            """UPDATE playbooks
               SET status = ?, effective_from = ?, approved_by_person_id = ?, approved_at = ?
               WHERE id = ?""",
            (target_status, effective_from if target_status == "published" else playbook.effective_from,
             approved_by, approved_at, playbook.id),
        )
        _audit(conn, "playbook", playbook.id, playbook.status, target_status, actor_id, reason)
    return repository.get_playbook(conn, playbook.id)  # type: ignore[return-value]


def _validate_trial_protocol(
    treatment: Any, comparator: Any, eligibility_rule: Any, measurements: Any, guardrails: Any
) -> None:
    _require_object(treatment, "treatment")
    _require_object(comparator, "comparator")
    _require_object(eligibility_rule, "eligibility_rule")
    measurement_items = _require_list(measurements, "measurements")
    guardrail_items = _require_list(guardrails, "guardrails")
    for item in measurement_items:
        if not isinstance(item, dict):
            raise ValueError("measurements entries must be objects")
        for key in ("outcome", "method", "cadence"):
            _nonempty(item.get(key), "measurements.{0}".format(key))
    for item in guardrail_items:
        if not isinstance(item, dict):
            raise ValueError("guardrails entries must be objects")
        for key in ("threshold", "action"):
            _nonempty(item.get(key), "guardrails.{0}".format(key))


def create_trial(
    conn: sqlite3.Connection, name: str, hypothesis: str, owner_id: str, protocol_version: str,
    decision_question: str, treatment: Any, comparator: Any, eligibility_rule: Any,
    measurements: Any, guardrails: Any,
) -> Trial:
    """Create a draft trial with its protocol fixed before any field enrolment."""
    name = _nonempty(name, "name")
    hypothesis = _nonempty(hypothesis, "hypothesis")
    protocol_version = _nonempty(protocol_version, "protocol_version")
    decision_question = _nonempty(decision_question, "decision_question")
    owner = _person(conn, owner_id, "owner_id")
    _validate_trial_protocol(treatment, comparator, eligibility_rule, measurements, guardrails)
    return repository.create_trial(
        conn, name, hypothesis, owner.id, protocol_version, decision_question, treatment, comparator,
        eligibility_rule, measurements, guardrails, status="draft",
    )


def _require_trial_allocation(conn: sqlite3.Connection, trial_id: str, allocation_id: str) -> None:
    if conn.execute("SELECT 1 FROM crop_allocations WHERE id = ?", (allocation_id,)).fetchone() is None:
        raise ValueError("allocation_id does not exist")
    existing = conn.execute(
        "SELECT 1 FROM trial_allocations WHERE trial_id = ? AND allocation_id = ?", (trial_id, allocation_id)
    ).fetchone()
    if existing is not None:
        raise ValueError("allocation is already part of this trial")


def add_trial_allocation(
    conn: sqlite3.Connection, trial_id: str, allocation_id: str, arm: str, actor_id: str,
) -> TrialAllocation:
    trial = repository.get_trial(conn, trial_id)
    if trial is None:
        raise ValueError("trial does not exist")
    if trial.status != "draft":
        raise ValueError("allocations can only be added while a trial is draft")
    _require_owner_or_manager(conn, actor_id, trial.owner_id, "trial allocation")
    if arm not in {"treatment", "comparator"}:
        raise ValueError("arm must be treatment or comparator")
    _require_trial_allocation(conn, trial.id, allocation_id)
    allocation = repository.create_trial_allocation(
        conn, trial.id, allocation_id, arm, status="eligible"
    )
    repository.create_audit_event(conn, "trial_allocation", allocation.id, "none", "eligible", actor_id, "added")
    return allocation


def transition_trial_allocation(
    conn: sqlite3.Connection, trial_id: str, trial_allocation_id: str, target_status: str,
    actor_id: str, reason: str,
) -> TrialAllocation:
    trial = repository.get_trial(conn, trial_id)
    allocation = repository.get_trial_allocation(conn, trial_allocation_id)
    if trial is None or allocation is None or allocation.trial_id != trial_id:
        raise ValueError("trial allocation does not exist")
    if target_status not in _TRIAL_ALLOCATION_TRANSITIONS.get(allocation.status, set()):
        raise ValueError("invalid trial allocation transition")
    if trial.status not in {"draft", "paused"}:
        raise ValueError("trial allocations can only change while the trial is draft or paused")
    _require_owner_or_manager(conn, actor_id, trial.owner_id, "trial allocation transition")
    reason = _nonempty(reason, "reason")
    changed_at = _now()
    withdrawn_at = changed_at if target_status in {"withdrawn", "excluded"} else None
    with conn:
        conn.execute(
            "UPDATE trial_allocations SET status = ?, withdrawn_at = ?, reason = ? WHERE id = ?",
            (target_status, withdrawn_at, reason, allocation.id),
        )
        _audit(conn, "trial_allocation", allocation.id, allocation.status, target_status, actor_id, reason)
    return repository.get_trial_allocation(conn, allocation.id)  # type: ignore[return-value]


def _enrolled_arms(conn: sqlite3.Connection, trial_id: str) -> set:
    rows = conn.execute(
        "SELECT DISTINCT arm FROM trial_allocations WHERE trial_id = ? AND status = 'enrolled'", (trial_id,)
    ).fetchall()
    return {row["arm"] for row in rows}


def transition_trial(
    conn: sqlite3.Connection, trial_id: str, target_status: str, actor_id: str, reason: str,
) -> Trial:
    trial = repository.get_trial(conn, trial_id)
    if trial is None or target_status not in _TRIAL_TRANSITIONS.get(trial.status, set()):
        raise ValueError("invalid trial transition")
    reason = _nonempty(reason, "reason")
    if target_status == "active":
        _require_owner_or_manager(conn, actor_id, trial.owner_id, "trial activation")
        if _enrolled_arms(conn, trial.id) != {"treatment", "comparator"}:
            raise ValueError("trial activation requires enrolled treatment and comparator allocations")
    else:
        _require_owner_or_manager(conn, actor_id, trial.owner_id, "trial transition")
    changed_at = _now()
    starts_on = trial.starts_on or changed_at if target_status == "active" else trial.starts_on
    ends_on = changed_at if target_status in {"stopped", "completed"} else trial.ends_on
    with conn:
        conn.execute(
            "UPDATE trials SET status = ?, starts_on = ?, ends_on = ?, status_reason = ? WHERE id = ?",
            (target_status, starts_on, ends_on, reason, trial.id),
        )
        _audit(conn, "trial", trial.id, trial.status, target_status, actor_id, reason)
    return repository.get_trial(conn, trial.id)  # type: ignore[return-value]


def record_trial_confounder(
    conn: sqlite3.Connection, trial_id: str, category: str, description: str, observed_at: str,
    actor_id: str, allocation_id: Optional[str] = None, evidence_artifact_id: Optional[str] = None,
) -> TrialConfounder:
    trial = repository.get_trial(conn, trial_id)
    if trial is None:
        raise ValueError("trial does not exist")
    if trial.status not in {"active", "paused", "stopped", "completed"}:
        raise ValueError("confounders can only be recorded after a trial starts")
    _require_owner_or_manager(conn, actor_id, trial.owner_id, "trial confounder")
    _nonempty(category, "category")
    _nonempty(description, "description")
    _parse_time(observed_at, "observed_at")
    if evidence_artifact_id is not None and repository.get_evidence_artifact(conn, evidence_artifact_id) is None:
        raise ValueError("evidence_artifact_id does not exist")
    # Repository repeats this membership guard at the durable boundary.
    return repository.create_trial_confounder(
        conn, trial.id, category, description, observed_at, actor_id, allocation_id, evidence_artifact_id
    )


def _validate_limitations(limitations: Any) -> List[Any]:
    items = _require_list(limitations, "limitations")
    for item in items:
        if isinstance(item, str):
            _nonempty(item, "limitations entry")
        elif isinstance(item, dict):
            _nonempty(item.get("statement"), "limitations entry statement")
        else:
            raise ValueError("limitations entries must be strings or objects with a statement")
    return items


def _validate_result(result: Any, trial: Trial, conn: sqlite3.Connection) -> Dict[str, Any]:
    result = _require_object(result, "result")
    _nonempty(result.get("summary"), "result.summary")
    claim_type = result.get("claim_type")
    if claim_type not in _CLAIM_TYPES:
        raise ValueError("result.claim_type must be descriptive, associative, or causal")
    if claim_type == "causal":
        context = result.get("comparison_context")
        if not isinstance(context, dict):
            raise ValueError("causal conclusions require comparison_context")
        _nonempty(context.get("control_strategy"), "comparison_context.control_strategy")
        treatment_ids = context.get("treatment_allocation_ids")
        comparator_ids = context.get("comparator_allocation_ids")
        if not isinstance(treatment_ids, list) or not treatment_ids or not isinstance(comparator_ids, list) or not comparator_ids:
            raise ValueError("causal conclusions require treatment and comparator allocation context")
        enrolled = {
            row["allocation_id"]: row["arm"] for row in conn.execute(
                "SELECT allocation_id, arm FROM trial_allocations WHERE trial_id = ? AND status = 'enrolled'", (trial.id,)
            ).fetchall()
        }
        if not set(treatment_ids).issubset({key for key, arm in enrolled.items() if arm == "treatment"}):
            raise ValueError("causal conclusion treatment context must reference enrolled treatment allocations")
        if not set(comparator_ids).issubset({key for key, arm in enrolled.items() if arm == "comparator"}):
            raise ValueError("causal conclusion comparator context must reference enrolled comparator allocations")
    return result


def create_trial_conclusion(
    conn: sqlite3.Connection, trial_id: str, reviewer_id: str, result: Any, confidence_level: str,
    limitations: Any, evidence_artifact_id: str, playbook_decision: str = "none",
    playbook_id: Optional[str] = None,
) -> TrialConclusion:
    trial = repository.get_trial(conn, trial_id)
    if trial is None:
        raise ValueError("trial does not exist")
    if trial.status not in {"stopped", "completed"}:
        raise ValueError("conclusions require a stopped or completed trial")
    reviewer = _person(conn, reviewer_id, "reviewer_id")
    _require_role(reviewer, _REVIEWER_ROLES, "trial conclusion review")
    if confidence_level not in {"low", "medium", "high"}:
        raise ValueError("confidence_level must be low, medium, or high")
    _validate_result(result, trial, conn)
    _validate_limitations(limitations)
    _nonempty(evidence_artifact_id, "evidence_artifact_id")
    if repository.get_evidence_artifact(conn, evidence_artifact_id) is None:
        raise ValueError("evidence_artifact_id does not exist")
    if playbook_decision not in _PLAYBOOK_DECISIONS:
        raise ValueError("invalid playbook decision")
    if playbook_decision == "promote":
        raise ValueError("playbook promotion decision must be selected when the conclusion is approved")
    if playbook_decision == "none" and playbook_id is not None:
        raise ValueError("playbook_id requires a playbook decision")
    if playbook_decision != "none":
        _nonempty(playbook_id, "playbook_id")
        playbook = repository.get_playbook(conn, playbook_id or "")
        if playbook is None:
            raise ValueError("playbook_id does not exist")
        if playbook_decision == "promote" and playbook.status != "review":
            raise ValueError("promoted playbook must be in review")
        if playbook_decision == "retire" and playbook.status != "published":
            raise ValueError("retired playbook must be published")
    return repository.create_trial_conclusion(
        conn, trial.id, reviewer.id, result, confidence_level, limitations, evidence_artifact_id,
        playbook_decision=playbook_decision, status="draft", playbook_id=playbook_id,
    )


def transition_trial_conclusion(
    conn: sqlite3.Connection, trial_id: str, conclusion_id: str, target_status: str,
    actor_id: str, reason: str, playbook_decision: Optional[str] = None,
    playbook_id: Optional[str] = None,
) -> TrialConclusion:
    trial = repository.get_trial(conn, trial_id)
    conclusion = repository.get_trial_conclusion(conn, conclusion_id)
    if trial is None or conclusion is None or conclusion.trial_id != trial_id:
        raise ValueError("trial conclusion does not exist")
    if target_status not in _CONCLUSION_TRANSITIONS.get(conclusion.status, set()):
        raise ValueError("invalid trial conclusion transition")
    reason = _nonempty(reason, "reason")
    actor = _person(conn, actor_id, "actor_id")
    _require_role(actor, _REVIEWER_ROLES, "trial conclusion transition")
    if target_status in {"review", "approved", "rejected"} and actor.id != conclusion.reviewer_id:
        raise ValueError("trial conclusion transition must be performed by the named reviewer")
    resolved_decision = playbook_decision if playbook_decision is not None else conclusion.playbook_decision
    resolved_playbook_id = playbook_id if playbook_id is not None else conclusion.playbook_id
    if target_status != "approved" and playbook_decision is not None:
        raise ValueError("playbook decision can only change when a conclusion is approved")
    if target_status == "approved":
        if resolved_decision not in _PLAYBOOK_DECISIONS:
            raise ValueError("invalid playbook decision")
        if resolved_decision == "none" and resolved_playbook_id is not None:
            raise ValueError("playbook_id requires a playbook decision")
        if resolved_decision != "none":
            _nonempty(resolved_playbook_id, "playbook_id")
            playbook = repository.get_playbook(conn, resolved_playbook_id or "")
            if playbook is None:
                raise ValueError("playbook_id does not exist")
            if resolved_decision == "promote" and playbook.status != "review":
                raise ValueError("promoted playbook must be in review")
            if resolved_decision == "retire" and playbook.status != "published":
                raise ValueError("retired playbook must be published")
    approved_at = _now() if target_status == "approved" else None
    with conn:
        conn.execute(
            """UPDATE trial_conclusions
               SET status = ?, approved_at = ?, playbook_id = ?, playbook_decision = ? WHERE id = ?""",
            (target_status, approved_at, resolved_playbook_id, resolved_decision, conclusion.id),
        )
        _audit(conn, "trial_conclusion", conclusion.id, conclusion.status, target_status, actor.id, reason)
    return repository.get_trial_conclusion(conn, conclusion.id)  # type: ignore[return-value]


def trial_detail(conn: sqlite3.Connection, trial_id: str) -> Dict[str, Any]:
    """Return the complete, attributed record needed to assess a trial outcome."""
    trial = repository.get_trial(conn, trial_id)
    if trial is None:
        raise LookupError("trial does not exist")
    allocations = repository.list_trial_allocations(conn, trial.id)
    confounders = repository.list_trial_confounders(conn, trial.id)
    conclusions = repository.list_trial_conclusions(conn, trial.id)
    return {
        "trial": asdict(trial),
        "allocations": [asdict(item) for item in allocations],
        "confounders": [asdict(item) for item in confounders],
        "conclusions": [asdict(item) for item in conclusions],
        "audit_events": [asdict(item) for item in repository.list_audit_events(conn, "trial", trial.id)],
        "allocation_audit_events": {
            item.id: [asdict(event) for event in repository.list_audit_events(conn, "trial_allocation", item.id)]
            for item in allocations
        },
        "conclusion_audit_events": {
            item.id: [asdict(event) for event in repository.list_audit_events(conn, "trial_conclusion", item.id)]
            for item in conclusions
        },
    }
