"""Manager-only boundary for registration-level Farm + Grower reviews."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ffl.communications.auth import require_manager
from ffl.persistence import repository
from ffl.services import farm_candidate_reviews


router = APIRouter(prefix="/api/v1/farm-candidates")


class FarmCandidateAcceptanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operating_unit_id: str = Field(min_length=1, max_length=128)
    farm_name: str = Field(min_length=1, max_length=160)
    grower_effective_on: date
    expected_updated_at: str = Field(min_length=1, max_length=64)

    @field_validator("operating_unit_id", "farm_name", "expected_updated_at")
    @classmethod
    def nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value.strip()


class FarmCandidateDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=500)
    expected_updated_at: str = Field(min_length=1, max_length=64)

    @field_validator("reason", "expected_updated_at")
    @classmethod
    def nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value.strip()


def _connection(request: Request):
    return getattr(request.state, "conn", request.app.state.conn)


def _error(error: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


@router.get("/operating-units")
def operating_units(request: Request, _manager_id: str = Depends(require_manager)) -> list[dict]:
    return farm_candidate_reviews.list_operating_units(_connection(request))


@router.post("/refresh")
def refresh(request: Request, _manager_id: str = Depends(require_manager)) -> list[dict]:
    try:
        return farm_candidate_reviews.refresh_cases(_connection(request))
    except ValueError as error:
        raise _error(error)


@router.post("/registrations/{registration_id}/case")
def registration_case(registration_id: str, request: Request,
                      _manager_id: str = Depends(require_manager)) -> dict:
    try:
        cases = farm_candidate_reviews.refresh_cases(
            _connection(request), limit=100, registration_id=registration_id,
        )
    except ValueError as error:
        raise _error(error)
    if not cases:
        raise HTTPException(status_code=404, detail="eligible farm candidate not found")
    return cases[0]


@router.get("/cases")
def cases(
    request: Request,
    case_status: Literal["open", "held", "accepted", "rejected"] = Query(default="open", alias="status"),
    limit: int = Query(default=100, ge=1, le=100),
    _manager_id: str = Depends(require_manager),
) -> list[dict]:
    try:
        return farm_candidate_reviews.list_cases(_connection(request), case_status, limit)
    except ValueError as error:
        raise _error(error)


@router.post("/cases/{case_id}/accept")
def accept(case_id: str, payload: FarmCandidateAcceptanceRequest, request: Request,
           manager_id: str = Depends(require_manager)) -> dict:
    try:
        case = repository.accept_farm_candidate_review_case(
            _connection(request), case_id, manager_id, payload.operating_unit_id,
            payload.farm_name, payload.grower_effective_on.isoformat(), payload.expected_updated_at,
        )
    except repository.FarmTruthConflict as error:
        raise HTTPException(status_code=409, detail=str(error))
    except ValueError as error:
        raise _error(error)
    return {"id": case.id, "status": case.status, "farm_id": case.accepted_farm_id,
            "grower_person_id": case.accepted_grower_person_id}


@router.post("/cases/{case_id}/{decision}")
def decide(case_id: str, decision: Literal["held", "rejected"], payload: FarmCandidateDecisionRequest,
           request: Request, manager_id: str = Depends(require_manager)) -> dict:
    try:
        case = repository.resolve_farm_candidate_review_case(
            _connection(request), case_id, manager_id, decision, payload.reason, payload.expected_updated_at,
        )
    except repository.FarmTruthConflict as error:
        raise HTTPException(status_code=409, detail=str(error))
    except ValueError as error:
        raise _error(error)
    return {"id": case.id, "status": case.status}
