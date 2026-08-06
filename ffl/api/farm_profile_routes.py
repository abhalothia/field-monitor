"""Manager-only HTTP boundary for safe farm and farmer profiles."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from ffl.communications.auth import require_manager
from ffl.services import farm_profiles


router = APIRouter(prefix="/api/v1")


def _connection(request: Request):
    return getattr(request.state, "conn", request.app.state.conn)


@router.get("/farm-profiles/{block_id}")
def get_farm_profile(
    request: Request, block_id: str, _manager_id: str = Depends(require_manager),
) -> dict:
    profile = farm_profiles.farm_profile(_connection(request), block_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="farm profile not found")
    return profile


@router.get("/farmer-profiles/{person_id}")
def get_farmer_profile(
    request: Request, person_id: str, _manager_id: str = Depends(require_manager),
) -> dict:
    profile = farm_profiles.farmer_profile(_connection(request), person_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="farmer profile not found")
    return profile


@router.get("/reported-farm-profiles/{candidate_id}")
def get_reported_farm_profile(
    request: Request, candidate_id: str, _manager_id: str = Depends(require_manager),
) -> dict:
    profile = farm_profiles.reported_farm_profile(_connection(request), candidate_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="reported farm profile not found")
    return profile


@router.get("/reported-farmer-profiles/{party_id}")
def get_reported_farmer_profile(
    request: Request, party_id: str, _manager_id: str = Depends(require_manager),
) -> dict:
    profile = farm_profiles.reported_farmer_profile(_connection(request), party_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="reported farmer profile not found")
    return profile
