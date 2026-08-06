"""Fail-closed identity seam for privileged communications operations."""

import hmac
import os
from typing import Optional

from fastapi import HTTPException, Request, status

from ffl.manager_session_auth import active_manager_session
from ffl.password_identity import active_password_principal
from ffl.portal import (
    customer_portal_for_hostname,
    hostname_from_host_header,
    portal_host_is_under_base,
    portal_principal_for_membership,
)
from ffl.portal_auth import active_portal_session


MANAGER_ROLES = {"farm_manager", "operations_lead", "agronomist"}


def active_portal_principal(request: Request):
    """Resolve a customer phone session and re-check its private membership.

    The signed cookie alone is insufficient: a suspended customer portal,
    membership, or identity immediately loses authority on the next request.
    """

    hostname = hostname_from_host_header(request.headers.get("host"))
    base_domain = getattr(request.app.state, "portal_base_domain", "agroceo.com")
    if not portal_host_is_under_base(hostname, base_domain):
        return None
    connection = getattr(request.state, "conn", request.app.state.conn)
    portal = customer_portal_for_hostname(connection, hostname)
    session = active_portal_session(request.app, request.session)
    if portal is None or session is None or session["portal_id"] != portal.id:
        return None
    return portal_principal_for_membership(
        connection, portal_id=portal.id, membership_id=session["membership_id"],
    )


def require_manager(request: Request) -> str:
    portal_principal = active_portal_principal(request)
    portal_hostname = hostname_from_host_header(request.headers.get("host"))
    portal_host = portal_host_is_under_base(
        portal_hostname, getattr(request.app.state, "portal_base_domain", "agroceo.com"),
    )
    if portal_host:
        if portal_principal is None or not portal_principal.is_manager:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="manager authorization is required")
        return portal_principal.person_id
    expected = request.app.state.manager_api_token
    manager_id = request.app.state.manager_person_id
    presented = request.headers.get("x-ffl-manager-token")
    session = active_manager_session(request.app, request.session)
    password_principal = active_password_principal(request)
    if password_principal is not None and password_principal.is_manager:
        # The private password-identity row is re-checked on this request.
        # A signed cookie alone, browser-provided role, or ordinary farmer /
        # field-worker account can never pass this manager boundary.
        return password_principal.person_id
    legacy_header_matches = bool(expected and presented and hmac.compare_digest(expected, presented))
    # The legacy header is retained solely for existing server-to-server and
    # test callers.  The manager browser never receives, stores, or sends it;
    # its authority comes from the signed short-lived session above.
    if not manager_id or (session is None and not legacy_header_matches):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="manager authorization is required")
    connection = getattr(request.state, "conn", request.app.state.conn)
    person = connection.execute("SELECT role FROM people WHERE id = ?", (manager_id,)).fetchone()
    if person is None or person["role"] not in MANAGER_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="manager authorization is not valid")
    return manager_id


def configured_manager_token() -> Optional[str]:
    return os.environ.get("FFL_MANAGER_API_TOKEN")


def configured_manager_person_id() -> Optional[str]:
    return os.environ.get("FFL_MANAGER_PERSON_ID")
