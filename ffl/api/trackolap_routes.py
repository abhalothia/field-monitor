"""Manager-only, aggregate-only TrackOlap source endpoints."""

from __future__ import annotations

import base64
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from ffl.communications.auth import require_manager
from ffl.integrations.trackolap.mapping import MappingManifest, MappingManifestError
from ffl.persistence import repository
from ffl.services.evidence_store import EvidenceStoreError
from ffl.services import trackolap_ingest, trackolap_metrics


router = APIRouter(prefix="/api/v1/trackolap")


class TrackolapCsvImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_base64: str = Field(min_length=1)
    mapping_manifest: dict[str, Any]
    original_filename: Optional[str] = Field(default=None, max_length=255)


def _connection(request: Request):
    return getattr(request.state, "conn", request.app.state.conn)


def _content(value: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as error:
        raise ValueError("content_base64 must be valid base64") from error


def _not_found(error: LookupError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))


def _unprocessable(error: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


@router.post("/imports/csv", status_code=status.HTTP_201_CREATED)
def create_trackolap_csv_import(
    payload: TrackolapCsvImportRequest,
    request: Request,
    response: Response,
    manager_id: str = Depends(require_manager),
) -> dict:
    try:
        manifest = MappingManifest.from_dict(payload.mapping_manifest)
        result = trackolap_ingest.ingest_csv_bundle(
            _connection(request),
            _content(payload.content_base64),
            manifest,
            manager_id,
            original_filename=payload.original_filename or "trackolap-export.zip",
            evidence_store=getattr(request.app.state, "evidence_store", None),
        )
    except EvidenceStoreError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error))
    except (ValueError, MappingManifestError) as error:
        raise _unprocessable(error)
    if result.idempotent:
        response.status_code = status.HTTP_200_OK
    return _safe_import_result(result)


@router.post("/imports/{import_batch_id}/review")
def review_trackolap_import(
    import_batch_id: str,
    request: Request,
    manager_id: str = Depends(require_manager),
) -> dict:
    try:
        batch = trackolap_ingest.review_trackolap_import(_connection(request), import_batch_id, manager_id)
        return _safe_batch(batch)
    except LookupError as error:
        raise _not_found(error)
    except ValueError as error:
        raise _unprocessable(error)


@router.post("/imports/{import_batch_id}/publish")
def publish_trackolap_import(
    import_batch_id: str,
    request: Request,
    manager_id: str = Depends(require_manager),
) -> dict:
    try:
        batch = trackolap_ingest.publish_trackolap_import(
            _connection(request), import_batch_id, manager_id
        )
        return _safe_batch(batch)
    except LookupError as error:
        raise _not_found(error)
    except ValueError as error:
        raise _unprocessable(error)


@router.get("/metrics")
def get_trackolap_metrics(
    request: Request,
    as_of: Optional[str] = None,
    _manager_id: str = Depends(require_manager),
) -> dict:
    try:
        return trackolap_metrics.dashboard_metrics_for_source(_connection(request), as_of=as_of)
    except ValueError as error:
        raise _unprocessable(error)


@router.get("/health")
def get_trackolap_health(request: Request, _manager_id: str = Depends(require_manager)) -> dict:
    """Safe integration status with no endpoint, token, cursor, or raw payload."""
    source = repository.get_source_registry_by_key(_connection(request), trackolap_ingest.SOURCE_KEY)
    if source is None:
        return {"source_key": trackolap_ingest.SOURCE_KEY, "state": "not_configured"}
    runs = repository.list_source_runs(_connection(request), source.id)
    latest = runs[-1] if runs else None
    return {
        "source_key": source.source_key,
        "state": latest.status if latest is not None else "registered",
        "enabled": source.enabled,
        "latest_run": (
            None
            if latest is None
            else {
                "status": latest.status,
                "rows_received": latest.rows_received,
                "rows_accepted": latest.rows_accepted,
                "mapping_version": latest.mapping_version,
            }
        ),
    }


@router.post("/refresh")
def refresh_trackolap_source(
    request: Request,
    manager_id: str = Depends(require_manager),
) -> dict:
    """Operator-triggered live refresh; its response intentionally has no provider data."""
    result = trackolap_ingest.refresh_live_source(_connection(request), manager_id)
    return {
        "source_key": result.source.source_key,
        "state": result.state,
        "valid_count": result.valid_count,
        "quarantined_count": result.quarantined_count,
    }


def _safe_import_result(result: trackolap_ingest.TrackolapIngestResult) -> dict:
    return {
        "source_key": result.source.source_key,
        "import": _safe_batch(result.batch),
        "valid_count": result.valid_count,
        "quarantined_count": result.quarantined_count,
        "idempotent": result.idempotent,
    }


def _safe_batch(batch) -> dict:
    return {
        "id": batch.id,
        "status": batch.status,
        "mapping_version": batch.mapping_version,
        "received_at": batch.received_at,
        "reviewed_at": batch.reviewed_at,
        "published_at": batch.published_at,
    }
