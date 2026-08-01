"""Read-only FFL portfolio endpoint."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Request, status

from ffl.services import portfolio


router = APIRouter(prefix="/api/v1")


@router.get("/portfolio")
def get_portfolio(request: Request, as_of: Optional[str] = None) -> dict:
    try:
        current_time = portfolio.parse_as_of(as_of) if as_of is not None else None
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))
    return portfolio.portfolio_snapshot(
        getattr(request.state, "conn", request.app.state.conn), as_of=current_time
    )
