"""Manager-safe API for trusted external context sources.

The application installs no provider adapter by default, so refresh remains a
deterministic unavailable run until a provider access review adds one.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel

from ffl.persistence import repository
from ffl.services import sources


router = APIRouter(prefix="/api/v1")


class SourceRegistrationRequest(BaseModel):
    source_key: str
    display_name: str
    source_type: str
    purpose: str
    authority_level: str
    owner_id: str
    permitted_data_classes: List[str]
    schema_version: str
    mapping_version: str
    default_coverage: Dict[str, Any]
    credentials_reference: Optional[str] = None
    endpoint: Optional[str] = None
    freshness_target_hours: Optional[float] = None
    license_notes: Optional[str] = None
    enabled: bool = False


def _connection(request: Request):
    return request.app.state.conn


def _not_found(error: LookupError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))


def _unprocessable(error: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


@router.get("/sources/india-candidates")
def get_india_source_candidates() -> List[dict]:
    return sources.india_source_candidates()


@router.get("/regional-context")
def get_regional_context(region: str, request: Request) -> dict:
    try:
        return sources.regional_context(_connection(request), region)
    except ValueError as error:
        raise _unprocessable(error)


@router.post("/sources", status_code=status.HTTP_201_CREATED)
def create_source(payload: SourceRegistrationRequest, request: Request, response: Response) -> dict:
    try:
        values = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
        existing = repository.get_source_registry_by_key(_connection(request), values["source_key"])
        source = sources.register_source(_connection(request), **values)
        if existing is not None:
            response.status_code = status.HTTP_200_OK
        return sources.source_status(_connection(request), source)
    except ValueError as error:
        raise _unprocessable(error)


@router.get("/sources")
def get_source_statuses(request: Request) -> List[dict]:
    return sources.list_source_statuses(_connection(request))


@router.get("/sources/{source_key}")
def get_source_status(source_key: str, request: Request) -> dict:
    try:
        return sources.get_source_status(_connection(request), source_key)
    except LookupError as error:
        raise _not_found(error)


@router.get("/sources/{source_key}/runs")
def get_source_runs(source_key: str, request: Request) -> List[dict]:
    try:
        return sources.list_source_run_summaries(_connection(request), source_key)
    except LookupError as error:
        raise _not_found(error)


@router.post("/sources/{source_key}/refresh")
def refresh_source(source_key: str, request: Request) -> dict:
    try:
        # The app does not install adapters until an operator completes the
        # provider's access review.  This call therefore remains a safe,
        # durable unavailable state rather than attempting a network request.
        sources.refresh_source(_connection(request), source_key)
        return sources.get_source_status(_connection(request), source_key)
    except LookupError as error:
        raise _not_found(error)
