"""Server-side manager browser unlock; never a browser bearer-token store."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from ffl.communications.auth import MANAGER_ROLES, active_portal_principal
from ffl.launch_auth import SESSION_FLAG
from ffl.manager_session_auth import (
    MANAGER_SESSION_FLAG,
    active_manager_session,
    begin_manager_session,
    manager_session_configuration_is_present,
    manager_session_matches_secret,
)
from ffl.portal_auth import active_portal_session, end_portal_session
from ffl.password_identity import active_password_principal


router = APIRouter(prefix="/api/v1/manager-session")


class ManagerSessionLoginRequest(BaseModel):
    """The secret stays in this request only and is never persisted or echoed."""

    model_config = ConfigDict(extra="forbid")

    secret: str = Field(min_length=1, max_length=2048)


def _connection(request: Request):
    return getattr(request.state, "conn", request.app.state.conn)


def _configured_manager_is_valid(request: Request) -> bool:
    manager_id = request.app.state.manager_person_id
    if not manager_id:
        return False
    person = _connection(request).execute("SELECT role FROM people WHERE id = ?", (manager_id,)).fetchone()
    return person is not None and person["role"] in MANAGER_ROLES


def _configuration_or_503(request: Request) -> None:
    if not manager_session_configuration_is_present(request.app) or not _configured_manager_is_valid(request):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="manager browser access is unavailable")


@router.get("/status")
def manager_session_status(request: Request) -> dict:
    """A safe UI status surface; it reveals no credentials or identity data."""

    portal_principal = active_portal_principal(request)
    if portal_principal is not None and portal_principal.is_manager:
        portal_session = active_portal_session(request.app, request.session)
        return {
            "authenticated": True,
            "expires_at": portal_session["expires_at"],
            "auth_method": "phone",
        }
    active = active_manager_session(request.app, request.session)
    password_principal = active_password_principal(request)
    if password_principal is not None and password_principal.is_manager:
        return {
            "authenticated": True,
            "expires_at": password_principal.expires_at,
            "auth_method": "id_password",
        }
    if active is None:
        return {"authenticated": False}
    if not _configured_manager_is_valid(request):
        request.session.pop(MANAGER_SESSION_FLAG, None)
        return {"authenticated": False}
    return {"authenticated": True, "expires_at": active["expires_at"]}


@router.post("/login")
def manager_session_login(payload: ManagerSessionLoginRequest, request: Request) -> dict:
    """Authenticate the configured manager into a short-lived signed session."""

    _configuration_or_503(request)
    if not manager_session_matches_secret(request.app.state.manager_session_secret, payload.secret):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid manager secret")
    expires_at = begin_manager_session(request.app, request.session)
    return {"status": "authenticated", "expires_at": expires_at}


@router.post("/logout")
def manager_session_logout(request: Request) -> dict:
    """Remove manager authority without changing the outer launch session."""

    portal_principal = active_portal_principal(request)
    if portal_principal is not None and portal_principal.is_manager:
        end_portal_session(request.session)
        request.session.pop(SESSION_FLAG, None)
        return {"status": "signed_out"}
    password_principal = active_password_principal(request)
    if password_principal is not None and password_principal.is_manager:
        # A password manager session is its own login, so "lock" must not
        # leave a still-valid manager cookie behind.
        request.session.clear()
        return {"status": "signed_out"}
    request.session.pop(MANAGER_SESSION_FLAG, None)
    return {"status": "signed_out"}
