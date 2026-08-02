"""Evidence and CSV import endpoints for the FFL operating application."""

import base64
from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel

from ffl.services import evidence, imports
from ffl.services.evidence_store import EvidenceStoreError


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


class ImportReviewRequest(BaseModel):
    reviewer_id: str


def _connection(request: Request):
    return getattr(request.state, "conn", request.app.state.conn)


def _evidence_store(request: Request):
    return getattr(request.app.state, "evidence_store", None)


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
        artifact, created = evidence.retain_evidence_result(
            _connection(request), content, payload.media_type, payload.original_filename,
            payload.source_uri, payload.created_by_person_id, store=_evidence_store(request),
        )
    except EvidenceStoreError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error))
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))
    if not created:
        response.status_code = status.HTTP_200_OK
    return asdict(artifact)


@router.post("/imports/csv", status_code=status.HTTP_201_CREATED)
def create_csv_import(payload: CsvImportRequest, request: Request, response: Response) -> dict:
    if payload.purpose == "farm_manifest":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="farm_manifest imports require the manager-only /farm-manifests/csv route",
        )
    try:
        result = imports.register_csv_import(
            _connection(request), _content(payload.content_base64), payload.purpose, payload.owner_id,
            payload.original_filename, evidence_store=_evidence_store(request),
        )
    except EvidenceStoreError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error))
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))
    if result["idempotent"]:
        response.status_code = status.HTTP_200_OK
    return _result(result)


@router.get("/imports/{import_batch_id}")
def get_csv_import(import_batch_id: str, request: Request) -> dict:
    try:
        result = imports.get_import(_connection(request), import_batch_id)
        if result["batch"].purpose == "farm_manifest":
            raise LookupError("import batch not found")
        return _result(result)
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))


@router.post("/imports/{import_batch_id}/review")
def review_csv_import(import_batch_id: str, payload: ImportReviewRequest, request: Request) -> dict:
    try:
        batch = imports.review_import(_connection(request), import_batch_id, payload.reviewer_id)
    except ValueError as error:
        if str(error) == "import batch does not exist":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="import batch not found")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))
    return _result({"batch": batch, "counters": imports.get_import(_connection(request), batch.id)["counters"]})


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
