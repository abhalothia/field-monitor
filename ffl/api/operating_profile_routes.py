"""Read-only operating profile used by the manager command surface."""

from fastapi import APIRouter, Request


router = APIRouter(prefix="/api/v1")


@router.get("/operating-profile")
def get_operating_profile(request: Request) -> dict:
    return request.app.state.operating_profile
