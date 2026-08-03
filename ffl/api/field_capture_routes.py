"""Fail-closed browser boundary for native field observation capture."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from ffl.communications.auth import require_manager
from ffl.persistence import repository
from ffl.services import field_capture


router = APIRouter(prefix="/api/v1")


class FieldCapturePassRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_information_request_id: str = Field(min_length=1, max_length=128)
    signal_template_id: str = Field(min_length=1, max_length=128)
    signal_template_version: int = Field(ge=1)
    expires_at: str = Field(min_length=1, max_length=64)


class FieldCaptureEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_base64: str = Field(min_length=1, max_length=4_194_304)
    media_type: str = Field(min_length=1, max_length=100)
    filename: Optional[str] = Field(default=None, max_length=180)


class FieldCaptureSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(min_length=8, max_length=128)
    observed_at: str = Field(min_length=1, max_length=64)
    values: dict[str, Any]
    evidence: Optional[FieldCaptureEvidence] = None


def _connection(request: Request):
    return getattr(request.state, "conn", request.app.state.conn)


def _unprocessable(error: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


def _field_token(request: Request) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="field capture authorization is required")
    return token.strip()


@router.post("/field-capture/passes", status_code=status.HTTP_201_CREATED)
def issue_field_capture_pass(
    payload: FieldCapturePassRequest,
    request: Request,
    manager_id: str = Depends(require_manager),
) -> dict:
    """Return an opaque one-time field link capability to an authenticated manager."""
    try:
        values = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
        capture_pass, token = field_capture.issue_capture_pass(
            _connection(request), request.app.state.field_capture_signing_key,
            issued_by_person_id=manager_id, **values,
        )
    except field_capture.FieldCaptureUnavailable as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error))
    except ValueError as error:
        raise _unprocessable(error)
    # This is deliberately the only response that includes the bearer token.
    return {
        "access_token": token,
        "expires_at": capture_pass.expires_at,
        "field_information_request_id": capture_pass.field_information_request_id,
    }


@router.get("/field-capture/context")
def get_field_capture_context(request: Request) -> dict:
    """Read the current pass's bounded crop/request/template context."""
    token = _field_token(request)
    try:
        return field_capture.capture_context(
            _connection(request), request.app.state.field_capture_signing_key, token
        )
    except field_capture.FieldCaptureUnavailable:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="field capture authorization is invalid")
    except ValueError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="field capture authorization is invalid")


@router.post("/field-capture/submissions", status_code=status.HTTP_201_CREATED)
def submit_field_capture_candidate(
    payload: FieldCaptureSubmission, request: Request, response: Response,
) -> dict:
    """Create/replay one review candidate.  It does not write farm truth."""
    token = _field_token(request)
    try:
        values = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
        candidate, created = field_capture.submit_capture_candidate(
            _connection(request), request.app.state.field_capture_signing_key, token,
            values["idempotency_key"], values["observed_at"], values["values"], values.get("evidence"),
            request.app.state.evidence_store,
        )
    except field_capture.FieldCaptureUnavailable:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="field capture authorization is invalid")
    except ValueError as error:
        raise _unprocessable(error)
    if not created:
        response.status_code = status.HTTP_200_OK
    artifact = repository.get_evidence_artifact(
        _connection(request), candidate.evidence_artifact_id
    ) if candidate.evidence_artifact_id else None
    return field_capture.field_candidate_field_summary(candidate, artifact)


@router.get("/field-capture/candidates/{candidate_id}")
def get_field_capture_candidate(
    candidate_id: str,
    request: Request,
    _manager_id: str = Depends(require_manager),
) -> dict:
    try:
        return field_capture.field_candidate_manager_detail(_connection(request), candidate_id)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))


@router.post("/field-capture/candidates/{candidate_id}/accept")
def accept_field_capture_candidate(
    candidate_id: str,
    request: Request,
    manager_id: str = Depends(require_manager),
) -> dict:
    try:
        return {"id": field_capture.accept_capture_candidate(_connection(request), candidate_id, manager_id).id,
                "status": "accepted"}
    except ValueError as error:
        raise _unprocessable(error)


@router.post("/field-capture/candidates/{candidate_id}/reject")
def reject_field_capture_candidate(
    candidate_id: str,
    request: Request,
    manager_id: str = Depends(require_manager),
) -> dict:
    try:
        return {"id": field_capture.reject_capture_candidate(_connection(request), candidate_id, manager_id).id,
                "status": "rejected"}
    except ValueError as error:
        raise _unprocessable(error)
