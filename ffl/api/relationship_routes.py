"""Manager-only HTTP boundary for time-bounded operating relationships."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from ffl.communications.auth import require_manager
from ffl.services import relationships


router = APIRouter(prefix="/api/v1")


class PersonOperatingRelationshipCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    person_id: str = Field(min_length=1, max_length=128)
    scope_type: str = Field(min_length=1, max_length=40)
    scope_id: str = Field(min_length=1, max_length=128)
    role: str = Field(min_length=1, max_length=40)
    starts_on: str = Field(min_length=1, max_length=32)
    ends_on: Optional[str] = Field(default=None, max_length=32)
    provenance: Optional[str] = Field(default=None, max_length=1000)


class PersonOperatingRelationshipEndRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ends_on: str = Field(min_length=1, max_length=32)
    reason: str = Field(min_length=1, max_length=500)


def _connection(request: Request):
    return getattr(request.state, "conn", request.app.state.conn)


def _unprocessable(error: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


@router.post("/person-operating-relationships", status_code=status.HTTP_201_CREATED)
def create_person_operating_relationship(
    payload: PersonOperatingRelationshipCreateRequest,
    request: Request,
    manager_id: str = Depends(require_manager),
) -> dict:
    """Create one manager-reviewed person role in one explicit operating scope."""
    try:
        values = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
        relationship = relationships.establish_person_operating_relationship(
            _connection(request), manager_id=manager_id, **values
        )
        return relationships.relationship_summary(relationship)
    except ValueError as error:
        raise _unprocessable(error)


@router.get("/person-operating-relationships")
def list_person_operating_relationships(
    request: Request,
    person_id: Optional[str] = None,
    scope_type: Optional[str] = None,
    scope_id: Optional[str] = None,
    relationship_status: Optional[str] = None,
    manager_id: str = Depends(require_manager),
) -> list[dict]:
    del manager_id
    try:
        return relationships.list_relationship_summaries(
            _connection(request), person_id=person_id, scope_type=scope_type,
            scope_id=scope_id, status=relationship_status,
        )
    except ValueError as error:
        raise _unprocessable(error)


@router.get("/person-operating-relationships/{relationship_id}")
def get_person_operating_relationship(
    relationship_id: str,
    request: Request,
    manager_id: str = Depends(require_manager),
) -> dict:
    del manager_id
    try:
        return relationships.relationship_detail(_connection(request), relationship_id)
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))


@router.post("/person-operating-relationships/{relationship_id}/end")
def end_person_operating_relationship(
    relationship_id: str,
    payload: PersonOperatingRelationshipEndRequest,
    request: Request,
    manager_id: str = Depends(require_manager),
) -> dict:
    """Close a link without deleting its original review/source history."""
    try:
        relationship = relationships.end_person_operating_relationship(
            _connection(request), relationship_id, payload.ends_on, manager_id, payload.reason
        )
        return relationships.relationship_summary(relationship)
    except ValueError as error:
        raise _unprocessable(error)
