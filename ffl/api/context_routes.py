"""API boundary for farm context foundations and the deterministic daily brief."""

from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from ffl.persistence import repository
from ffl.communications.auth import require_manager
from ffl.pilot_setup_auth import require_pilot_setup_approval
from ffl.services import morning_brief, operating_export, pilot_readiness, pilot_setup


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


class PilotSetupProposalRequest(BaseModel):
    farm_name: str
    people: List[Dict[str, Any]]
    parcels: List[Dict[str, Any]]
    blocks: List[Dict[str, Any]]
    season: Dict[str, Any]
    allocations: List[Dict[str, Any]]
    location: Dict[str, Any]
    first_work: Dict[str, Any]


class QuickPilotSetupRequest(BaseModel):
    farm_name: str
    field_name: str
    area_hectares: float
    crop_name: str
    manager_name: str
    state_name: str = "Uttar Pradesh"
    district_name: str
    village_name: Optional[str] = None
    pincode: Optional[str] = None


class PilotSetupAcceptanceRequest(PilotSetupProposalRequest):
    """A proposed first farm plus the durable replay key and named approver."""

    idempotency_key: str = Field(min_length=8, max_length=128)
    approving_manager_reference: str = Field(min_length=1, max_length=80)


def _connection(request: Request):
    return getattr(request.state, "conn", request.app.state.conn)


def _unprocessable(error: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


@router.get("/pilot/readiness")
def get_pilot_readiness(request: Request) -> dict:
    """Show the real pilot's setup gap without creating sample farm records."""
    return pilot_readiness.pilot_readiness(_connection(request))


@router.post("/pilot/setup/validate")
def validate_pilot_setup(payload: PilotSetupProposalRequest) -> dict:
    """Rehearse an UP pilot pack; a separate human acceptance will persist it."""
    try:
        values = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
        return pilot_setup.validate_up_pilot_setup(values)
    except ValueError as error:
        raise _unprocessable(error)


@router.post("/pilot/quick-start/validate")
def validate_quick_pilot_start(payload: QuickPilotSetupRequest) -> dict:
    try:
        values = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
        return pilot_setup.validate_quick_start(values)
    except ValueError as error:
        raise _unprocessable(error)


@router.post("/pilot/setup/accept", status_code=status.HTTP_201_CREATED)
def accept_pilot_setup(
    payload: PilotSetupAcceptanceRequest,
    request: Request,
    response: Response,
    _approval: str = Depends(require_pilot_setup_approval),
) -> dict:
    """Create the first real UP farm exactly once after independent approval.

    This route remains behind the launch session.  The additional server-side
    approval header exists only to bootstrap the first durable manager record;
    later manager operations use the normal named-manager boundary instead.
    """

    try:
        values = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
        result = pilot_setup.accept_up_pilot_setup(
            _connection(request),
            values,
            idempotency_key=values.pop("idempotency_key"),
            approving_manager_reference=values.pop("approving_manager_reference"),
        )
        if result["idempotent"]:
            response.status_code = status.HTTP_200_OK
        return result
    except ValueError as error:
        raise _unprocessable(error)


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


@router.get("/operating-units/{operating_unit_id}/operating-ledger.csv")
def export_operating_ledger(
    operating_unit_id: str, request: Request, _manager_id: str = Depends(require_manager),
) -> Response:
    """Download canonical operating records, never the communications archive."""
    try:
        output = operating_export.operating_ledger_csv(_connection(request), operating_unit_id)
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    return Response(
        content=output,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="agro-ceo-operating-ledger.csv"'},
    )
