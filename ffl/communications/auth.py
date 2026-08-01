"""Fail-closed identity seam for privileged communications operations."""

import hmac
import os
from typing import Optional

from fastapi import HTTPException, Request, status


MANAGER_ROLES = {"farm_manager", "operations_lead", "agronomist"}


def require_manager(request: Request) -> str:
    expected = request.app.state.manager_api_token
    manager_id = request.app.state.manager_person_id
    presented = request.headers.get("x-ffl-manager-token")
    if not expected or not manager_id or not presented or not hmac.compare_digest(expected, presented):
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
