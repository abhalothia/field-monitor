"""Evidence and CSV import endpoints.

This router is intentionally not mounted by ``ffl.app`` until the V1 integration
phase chooses the authenticated manager surface that owns it.
"""

import base64
import hashlib
from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel

from ffl.persistence import repository
from ffl.services import evidence, imports


router = APIRouter(prefix="/api/v1")


class EvidenceCreateRequest(BaseModel):
    content_base64: str
    media_type: str
    original_filename: Optional[str] = None
    source_uri: Optional[str] = None
    created_by_person_id: Optional[str] = None


class CsvImportRequest(BaseModel):
    content_base64: str
    purpose: str
    owner_id: str
    original_filename: Optional[str] = None
    reviewed_by: Optional[str] = None


def _connection(request: Request):
    return request.app.state.conn


def _content(value: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("content_base64 must be valid base64") from exc


def _result(value: dict) -> dict:
    result = dict(value)
    result["batch"] = asdict(result["batch"])
    if "rows" in result:
        result["rows"] = [asdict(row) for row in result["rows"]]
    return result


@router.post("/evidence", status_code=status.HTTP_201_CREATED)
def create_evidence(payload: EvidenceCreateRequest, request: Request, response: Response) -> dict:
    try:
        content = _content(payload.content_base64)
        existing = repository.get_evidence_artifact_by_hash(
            _connection(request), hashlib.sha256(content).hexdigest()
        )
        artifact = evidence.retain_evidence(
            _connection(request), content, payload.media_type, payload.original_filename,
            payload.source_uri, payload.created_by_person_id,
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))
    if existing is not None:
        response.status_code = status.HTTP_200_OK
    return asdict(artifact)


@router.post("/imports/csv", status_code=status.HTTP_201_CREATED)
def create_csv_import(payload: CsvImportRequest, request: Request, response: Response) -> dict:
    try:
        result = imports.register_csv_import(
            _connection(request), _content(payload.content_base64), payload.purpose, payload.owner_id,
            payload.original_filename, payload.reviewed_by,
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))
    if result["idempotent"]:
        response.status_code = status.HTTP_200_OK
    return _result(result)


@router.get("/imports/{import_batch_id}")
def get_csv_import(import_batch_id: str, request: Request) -> dict:
    try:
        return _result(imports.get_import(_connection(request), import_batch_id))
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))


@router.post("/imports/{import_batch_id}/publish")
def publish_csv_import(import_batch_id: str, request: Request) -> dict:
    try:
        return _result(imports.publish_import(_connection(request), import_batch_id))
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    except ValueError as error:
        if str(error) == "import batch does not exist":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="import batch not found")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))
