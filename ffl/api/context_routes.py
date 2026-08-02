"""API boundary for farm context foundations and the deterministic daily brief."""

from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from ffl.persistence import repository
from ffl.services import morning_brief


router = APIRouter(prefix="/api/v1")


class OperatingUnitLocationRequest(BaseModel):
    state_name: str
    district_name: str
    district_context_key: str
    verified_by_person_id: str
    verified_at: str
    verification_method: str = "field_verified"
    subdistrict_name: Optional[str] = None
    village_name: Optional[str] = None
    pincode: Optional[str] = None


class SoilBaselineRequest(BaseModel):
    sampled_on: str
    lab_name: str
    measurements: Dict[str, Dict[str, Any]]
    evidence_artifact_id: str
    reviewed_by_person_id: str
    depth_cm_start: Optional[float] = None
    depth_cm_end: Optional[float] = None


def _connection(request: Request):
    return getattr(request.state, "conn", request.app.state.conn)


def _unprocessable(error: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


@router.put("/operating-units/{operating_unit_id}/location", status_code=status.HTTP_201_CREATED)
def set_operating_unit_location(
    operating_unit_id: str, payload: OperatingUnitLocationRequest, request: Request
) -> dict:
    try:
        values = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
        return asdict(repository.create_operating_unit_location(_connection(request), operating_unit_id, **values))
    except ValueError as error:
        raise _unprocessable(error)


@router.get("/operating-units/{operating_unit_id}/location")
def get_operating_unit_location(operating_unit_id: str, request: Request) -> dict:
    location = repository.get_active_operating_unit_location(_connection(request), operating_unit_id)
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="active operating-unit location not found")
    return asdict(location)


@router.post("/operating-units/{operating_unit_id}/soil-baselines", status_code=status.HTTP_201_CREATED)
def create_soil_baseline(operating_unit_id: str, payload: SoilBaselineRequest, request: Request) -> dict:
    try:
        values = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
        return asdict(repository.create_soil_baseline(_connection(request), operating_unit_id, **values))
    except ValueError as error:
        raise _unprocessable(error)


@router.get("/operating-units/{operating_unit_id}/soil-baselines")
def get_soil_baselines(operating_unit_id: str, request: Request) -> List[dict]:
    return [asdict(item) for item in repository.list_soil_baselines(_connection(request), operating_unit_id)]


@router.get("/operating-units/{operating_unit_id}/morning-brief")
def get_morning_brief(operating_unit_id: str, request: Request, as_of: Optional[str] = None) -> dict:
    try:
        parsed = None if as_of is None else datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="as_of must be ISO-8601")
    try:
        return morning_brief.morning_brief(_connection(request), operating_unit_id, parsed)
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
