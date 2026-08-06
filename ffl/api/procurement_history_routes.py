"""Manager-only, privacy-minimising procurement history intake."""

import base64
from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from ffl.communications.auth import require_manager
from ffl.services import procurement_capture, procurement_history
from ffl.services.evidence_store import EvidenceStoreError


router = APIRouter(prefix="/api/v1")


class ProcurementHistoryCreateRequest(BaseModel):
    content_base64: str
    original_filename: Optional[str] = None


class ProcurementCaptureCreateRequest(BaseModel):
    content_base64: str
    original_filename: Optional[str] = None


def _connection(request: Request):
    return getattr(request.state, "conn", request.app.state.conn)


def _content(value: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as error:
        raise ValueError("content_base64 must be valid base64") from error


def _result(value: dict) -> dict:
    result = dict(value)
    result["batch"] = asdict(result["batch"])
    return result


@router.post("/procurement-history/csv", status_code=status.HTTP_201_CREATED)
def create_procurement_history(
    payload: ProcurementHistoryCreateRequest,
    request: Request,
    response: Response,
    manager_id: str = Depends(require_manager),
) -> dict:
    try:
        result = procurement_history.register_procurement_history(
            _connection(request), _content(payload.content_base64), manager_id, payload.original_filename,
            evidence_store=getattr(request.app.state, "evidence_store", None),
        )
    except EvidenceStoreError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error))
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))
    if result["idempotent"]:
        response.status_code = status.HTTP_200_OK
    return _result(result)


@router.get("/procurement-history/latest")
def get_latest_procurement_history(
    request: Request,
    manager_id: str = Depends(require_manager),
) -> dict:
    """Safe company context for the command surface; never a source ledger."""
    del manager_id
    summary = procurement_history.latest_published_procurement_history(_connection(request))
    return {"state": "not_loaded"} if summary is None else {"state": "published", "summary": _result(summary)}


@router.get("/procurement-history/{import_batch_id}")
def get_procurement_history(
    import_batch_id: str,
    request: Request,
    manager_id: str = Depends(require_manager),
) -> dict:
    del manager_id
    try:
        return _result(procurement_history.procurement_history_summary(_connection(request), import_batch_id))
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))


@router.post("/procurement-history/{import_batch_id}/review")
def review_procurement_history(
    import_batch_id: str,
    request: Request,
    manager_id: str = Depends(require_manager),
) -> dict:
    try:
        procurement_history.review_procurement_history(_connection(request), import_batch_id, manager_id)
        return _result(procurement_history.procurement_history_summary(_connection(request), import_batch_id))
    except ValueError as error:
        if str(error) == "procurement history batch does not exist":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="procurement history batch not found")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


@router.post("/procurement-history/{import_batch_id}/publish")
def publish_procurement_history(
    import_batch_id: str,
    request: Request,
    manager_id: str = Depends(require_manager),
) -> dict:
    try:
        return _result(procurement_history.publish_procurement_history(_connection(request), import_batch_id, manager_id))
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


@router.post("/procurement-capture/csv", status_code=status.HTTP_201_CREATED)
def create_procurement_capture(
    payload: ProcurementCaptureCreateRequest,
    request: Request,
    response: Response,
    manager_id: str = Depends(require_manager),
) -> dict:
    """Accept a one-season opaque-code snapshot; retain its aggregate only."""
    try:
        result = procurement_capture.register_procurement_capture(
            _connection(request), _content(payload.content_base64), manager_id, payload.original_filename,
            evidence_store=getattr(request.app.state, "evidence_store", None),
        )
    except EvidenceStoreError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error))
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))
    if result["idempotent"]:
        response.status_code = status.HTTP_200_OK
    return _result(result)


@router.get("/procurement-capture/{import_batch_id}")
def get_procurement_capture(
    import_batch_id: str,
    request: Request,
    manager_id: str = Depends(require_manager),
) -> dict:
    del manager_id
    try:
        return _result(procurement_capture.procurement_capture_summary(_connection(request), import_batch_id))
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))


@router.post("/procurement-capture/{import_batch_id}/review")
def review_procurement_capture(
    import_batch_id: str,
    request: Request,
    manager_id: str = Depends(require_manager),
) -> dict:
    try:
        procurement_capture.review_procurement_capture(_connection(request), import_batch_id, manager_id)
        return _result(procurement_capture.procurement_capture_summary(_connection(request), import_batch_id))
    except ValueError as error:
        if str(error) == "procurement capture batch does not exist":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="procurement capture batch not found")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


@router.post("/procurement-capture/{import_batch_id}/publish")
def publish_procurement_capture(
    import_batch_id: str,
    request: Request,
    manager_id: str = Depends(require_manager),
) -> dict:
    try:
        return _result(procurement_capture.publish_procurement_capture(_connection(request), import_batch_id, manager_id))
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))
