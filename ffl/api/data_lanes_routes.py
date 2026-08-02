"""Read-only manager surface for the five FFL operating-data lanes."""

from fastapi import APIRouter, Request

from ffl.services import data_lanes


router = APIRouter(prefix="/api/v1")


@router.get("/data-lanes")
def get_data_lanes(request: Request) -> dict:
    """Return aggregate readiness only; never refresh or persist source data."""
    connection = getattr(request.state, "conn", request.app.state.conn)
    return data_lanes.data_lanes_snapshot(connection)
