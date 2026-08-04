"""Customer-portal phone sign-in boundary.

These routes intentionally expose only the current tenant's display name and
the signed-in person's own role.  They never return TrackWick contacts, raw
phone numbers, provider responses, or a tenant directory.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from ffl.launch_auth import SESSION_FLAG
from ffl.portal import (
    customer_portal_for_hostname,
    eligible_phone_identity,
    hostname_from_host_header,
    normalise_phone_e164,
    portal_host_is_under_base,
    portal_principal_for_membership,
    activate_phone_identity,
)
from ffl.portal_auth import (
    PortalOtpError,
    active_portal_session,
    begin_portal_session,
    end_portal_session,
    portal_session_configuration_is_present,
)


router = APIRouter(prefix="/api/v1/portal")


class PhoneCodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: str = Field(min_length=8, max_length=16)


class VerifyPhoneCodeRequest(PhoneCodeRequest):
    code: str = Field(min_length=4, max_length=12, pattern=r"^[0-9]+$")


def _connection(request: Request):
    return getattr(request.state, "conn", request.app.state.conn)


def portal_for_request(request: Request):
    hostname = hostname_from_host_header(request.headers.get("host"))
    base_domain = getattr(request.app.state, "portal_base_domain", "agroceo.com")
    if not portal_host_is_under_base(hostname, base_domain):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="customer portal was not found")
    portal = customer_portal_for_hostname(_connection(request), hostname)
    if portal is None or portal.status != "active":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="customer portal was not found")
    return portal


def portal_principal_from_request(request: Request, *, require_manager: bool = False):
    portal = portal_for_request(request)
    session = active_portal_session(request.app, request.session)
    if session is None or session["portal_id"] != portal.id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="phone sign-in is required")
    principal = portal_principal_for_membership(
        _connection(request), portal_id=portal.id, membership_id=session["membership_id"],
    )
    if principal is None:
        end_portal_session(request.session)
        request.session.pop(SESSION_FLAG, None)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="phone sign-in is required")
    if require_manager and not principal.is_manager:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="manager authorization is required")
    return principal


@router.get("/bootstrap")
def portal_bootstrap(request: Request) -> dict:
    portal = portal_for_request(request)
    provider = request.app.state.portal_auth_provider
    return {
        "portal": {"slug": portal.slug, "name": portal.display_name},
        "phone_sign_in": {
            "enabled": bool(provider.configured and portal_session_configuration_is_present(request.app)),
            "delivery_channel": provider.delivery_channel if provider.configured else None,
        },
    }


@router.post("/auth/request-code")
def request_phone_code(payload: PhoneCodeRequest, request: Request) -> dict:
    portal = portal_for_request(request)
    try:
        phone = normalise_phone_e164(payload.phone)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    # Deliberately generic: callers cannot use this endpoint to enumerate who
    # is an approved Fortune farmer, worker, or staff member.
    candidate = eligible_phone_identity(_connection(request), portal_id=portal.id, phone_e164=phone)
    provider = request.app.state.portal_auth_provider
    if candidate is not None and provider.configured and portal_session_configuration_is_present(request.app):
        try:
            provider.request_code(phone)
        except PortalOtpError:
            # A user sees one safe retry message, never an upstream account,
            # sender, template, or credential diagnostic.
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="phone sign-in is temporarily unavailable")
    return {"status": "code_requested"}


@router.post("/auth/verify-code")
def verify_phone_code(payload: VerifyPhoneCodeRequest, request: Request) -> dict:
    portal = portal_for_request(request)
    try:
        phone = normalise_phone_e164(payload.phone)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    candidate = eligible_phone_identity(_connection(request), portal_id=portal.id, phone_e164=phone)
    provider = request.app.state.portal_auth_provider
    if candidate is None or not provider.configured or not portal_session_configuration_is_present(request.app):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="phone code could not be verified")
    try:
        verified = provider.verify_code(phone, payload.code)
        verified_phone = normalise_phone_e164(verified.phone_e164)
        if verified_phone != phone:
            raise PortalOtpError("phone code could not be verified")
        principal = activate_phone_identity(
            _connection(request), portal_id=portal.id, phone_e164=phone, auth_subject=verified.auth_subject,
        )
    except (PortalOtpError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="phone code could not be verified")
    expires_at = begin_portal_session(
        request.app, request.session, portal_id=portal.id, membership_id=principal.membership_id,
    )
    # Existing manager APIs have a launch shell gate in front of them.  Only a
    # verified tenant owner/admin gets that shell flag; all privileged routes
    # still independently re-check the active portal membership.
    if principal.is_manager:
        request.session[SESSION_FLAG] = True
    return {
        "status": "authenticated",
        "portal_role": principal.portal_role,
        "next_path": "/manager" if principal.is_manager else "/",
        "expires_at": expires_at,
    }


@router.get("/session")
def portal_session(request: Request) -> dict:
    principal = portal_principal_from_request(request)
    session = active_portal_session(request.app, request.session)
    return {
        "authenticated": True,
        "person_name": principal.person_name,
        "portal_role": principal.portal_role,
        "next_path": "/manager" if principal.is_manager else "/",
        "expires_at": session["expires_at"],
    }


@router.post("/auth/logout")
def portal_logout(request: Request) -> dict:
    # Resolve the hostname before modifying a cookie, so a request on the main
    # domain cannot erase a distinct customer portal session.
    portal_for_request(request)
    end_portal_session(request.session)
    request.session.pop(SESSION_FLAG, None)
    return {"status": "signed_out"}
