"""Fail-closed, one-time approval boundary for initial pilot setup.

This is intentionally narrower than the normal manager boundary: before a
first farm exists there can be no durable manager person ID to authenticate.
The server-side approval secret is therefore an explicit bootstrap authority,
used alongside the launch session and retired after a successful setup.  It is
not a browser identity system and it must never be placed in a client bundle.
"""

import hmac
import os
from typing import Optional

from fastapi import HTTPException, Request, status


APPROVAL_HEADER = "x-ffl-pilot-setup-approval"


def configured_pilot_setup_approval_token() -> Optional[str]:
    return os.environ.get("FFL_PILOT_SETUP_APPROVAL_TOKEN")


def require_pilot_setup_approval(request: Request) -> str:
    expected = getattr(request.app.state, "pilot_setup_approval_token", None)
    presented = request.headers.get(APPROVAL_HEADER)
    if not expected or not presented or not hmac.compare_digest(expected, presented):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="initial pilot setup approval is required",
        )
    return "bootstrap_setup_approval"
