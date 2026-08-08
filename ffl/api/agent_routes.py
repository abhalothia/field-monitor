"""Private manager endpoints for simple, human-written operating agents."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ffl.communications.auth import require_manager, require_operating_read
from ffl.persistence import repository
from ffl.services import agent_notifications


router = APIRouter(prefix="/api/v1/agents")


class AgentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    instruction: str = Field(min_length=8, max_length=500)
    enabled: bool = False

    @field_validator("name", "instruction")
    @classmethod
    def nonempty(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if not value.strip():
            raise ValueError("value must not be blank")
        return value.strip()


class AgentUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    instruction: Optional[str] = Field(default=None, min_length=8, max_length=500)
    enabled: Optional[bool] = None

    @field_validator("name", "instruction")
    @classmethod
    def nonempty(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not value.strip():
            raise ValueError("value must not be blank")
        return value.strip() if value is not None else None


def _connection(request: Request):
    return getattr(request.state, "conn", request.app.state.conn)


def _item(item: repository.AgentNotification) -> dict:
    return {
        "id": item.id, "name": item.name, "instruction": item.natural_language_rule,
        "enabled": item.enabled, "status": "live" if item.enabled else "in_review", "updated_at": item.updated_at,
    }


@router.get("")
def get_agents(request: Request, _manager_id: str = Depends(require_operating_read)) -> dict:
    return agent_notifications.board(_connection(request))


@router.post("", status_code=status.HTTP_201_CREATED)
def create_agent(payload: AgentCreateRequest, request: Request,
                 manager_id: str = Depends(require_manager)) -> dict:
    try:
        return _item(repository.create_agent_notification(
            _connection(request), manager_id, payload.name or "Agent request", payload.instruction, payload.enabled,
        ))
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


@router.patch("/{agent_id}")
def update_agent(agent_id: str, payload: AgentUpdateRequest, request: Request,
                 _manager_id: str = Depends(require_manager)) -> dict:
    if payload.name is None and payload.instruction is None and payload.enabled is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="provide a change")
    try:
        return _item(repository.update_agent_notification(
            _connection(request), agent_id, name=payload.name,
            natural_language_rule=payload.instruction, enabled=payload.enabled,
        ))
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
