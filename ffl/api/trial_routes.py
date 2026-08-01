"""HTTP boundary for governed FFL trials and playbooks."""

from dataclasses import asdict
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from ffl.persistence import repository
from ffl.services import trials


router = APIRouter(prefix="/api/v1")


class PlaybookCreateRequest(BaseModel):
    name: str
    version: int
    owner_id: str
    protocol: Dict[str, Any]
    effective_from: Optional[str] = None


class PlaybookTransitionRequest(BaseModel):
    status: str
    actor_id: str
    reason: str
    effective_from: Optional[str] = None
    supporting_conclusion_id: Optional[str] = None


class TrialCreateRequest(BaseModel):
    name: str
    hypothesis: str
    owner_id: str
    protocol_version: str
    decision_question: str
    treatment: Dict[str, Any]
    comparator: Dict[str, Any]
    eligibility_rule: Dict[str, Any]
    measurements: List[Dict[str, Any]]
    guardrails: List[Dict[str, Any]]


class TrialTransitionRequest(BaseModel):
    status: str
    actor_id: str
    reason: str


class TrialAllocationCreateRequest(BaseModel):
    allocation_id: str
    arm: str
    actor_id: str


class TrialAllocationTransitionRequest(BaseModel):
    status: str
    actor_id: str
    reason: str


class TrialConfounderRequest(BaseModel):
    category: str
    description: str
    observed_at: str
    actor_id: str
    allocation_id: Optional[str] = None
    evidence_artifact_id: Optional[str] = None


class TrialConclusionRequest(BaseModel):
    reviewer_id: str
    result: Dict[str, Any]
    confidence_level: str
    limitations: List[Any]
    evidence_artifact_id: str
    playbook_decision: str = "none"
    playbook_id: Optional[str] = None


class TrialConclusionTransitionRequest(BaseModel):
    status: str
    actor_id: str
    reason: str
    playbook_decision: Optional[str] = None
    playbook_id: Optional[str] = None


def _connection(request: Request):
    return request.app.state.conn


def _unprocessable(error: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


@router.post("/playbooks", status_code=status.HTTP_201_CREATED)
def create_playbook(payload: PlaybookCreateRequest, request: Request) -> dict:
    try:
        return asdict(trials.create_playbook(
            _connection(request), payload.name, payload.version, payload.owner_id, payload.protocol,
            payload.effective_from,
        ))
    except ValueError as error:
        raise _unprocessable(error)


@router.get("/playbooks/{playbook_id}")
def get_playbook(playbook_id: str, request: Request) -> dict:
    playbook = repository.get_playbook(_connection(request), playbook_id)
    if playbook is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="playbook not found")
    return {
        **asdict(playbook),
        "audit_events": [asdict(event) for event in repository.list_audit_events(
            _connection(request), "playbook", playbook.id
        )],
    }


@router.post("/playbooks/{playbook_id}/transitions")
def transition_playbook(playbook_id: str, payload: PlaybookTransitionRequest, request: Request) -> dict:
    try:
        return asdict(trials.transition_playbook(
            _connection(request), playbook_id, payload.status, payload.actor_id, payload.reason,
            payload.effective_from, payload.supporting_conclusion_id,
        ))
    except ValueError as error:
        raise _unprocessable(error)


@router.post("/trials", status_code=status.HTTP_201_CREATED)
def create_trial(payload: TrialCreateRequest, request: Request) -> dict:
    try:
        return asdict(trials.create_trial(
            _connection(request), payload.name, payload.hypothesis, payload.owner_id,
            payload.protocol_version, payload.decision_question, payload.treatment, payload.comparator,
            payload.eligibility_rule, payload.measurements, payload.guardrails,
        ))
    except ValueError as error:
        raise _unprocessable(error)


@router.get("/trials/{trial_id}")
def get_trial(trial_id: str, request: Request) -> dict:
    try:
        return trials.trial_detail(_connection(request), trial_id)
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="trial not found")


@router.post("/trials/{trial_id}/transitions")
def transition_trial(trial_id: str, payload: TrialTransitionRequest, request: Request) -> dict:
    try:
        return asdict(trials.transition_trial(
            _connection(request), trial_id, payload.status, payload.actor_id, payload.reason,
        ))
    except ValueError as error:
        raise _unprocessable(error)


@router.post("/trials/{trial_id}/allocations", status_code=status.HTTP_201_CREATED)
def add_trial_allocation(trial_id: str, payload: TrialAllocationCreateRequest, request: Request) -> dict:
    try:
        return asdict(trials.add_trial_allocation(
            _connection(request), trial_id, payload.allocation_id, payload.arm, payload.actor_id,
        ))
    except ValueError as error:
        raise _unprocessable(error)


@router.post("/trials/{trial_id}/allocations/{trial_allocation_id}/transitions")
def transition_trial_allocation(
    trial_id: str, trial_allocation_id: str, payload: TrialAllocationTransitionRequest, request: Request,
) -> dict:
    try:
        return asdict(trials.transition_trial_allocation(
            _connection(request), trial_id, trial_allocation_id, payload.status, payload.actor_id, payload.reason,
        ))
    except ValueError as error:
        raise _unprocessable(error)


@router.post("/trials/{trial_id}/confounders", status_code=status.HTTP_201_CREATED)
def create_trial_confounder(trial_id: str, payload: TrialConfounderRequest, request: Request) -> dict:
    try:
        return asdict(trials.record_trial_confounder(
            _connection(request), trial_id, payload.category, payload.description, payload.observed_at,
            payload.actor_id, payload.allocation_id, payload.evidence_artifact_id,
        ))
    except ValueError as error:
        raise _unprocessable(error)


@router.post("/trials/{trial_id}/conclusions", status_code=status.HTTP_201_CREATED)
def create_trial_conclusion(trial_id: str, payload: TrialConclusionRequest, request: Request) -> dict:
    try:
        return asdict(trials.create_trial_conclusion(
            _connection(request), trial_id, payload.reviewer_id, payload.result, payload.confidence_level,
            payload.limitations, payload.evidence_artifact_id, payload.playbook_decision, payload.playbook_id,
        ))
    except ValueError as error:
        raise _unprocessable(error)


@router.post("/trials/{trial_id}/conclusions/{conclusion_id}/transitions")
def transition_trial_conclusion(
    trial_id: str, conclusion_id: str, payload: TrialConclusionTransitionRequest, request: Request,
) -> dict:
    try:
        return asdict(trials.transition_trial_conclusion(
            _connection(request), trial_id, conclusion_id, payload.status, payload.actor_id, payload.reason,
            payload.playbook_decision, payload.playbook_id,
        ))
    except ValueError as error:
        raise _unprocessable(error)
