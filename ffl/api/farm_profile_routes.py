"""Manager-only HTTP boundary for safe farm and farmer profiles."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ffl.communications.auth import require_manager
from ffl.services import farm_profiles


router = APIRouter(prefix="/api/v1")


def _connection(request: Request):
    return getattr(request.state, "conn", request.app.state.conn)


def _invalid(detail: str) -> None:
    raise HTTPException(status_code=422, detail=detail)


def _validate_date_window(date_from: str | None, date_to: str | None) -> None:
    """Reject malformed or unbounded profile windows before querying the service."""
    parsed: list[date | None] = []
    for value, name in ((date_from, "date_from"), (date_to, "date_to")):
        if value is None:
            parsed.append(None)
            continue
        try:
            candidate = date.fromisoformat(value)
        except ValueError:
            _invalid("{0} must be an ISO date".format(name))
        if value != candidate.isoformat():
            _invalid("{0} must be an ISO date".format(name))
        parsed.append(candidate)
    start, end = parsed
    if start is not None and end is not None:
        if start > end:
            _invalid("date_from must be on or before date_to")
        if (end - start).days > 366:
            _invalid("date window must not exceed 366 days")


@router.get("/farms")
def list_farms(
    request: Request,
    kind: str = "farm",
    query: str | None = Query(default=None, max_length=80),
    crop: str | None = Query(default=None, max_length=80),
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    state: str | None = None,
    _manager_id: str = Depends(require_manager),
) -> list[dict]:
    """List a bounded, canonical entity directory; candidates stay elsewhere."""
    if kind not in {"farm", "field", "farmer", "field_worker"}:
        _invalid("kind must be farm, field, farmer, or field_worker")
    if state not in {None, "all", "reviewed", "reported"}:
        _invalid("state must be all, reviewed, or reported")
    _validate_date_window(date_from, date_to)
    return farm_profiles.list_entity_directory(
        _connection(request), kind, query, crop, date_from, date_to, limit, state,
    )


@router.get("/farms/{farm_id}")
def get_farm(
    request: Request,
    farm_id: str,
    date_from: str | None = None,
    date_to: str | None = None,
    _manager_id: str = Depends(require_manager),
) -> dict:
    _validate_date_window(date_from, date_to)
    try:
        record = farm_profiles.farm_record(_connection(request), farm_id, date_from, date_to)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if record is None:
        raise HTTPException(status_code=404, detail="farm record not found")
    return record


@router.get("/fields/{block_id}")
def get_field(
    request: Request,
    block_id: str,
    date_from: str | None = None,
    date_to: str | None = None,
    _manager_id: str = Depends(require_manager),
) -> dict:
    _validate_date_window(date_from, date_to)
    try:
        record = farm_profiles.field_record(_connection(request), block_id, date_from, date_to)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if record is None:
        raise HTTPException(status_code=404, detail="field record not found")
    return record


@router.get("/people")
def list_people(
    request: Request,
    kind: str = "farmer",
    query: str | None = Query(default=None, max_length=80),
    crop: str | None = Query(default=None, max_length=80),
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    _manager_id: str = Depends(require_manager),
) -> list[dict]:
    """List only people with an openable canonical Farm assignment."""
    if kind not in {"farmer", "field_worker"}:
        _invalid("kind must be farmer or field_worker")
    _validate_date_window(date_from, date_to)
    return farm_profiles.list_entity_directory(
        _connection(request), kind, query, crop, date_from, date_to, limit, "reviewed",
    )


@router.get("/people/{kind}/{person_id}")
def get_person(
    request: Request,
    kind: str,
    person_id: str,
    date_from: str | None = None,
    date_to: str | None = None,
    _manager_id: str = Depends(require_manager),
) -> dict:
    if kind not in {"farmer", "field_worker"}:
        _invalid("kind must be farmer or field_worker")
    _validate_date_window(date_from, date_to)
    try:
        record = farm_profiles.person_context(
            _connection(request), person_id, kind, date_from, date_to,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if record is None:
        raise HTTPException(status_code=404, detail="person record not found")
    return record


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


@router.get("/reported-field-worker-profiles/{party_id}")
def get_reported_field_worker_profile(
    request: Request, party_id: str, _manager_id: str = Depends(require_manager),
) -> dict:
    profile = farm_profiles.reported_field_worker_profile(_connection(request), party_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="reported field worker profile not found")
    return profile
