"""Narrow manager-only boundary for reviewed farm-manifest imports."""

import base64
from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from ffl.communications.auth import require_manager
from ffl.services import imports
from ffl.services.evidence_store import EvidenceStoreError


router = APIRouter(prefix="/api/v1")


class FarmManifestCreateRequest(BaseModel):
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
    if "batch" in result:
        result["batch"] = asdict(result["batch"])
    return result


def _not_found(error: LookupError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))


def _unprocessable(error: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


@router.post("/farm-manifests/csv", status_code=status.HTTP_201_CREATED)
def create_farm_manifest(
    payload: FarmManifestCreateRequest,
    request: Request,
    response: Response,
    manager_id: str = Depends(require_manager),
) -> dict:
    try:
        result = imports.register_farm_manifest(
            _connection(request), _content(payload.content_base64), manager_id,
            payload.original_filename, evidence_store=getattr(request.app.state, "evidence_store", None),
        )
    except EvidenceStoreError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error))
    except ValueError as error:
        raise _unprocessable(error)
    if result["idempotent"]:
        response.status_code = status.HTTP_200_OK
    return _result({"batch": result["batch"], "counters": result["counters"]})


@router.get("/farm-manifests/{import_batch_id}")
def get_farm_manifest(
    import_batch_id: str,
    request: Request,
    manager_id: str = Depends(require_manager),
) -> dict:
    del manager_id
    try:
        return _result(imports.farm_manifest_summary(_connection(request), import_batch_id))
    except LookupError as error:
        raise _not_found(error)


@router.post("/farm-manifests/{import_batch_id}/review")
def review_farm_manifest(
    import_batch_id: str,
    request: Request,
    manager_id: str = Depends(require_manager),
) -> dict:
    try:
        imports.review_farm_manifest(_connection(request), import_batch_id, manager_id)
        return _result(imports.farm_manifest_summary(_connection(request), import_batch_id))
    except ValueError as error:
        if str(error) == "farm manifest does not exist":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="farm manifest not found")
        raise _unprocessable(error)
    except LookupError as error:
        raise _not_found(error)


@router.post("/farm-manifests/{import_batch_id}/publish")
def publish_farm_manifest(
    import_batch_id: str,
    request: Request,
    manager_id: str = Depends(require_manager),
) -> dict:
    try:
        return _result(imports.publish_farm_manifest(_connection(request), import_batch_id, manager_id))
    except LookupError as error:
        raise _not_found(error)
    except ValueError as error:
        raise _unprocessable(error)
