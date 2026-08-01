"""The very small HTTP boundary for the protected Fortune pilot launch."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from ffl.launch_auth import SESSION_FLAG, password_matches, safe_next_path


router = APIRouter(prefix="/api/v1/launch")


class LaunchLoginRequest(BaseModel):
    password: str
    next_path: Optional[str] = None


@router.post("/login")
def login(payload: LaunchLoginRequest, request: Request) -> dict:
    if not password_matches(request.app.state.launch_password, payload.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid launch password")
    request.session.clear()
    request.session[SESSION_FLAG] = True
    return {"status": "authenticated", "next_path": safe_next_path(payload.next_path)}


@router.post("/logout")
def logout(request: Request) -> dict:
    request.session.clear()
    return {"status": "signed_out"}
