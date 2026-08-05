"""Manager-only HTTP boundary for reviewed Farm Truth decisions."""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ffl.communications.auth import require_manager
from ffl.persistence import repository
from ffl.services import farm_truth


router = APIRouter(prefix="/api/v1/farm-truth")


class FarmTruthContextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operating_unit_id: str = Field(min_length=1, max_length=128)
    season_id: str = Field(min_length=1, max_length=128)

    @field_validator("operating_unit_id", "season_id")
    @classmethod
    def nonempty_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("identifier must not be blank")
        return value.strip()


class FarmTruthAcceptanceRequest(FarmTruthContextRequest):
    field_name: str = Field(min_length=1, max_length=160)
    managed_area_hectares: float = Field(gt=0, allow_inf_nan=False)
    crop_name: str = Field(min_length=1, max_length=160)
    cultivar: Optional[str] = Field(default=None, max_length=160)
    grower_effective_on: date
    right_type: str = Field(min_length=1, max_length=160)
    right_starts_on: date
    right_ends_on: Optional[date] = None
    field_worker_party_id: Optional[str] = Field(default=None, min_length=1, max_length=128)

    @field_validator("field_name", "crop_name", "right_type")
    @classmethod
    def nonempty_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value.strip()

    @field_validator("cultivar", "field_worker_party_id")
    @classmethod
    def normalize_optional_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def coherent_right_dates(self):
        if self.right_ends_on is not None and self.right_ends_on < self.right_starts_on:
            raise ValueError("right_ends_on must be on or after right_starts_on")
        return self


class FarmTruthNeedsEvidenceRequest(FarmTruthContextRequest):
    missing_evidence_kind: Literal[
        "plot_area",
        "crop_season",
        "right_to_operate",
        "farmer_identity",
        "field_worker_assignment",
    ]
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def nonempty_reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason must not be blank")
        return value.strip()


class FarmTruthRejectRequest(FarmTruthContextRequest):
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def nonempty_reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason must not be blank")
        return value.strip()


def _connection(request: Request):
    return getattr(request.state, "conn", request.app.state.conn)


def _unprocessable(error: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


def _conflict(detail: str = "farm truth review case is stale, claimed, or resolved") -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _case_for_decision(conn, case_id: str, operating_unit_id: str, season_id: str):
    case = repository.get_farm_truth_case(conn, case_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="farm truth review case not found")
    if case.status != "open":
        raise _conflict()
    try:
        current = farm_truth.get_farm_truth_case_detail(
            conn, case_id, operating_unit_id, season_id
        )
    except ValueError as error:
        raise _unprocessable(error)
    if current is None:
        raise _conflict()
    return case


def _acceptance_result(case: repository.FarmTruthReviewCase) -> dict:
    return {
        "id": case.id,
        "status": case.status,
        "land_parcel_id": case.accepted_land_parcel_id,
        "operational_block_id": case.accepted_operational_block_id,
        "crop_allocation_id": case.accepted_crop_allocation_id,
        "grower_person_id": case.accepted_grower_person_id,
        "field_worker_person_id": case.accepted_field_worker_person_id,
    }


def _validate_acceptance_dates(conn, payload: FarmTruthAcceptanceRequest) -> None:
    unit = repository.get_operating_unit(conn, payload.operating_unit_id)
    season = repository.get_season(conn, payload.season_id)
    if unit is None:
        raise ValueError("operating unit does not exist")
    if season is None or season.operating_unit_id != unit.id:
        raise ValueError("season does not belong to operating unit")
    starts_on = date.fromisoformat(season.starts_on)
    ends_on = date.fromisoformat(season.ends_on)
    if not starts_on <= date.today() <= ends_on:
        raise ValueError("selected season is not current")
    if not starts_on <= payload.grower_effective_on <= ends_on:
        raise ValueError("grower_effective_on must fall within the selected season")
    effective_right_end = payload.right_ends_on or ends_on
    if effective_right_end < payload.right_starts_on:
        raise ValueError("right_ends_on must be on or after right_starts_on")
    if not payload.right_starts_on <= payload.grower_effective_on <= effective_right_end:
        raise ValueError("grower_effective_on must fall within the right-to-operate interval")
    if payload.right_starts_on > starts_on or effective_right_end < ends_on:
        raise ValueError("right-to-operate interval must cover the selected season")


@router.post("/refresh")
def refresh_farm_truth_queue(
    payload: FarmTruthContextRequest,
    request: Request,
    manager_id: str = Depends(require_manager),
) -> list[dict]:
    try:
        return farm_truth.refresh_farm_truth_cases(
            _connection(request), payload.operating_unit_id, payload.season_id, manager_id
        )
    except ValueError as error:
        raise _unprocessable(error)


@router.get("/contexts")
def list_farm_truth_contexts(
    request: Request,
    _manager_id: str = Depends(require_manager),
) -> list[dict]:
    return farm_truth.list_current_farm_truth_contexts(_connection(request))


@router.get("/inbox")
def list_farm_truth_inbox(
    request: Request,
    limit: int = Query(default=50, ge=1, le=50),
    manager_id: str = Depends(require_manager),
) -> list[dict]:
    try:
        return farm_truth.list_farm_truth_inbox_items(
            _connection(request), manager_id, limit=limit
        )
    except ValueError as error:
        raise _unprocessable(error)


@router.get("/cases")
def list_farm_truth_cases(
    request: Request,
    operating_unit_id: str = Query(min_length=1, max_length=128),
    season_id: str = Query(min_length=1, max_length=128),
    case_status: Literal["open", "accepting", "needs_evidence", "accepted", "rejected"] = Query(
        default="open", alias="status"
    ),
    limit: int = Query(default=50, ge=1, le=50),
    manager_id: str = Depends(require_manager),
) -> list[dict]:
    try:
        return farm_truth.list_farm_truth_case_summaries(
            _connection(request),
            operating_unit_id,
            season_id,
            status=case_status,
            limit=limit,
            owner_person_id=manager_id if case_status == "needs_evidence" else None,
        )
    except ValueError as error:
        raise _unprocessable(error)


@router.get("/cases/{case_id}")
def get_farm_truth_case(
    case_id: str,
    request: Request,
    operating_unit_id: str = Query(min_length=1, max_length=128),
    season_id: str = Query(min_length=1, max_length=128),
    _manager_id: str = Depends(require_manager),
) -> dict:
    try:
        detail = farm_truth.get_farm_truth_case_detail(
            _connection(request), case_id, operating_unit_id, season_id
        )
    except ValueError as error:
        raise _unprocessable(error)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="farm truth review case not found")
    return detail


@router.post("/cases/{case_id}/accept")
def accept_farm_truth_case(
    case_id: str,
    payload: FarmTruthAcceptanceRequest,
    request: Request,
    manager_id: str = Depends(require_manager),
) -> dict:
    conn = _connection(request)
    established = repository.get_farm_truth_case(conn, case_id)
    if established is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="farm truth review case not found")
    expected_updated_at = None
    if established.status != "accepted":
        try:
            _validate_acceptance_dates(conn, payload)
        except ValueError as error:
            raise _unprocessable(error)
        expected = _case_for_decision(
            conn, case_id, payload.operating_unit_id, payload.season_id
        )
        expected_updated_at = expected.updated_at
    try:
        accepted = repository.accept_farm_truth_case(
            conn,
            case_id=case_id,
            reviewer_id=manager_id,
            operating_unit_id=payload.operating_unit_id,
            season_id=payload.season_id,
            field_name=payload.field_name,
            managed_area_hectares=payload.managed_area_hectares,
            crop_name=payload.crop_name,
            cultivar=payload.cultivar,
            grower_effective_on=payload.grower_effective_on.isoformat(),
            right_type=payload.right_type,
            right_starts_on=payload.right_starts_on.isoformat(),
            right_ends_on=payload.right_ends_on.isoformat() if payload.right_ends_on else None,
            field_worker_party_id=payload.field_worker_party_id,
            expected_case_updated_at=expected_updated_at,
        )
    except repository.FarmTruthConflict as error:
        raise _conflict(str(error))
    except sqlite3.IntegrityError as error:
        message = str(error)
        if (
            "trackwick_plot_operating_links.plot_id" in message
            or "agro_idx_trackwick_plot_links_one_reviewed" in message
        ):
            raise _conflict("source plot was accepted by another review")
        raise
    except ValueError as error:
        raise _unprocessable(error)
    return _acceptance_result(accepted)


@router.post("/cases/{case_id}/needs-evidence")
def mark_farm_truth_case_needs_evidence(
    case_id: str,
    payload: FarmTruthNeedsEvidenceRequest,
    request: Request,
    manager_id: str = Depends(require_manager),
) -> dict:
    conn = _connection(request)
    expected = _case_for_decision(
        conn, case_id, payload.operating_unit_id, payload.season_id
    )
    try:
        case = repository.mark_farm_truth_case_needs_evidence(
            conn,
            case_id,
            manager_id,
            payload.missing_evidence_kind,
            payload.reason,
            expected_case_updated_at=expected.updated_at,
        )
    except ValueError as error:
        raise _conflict(str(error))
    return {
        "id": case.id,
        "status": case.status,
        "missing_evidence_kind": case.missing_evidence_kind,
    }


@router.post("/cases/{case_id}/reject")
def reject_farm_truth_case(
    case_id: str,
    payload: FarmTruthRejectRequest,
    request: Request,
    manager_id: str = Depends(require_manager),
) -> dict:
    conn = _connection(request)
    expected = _case_for_decision(
        conn, case_id, payload.operating_unit_id, payload.season_id
    )
    try:
        case = repository.mark_farm_truth_case_rejected(
            conn,
            case_id,
            manager_id,
            payload.reason,
            expected_case_updated_at=expected.updated_at,
        )
    except ValueError as error:
        raise _conflict(str(error))
    return {"id": case.id, "status": case.status}
