"""HTTP boundary for season execution and learning records."""

from dataclasses import asdict
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from ffl.services import season


router = APIRouter(prefix="/api/v1")


class FieldSignalRequest(BaseModel):
    template_id: str
    template_version: int
    observed_at: str
    actor_id: str
    values: Dict[str, Any]
    evidence_artifact_id: Optional[str] = None
    status: str = "submitted"


class HarvestRecordRequest(BaseModel):
    harvest_starts_on: str
    quantity: float
    canonical_unit: str
    measurement_method: str
    quality_metrics: Any = Field(default_factory=dict)
    harvest_ends_on: Optional[str] = None
    evidence_artifact_id: Optional[str] = None
    status: Optional[str] = None
    correction_of_id: Optional[str] = None
    corrected_by_person_id: Optional[str] = None
    correction_reason: Optional[str] = None


class SeasonReviewRequest(BaseModel):
    owner_id: str
    confirmed_practices: List[Dict[str, Any]]
    invalidated_assumptions: List[Dict[str, Any]]
    unresolved_questions: List[Dict[str, Any]]
    proposed_playbook_changes: List[Dict[str, Any]]
    status: str = "draft"
    reviewed_at: Optional[str] = None


def _connection(request: Request):
    return request.app.state.conn


def _unprocessable(error: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


@router.get("/allocations/{allocation_id}/calendar")
def get_allocation_calendar(allocation_id: str, request: Request) -> dict:
    try:
        return season.allocation_calendar(_connection(request), allocation_id)
    except ValueError as error:
        raise _unprocessable(error)


@router.post("/allocations/{allocation_id}/signals", status_code=status.HTTP_201_CREATED)
def create_field_signal(allocation_id: str, payload: FieldSignalRequest, request: Request) -> dict:
    try:
        signal = season.record_field_signal(
            _connection(request), allocation_id, payload.template_id, payload.template_version,
            payload.observed_at, payload.actor_id, payload.values, payload.evidence_artifact_id, payload.status,
        )
    except ValueError as error:
        raise _unprocessable(error)
    return asdict(signal)


@router.post("/allocations/{allocation_id}/harvest-records", status_code=status.HTTP_201_CREATED)
def create_harvest_record(allocation_id: str, payload: HarvestRecordRequest, request: Request) -> dict:
    try:
        harvest = season.record_harvest(
            _connection(request), allocation_id, payload.harvest_starts_on, payload.quantity,
            payload.canonical_unit, payload.measurement_method, payload.quality_metrics,
            payload.harvest_ends_on, payload.evidence_artifact_id, payload.status,
            payload.correction_of_id, payload.corrected_by_person_id, payload.correction_reason,
        )
    except ValueError as error:
        raise _unprocessable(error)
    return asdict(harvest)


@router.post("/allocations/{allocation_id}/season-reviews", status_code=status.HTTP_201_CREATED)
def create_season_review(allocation_id: str, payload: SeasonReviewRequest, request: Request) -> dict:
    try:
        review = season.record_season_review(
            _connection(request), allocation_id, payload.owner_id, payload.confirmed_practices,
            payload.invalidated_assumptions, payload.unresolved_questions, payload.proposed_playbook_changes,
            payload.status, payload.reviewed_at,
        )
    except ValueError as error:
        raise _unprocessable(error)
    return asdict(review)
