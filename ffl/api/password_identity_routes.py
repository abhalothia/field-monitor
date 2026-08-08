"""HTTP boundary for private named ID/password accounts and personal work."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from ffl.communications.auth import require_manager
from ffl.launch_auth import SESSION_FLAG
from ffl.password_identity import (
    PasswordIdentityError,
    PasswordIdentityUnavailable,
    active_password_principal,
    authenticate_password_identity,
    begin_password_identity_session,
    change_password_identity,
    list_password_identities,
    provision_password_identity,
)


router = APIRouter(prefix="/api/v1")


class PasswordLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    login_id: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)


class PasswordIdentityProvisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_role: str = Field(pattern=r"^(owner|admin|field_worker|farmer)$")
    login_id: str = Field(min_length=3, max_length=64)
    temporary_password: str = Field(min_length=12, max_length=256)
    person_id: str | None = Field(default=None, min_length=1, max_length=128)
    person_name: str | None = Field(default=None, min_length=2, max_length=160)
    operational_role: str | None = Field(default=None, min_length=3, max_length=64)


class PasswordChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


def _connection(request: Request):
    return getattr(request.state, "conn", request.app.state.conn)


def _principal_or_401(request: Request):
    principal = active_password_principal(request)
    if principal is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="ID sign-in is required")
    return principal


def _unavailable(error: PasswordIdentityUnavailable) -> HTTPException:
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error))


@router.post("/identity/login")
def password_login(payload: PasswordLoginRequest, request: Request) -> dict:
    """Authenticate an explicitly provisioned account without role enumeration."""

    try:
        row = authenticate_password_identity(
            _connection(request), login_id=payload.login_id, password=payload.password,
        )
    except PasswordIdentityUnavailable as error:
        raise _unavailable(error) from error
    except PasswordIdentityError:
        row = None
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="ID or password was not accepted")
    request.session.clear()
    expires_at = begin_password_identity_session(
        request.app, request.session, identity_id=row["id"], password_version=row["password_version"],
    )
    is_manager = row["access_role"] in {"owner", "admin"}
    # The legacy command-centre shell is still behind the launch gate.  Only
    # a live manager account can pass that outer shell; field/farmer accounts
    # use their own scoped API and cannot read the company board.
    if is_manager:
        request.session[SESSION_FLAG] = True
    return {
        "status": "authenticated",
        "person_name": row["person_name"],
        "access_role": row["access_role"],
        "next_path": "/home" if is_manager else "/field-work" if row["access_role"] == "field_worker" else "/farmer",
        "expires_at": expires_at,
    }


@router.post("/identity/logout")
def password_logout(request: Request) -> dict:
    request.session.clear()
    return {"status": "signed_out"}


@router.get("/identity/session")
def password_session(request: Request) -> dict:
    principal = _principal_or_401(request)
    return {
        "authenticated": True,
        "person_name": principal.person_name,
        "access_role": principal.access_role,
        "next_path": "/home" if principal.is_manager else "/field-work" if principal.access_role == "field_worker" else "/farmer",
        "expires_at": principal.expires_at,
    }


@router.post("/identity/password")
def change_password(payload: PasswordChangeRequest, request: Request) -> dict:
    """Rotate the signed-in person's own password; never accepts a person id."""

    principal = _principal_or_401(request)
    try:
        next_version = change_password_identity(
            _connection(request), identity_id=principal.identity_id,
            current_password=payload.current_password, new_password=payload.new_password,
        )
    except PasswordIdentityUnavailable as error:
        raise _unavailable(error) from error
    except PasswordIdentityError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error)) from error
    request.session.clear()
    expires_at = begin_password_identity_session(
        request.app, request.session, identity_id=principal.identity_id, password_version=next_version,
    )
    if principal.is_manager:
        request.session[SESSION_FLAG] = True
    return {"status": "password_changed", "expires_at": expires_at}


@router.get("/my/overview")
def my_overview(request: Request) -> dict:
    """One person's own assigned work/request envelope, never a team directory."""

    principal = _principal_or_401(request)
    conn = _connection(request)
    work_rows = conn.execute(
        """SELECT work.id, work.title, work.status, work.due_at,
                  block.name AS field_name, allocation.crop_name
           FROM work_items work
           JOIN crop_allocations allocation ON allocation.id = work.allocation_id
           JOIN operational_blocks block ON block.id = allocation.operational_block_id
           WHERE work.owner_id = ?
           ORDER BY work.due_at, work.created_at
           LIMIT 30""",
        (principal.person_id,),
    ).fetchall()
    request_rows = conn.execute(
        """SELECT request.id, request.request_kind, request.evidence_required, request.due_at,
                  request.status, block.name AS field_name, allocation.crop_name
           FROM field_information_requests request
           JOIN crop_allocations allocation ON allocation.id = request.allocation_id
           JOIN operational_blocks block ON block.id = allocation.operational_block_id
           WHERE request.target_person_id = ?
             AND request.status IN ('draft', 'ready', 'dispatched')
           ORDER BY request.due_at, request.created_at
           LIMIT 30""",
        (principal.person_id,),
    ).fetchall()
    return {
        "person": {"name": principal.person_name, "role": principal.access_role},
        "work": [
            {"id": row["id"], "title": row["title"], "status": row["status"], "due_at": row["due_at"],
             "field_name": row["field_name"], "crop_name": row["crop_name"]}
            for row in work_rows
        ],
        "requests": [
            {"id": row["id"], "request_kind": row["request_kind"],
             "evidence_required": bool(row["evidence_required"]), "status": row["status"],
             "due_at": row["due_at"], "field_name": row["field_name"], "crop_name": row["crop_name"]}
            for row in request_rows
        ],
    }


@router.get("/identities")
def identities(request: Request, _manager_id: str = Depends(require_manager)) -> dict:
    """Manager-only account list. It deliberately excludes hashes and sessions."""

    try:
        return {"items": list_password_identities(_connection(request))}
    except PasswordIdentityUnavailable as error:
        raise _unavailable(error) from error


@router.post("/identities", status_code=status.HTTP_201_CREATED)
def provision_identity(
    payload: PasswordIdentityProvisionRequest,
    request: Request,
    manager_id: str = Depends(require_manager),
) -> dict:
    """Manager creates a named account; imported rows are never an input here."""

    try:
        principal = provision_password_identity(
            _connection(request), actor_person_id=manager_id,
            access_role=payload.access_role, login_id=payload.login_id,
            temporary_password=payload.temporary_password, person_id=payload.person_id,
            person_name=payload.person_name, operational_role=payload.operational_role,
        )
    except PasswordIdentityUnavailable as error:
        raise _unavailable(error) from error
    except PasswordIdentityError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    return {
        "id": principal.identity_id, "person_id": principal.person_id,
        "person_name": principal.person_name, "access_role": principal.access_role,
    }
