"""Manager-only boundary for bounded field fact and proof requests.

The API records reviewed intent only.  It cannot send a message, accept a
reply as farm truth, or close the linked work item.  A future communications
adapter remains responsible for its own endpoint, consent, template, and
WhatsApp-capability checks before it can dispatch a request that has been
made ready here.
"""

from dataclasses import asdict
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from ffl.communications.auth import require_manager
from ffl.persistence import repository
from ffl.services import field_information_requests
from ffl.services.allocation_relationship_coverage import active_person_allocation_coverage


router = APIRouter(prefix="/api/v1")

RequestKind = Literal[
    "field_check",
    "evidence_photo",
    "irrigation_status",
    "input_application",
    "pest_or_deviation",
    "harvest_update",
]


class FieldInformationRequestCreateRequest(BaseModel):
    """The reviewed, bilingual words of a single future field request."""

    model_config = ConfigDict(extra="forbid")

    allocation_id: str = Field(min_length=1, max_length=128)
    target_person_id: str = Field(min_length=1, max_length=128)
    request_kind: RequestKind
    evidence_required: bool
    due_at: str = Field(min_length=1, max_length=64)
    request_copy_en: str = Field(min_length=1, max_length=1600)
    request_copy_hi: str = Field(min_length=1, max_length=1600)
    idempotency_key: str = Field(min_length=8, max_length=128)
    work_item_id: Optional[str] = Field(default=None, min_length=1, max_length=128)


class FieldInformationRequestCancellation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=500)


def _connection(request: Request):
    return getattr(request.state, "conn", request.app.state.conn)


def _unprocessable(error: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


def _request_or_404(conn, request_id: str):
    result = repository.get_field_information_request(conn, request_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="field information request not found")
    return result


def _require_target_coverage(conn, target_person_id: str, allocation_id: str) -> None:
    """Require a present, explicit allocation relationship before requesting.

    A village, contact record, procurement history, or generic job title is
    never enough.  This gives the future delivery adapter a bounded recipient
    to verify instead of a broad people directory to guess from.
    """

    coverage = active_person_allocation_coverage(conn, target_person_id, allocation_id)
    if not coverage.eligible:
        raise ValueError("target person lacks an active explicit relationship to the crop allocation")


def _summary(item) -> dict:
    """Return durable request intent, not any communications archive or reply."""

    return asdict(item)


@router.post("/field-information-requests", status_code=status.HTTP_201_CREATED)
def create_field_information_request(
    payload: FieldInformationRequestCreateRequest,
    request: Request,
    manager_id: str = Depends(require_manager),
) -> dict:
    """Create/replay one manager-reviewed field request; it is initially a draft."""

    try:
        values = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
        conn = _connection(request)
        _require_target_coverage(conn, values["target_person_id"], values["allocation_id"])
        item = field_information_requests.create_information_request(
            conn, initiated_by_person_id=manager_id, **values
        )
        return _summary(item)
    except ValueError as error:
        raise _unprocessable(error)


@router.get("/field-information-requests")
def list_field_information_requests(
    request: Request,
    allocation_id: Optional[str] = None,
    target_person_id: Optional[str] = None,
    request_status: Optional[Literal["draft", "ready", "dispatched", "responded", "expired", "cancelled"]] = None,
    _manager_id: str = Depends(require_manager),
) -> list[dict]:
    """List reviewed requests for one manager; this is not a conversation archive."""

    try:
        return [
            _summary(item)
            for item in repository.list_field_information_requests(
                _connection(request), allocation_id=allocation_id,
                target_person_id=target_person_id, status=request_status,
            )
        ]
    except ValueError as error:
        raise _unprocessable(error)


@router.get("/field-information-requests/{request_id}")
def get_field_information_request(
    request_id: str,
    request: Request,
    _manager_id: str = Depends(require_manager),
) -> dict:
    """Inspect a request and its append-only lifecycle, never raw replies."""

    conn = _connection(request)
    item = _request_or_404(conn, request_id)
    return {
        "request": _summary(item),
        "events": [asdict(event) for event in repository.list_field_information_request_events(conn, item.id)],
    }


@router.post("/field-information-requests/{request_id}/ready")
def ready_field_information_request(
    request_id: str,
    request: Request,
    manager_id: str = Depends(require_manager),
) -> dict:
    """Review intent for a future dispatch adapter; this does not send it."""

    try:
        conn = _connection(request)
        item = _request_or_404(conn, request_id)
        _require_target_coverage(conn, item.target_person_id, item.allocation_id)
        return _summary(field_information_requests.ready_information_request(
            conn, request_id, actor_person_id=manager_id
        ))
    except ValueError as error:
        raise _unprocessable(error)


@router.post("/field-information-requests/{request_id}/cancel")
def cancel_field_information_request(
    request_id: str,
    payload: FieldInformationRequestCancellation,
    request: Request,
    manager_id: str = Depends(require_manager),
) -> dict:
    """Cancel a request without deleting its reviewed intent or lifecycle."""

    try:
        _request_or_404(_connection(request), request_id)
        return _summary(field_information_requests.cancel_information_request(
            _connection(request), request_id, actor_person_id=manager_id, reason=payload.reason
        ))
    except ValueError as error:
        raise _unprocessable(error)
