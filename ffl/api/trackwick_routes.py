"""Manager-only TrackWick source endpoints.

The manager board exposes a deliberately small working view: names, reported
farm candidates, open work, and source evidence points. It never receives the
TrackWick customer id, API key, provider identifiers, raw task payloads,
mobile numbers, remote media URLs, or addresses.
"""

from __future__ import annotations

import hmac
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ffl.communications.auth import require_manager, require_operating_read
from ffl.persistence import repository
from ffl.services import trackolap_metrics, trackwick_board, trackwick_ingest


router = APIRouter(prefix="/api/v1/trackwick")


def _connection(request: Request):
    return getattr(request.state, "conn", request.app.state.conn)


@router.get("/metrics")
def get_trackwick_metrics(
    request: Request,
    as_of: Optional[str] = None,
    _manager_id: str = Depends(require_manager),
) -> dict:
    try:
        return trackolap_metrics.dashboard_metrics_for_source(
            _connection(request), source_key=trackwick_ingest.SOURCE_KEY, as_of=as_of
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


@router.get("/health")
def get_trackwick_health(request: Request, _manager_id: str = Depends(require_manager)) -> dict:
    """Return safe source status without connection details or provider fields."""
    source = repository.get_source_registry_by_key(_connection(request), trackwick_ingest.SOURCE_KEY)
    if source is None:
        return {"source_key": trackwick_ingest.SOURCE_KEY, "state": "not_configured"}
    runs = repository.list_source_runs(_connection(request), source.id)
    latest = runs[-1] if runs else None
    return {
        "source_key": source.source_key,
        "state": latest.status if latest is not None else "registered",
        "enabled": source.enabled,
        "latest_run": (
            None
            if latest is None
            else {
                "status": latest.status,
                "rows_received": latest.rows_received,
                "rows_accepted": latest.rows_accepted,
                "mapping_version": latest.mapping_version,
            }
        ),
    }


@router.get("/board")
def get_trackwick_board(request: Request, _manager_id: str = Depends(require_manager)) -> dict:
    """Return the browser-safe manager board, never private source primitives."""
    return trackwick_board.command_centre_board_for_source(
        _connection(request), source_key=trackwick_ingest.SOURCE_KEY
    )


@router.get("/command-centre-board")
def get_command_centre_board(request: Request, _manager_id: str = Depends(require_operating_read)) -> dict:
    return trackwick_board.command_centre_board_for_source(
        _connection(request), source_key=trackwick_ingest.SOURCE_KEY
    )


@router.get("/daily-brief-reading")
def get_daily_brief_reading(request: Request, _manager_id: str = Depends(require_operating_read)) -> dict:
    """Return the optional AI wording without delaying the operating board."""
    return {
        "reading": trackwick_board.daily_brief_reading_for_source(
            _connection(request), source_key=trackwick_ingest.SOURCE_KEY,
        )
    }


@router.post("/refresh")
def refresh_trackwick_source(
    request: Request,
    manager_id: str = Depends(require_manager),
) -> dict:
    """Run a manual, server-only, read-only TrackWick refresh."""
    try:
        result = trackwick_ingest.refresh_live_trackwick(_connection(request), manager_id)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))
    return {
        "source_key": result.source.source_key,
        "state": result.state,
        "valid_count": result.valid_count,
        "quarantined_count": result.quarantined_count,
    }


@router.api_route("/cron-refresh", methods=["GET", "POST"])
def refresh_trackwick_source_on_schedule(request: Request) -> dict:
    """Run the same private refresh from Vercel Cron, never from the browser."""
    expected = os.environ.get("CRON_SECRET")
    presented = request.headers.get("authorization", "")
    if not expected or not hmac.compare_digest(presented, "Bearer " + expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="cron authorization is required")
    manager_id = request.app.state.manager_person_id
    if not manager_id:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="refresh owner is unavailable")
    result = trackwick_ingest.refresh_live_trackwick(_connection(request), manager_id)
    return {
        "source_key": result.source.source_key,
        "state": result.state,
        "valid_count": result.valid_count,
        "quarantined_count": result.quarantined_count,
    }
