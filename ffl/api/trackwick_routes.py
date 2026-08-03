"""Manager-only TrackWick source endpoints.

The browser sees aggregate metrics and source health only.  It never receives
the TrackWick customer id, API key, task identifiers, raw task payloads, mobile
numbers, names, photos, or GPS.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ffl.communications.auth import require_manager
from ffl.persistence import repository
from ffl.services import trackolap_metrics, trackwick_ingest


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
