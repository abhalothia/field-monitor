from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel

from ffl.persistence import repository
from ffl.services import operations


router = APIRouter(prefix="/api/v1")


class TransitionRequest(BaseModel):
    status: str
    actor_id: str
    reason: str


class ExceptionCreateRequest(BaseModel):
    allocation_id: str
    title: str
    severity: str
    owner_id: str
    fallback_owner_id: str
    observed_at: str
    idempotency_key: str


def _connection(request: Request):
    return request.app.state.conn


def _runtime_rows(conn, table: str, where: str = "", params: tuple = ()) -> list[dict]:
    query = "SELECT * FROM {0}".format(table)
    if where:
        query = "{0} WHERE {1}".format(query, where)
    query = "{0} ORDER BY created_at".format(query)
    return [dict(row) for row in conn.execute(query, params).fetchall()]


@router.get("/runtime")
def get_runtime(request: Request) -> dict:
    conn = _connection(request)
    row = conn.execute("SELECT * FROM operating_units ORDER BY created_at LIMIT 1").fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="operating unit not found")

    operating_unit = dict(row)
    allocations = _runtime_rows(
        conn, "crop_allocations", "operating_unit_id = ? AND status = 'active'", (operating_unit["id"],)
    )
    allocation_ids = [allocation["id"] for allocation in allocations]
    if not allocation_ids:
        return {"operating_unit": operating_unit, "allocations": [], "work_items": [], "exceptions": []}

    placeholders = ", ".join("?" for _ in allocation_ids)
    work_items = _runtime_rows(conn, "work_items", "allocation_id IN ({0})".format(placeholders), tuple(allocation_ids))
    exceptions = _runtime_rows(conn, "exception_records", "allocation_id IN ({0})".format(placeholders), tuple(allocation_ids))
    return {
        "operating_unit": operating_unit,
        "allocations": allocations,
        "work_items": work_items,
        "exceptions": exceptions,
    }


@router.post("/work-items/{work_item_id}/transitions")
def transition_work_item(work_item_id: str, payload: TransitionRequest, request: Request) -> dict:
    try:
        work_item = operations.transition_work_item(
            _connection(request), work_item_id, payload.status, payload.actor_id, payload.reason
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))
    return asdict(work_item)


@router.post("/exceptions", status_code=status.HTTP_201_CREATED)
def create_exception(payload: ExceptionCreateRequest, request: Request, response: Response) -> dict:
    conn = _connection(request)
    existing = repository.get_exception_by_idempotency_key(conn, payload.idempotency_key)
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return asdict(existing)

    try:
        exception = operations.report_exception(
            conn,
            payload.allocation_id,
            payload.title,
            payload.severity,
            payload.owner_id,
            payload.fallback_owner_id,
            payload.observed_at,
            payload.idempotency_key,
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))
    return asdict(exception)


@router.get("/exceptions/{exception_id}")
def get_exception(exception_id: str, request: Request) -> dict:
    conn = _connection(request)
    exception = repository.get_exception_record(conn, exception_id)
    if exception is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="exception not found")
    return {
        **asdict(exception),
        "audit_events": [
            asdict(event) for event in operations.list_audit_events(conn, "exception_record", exception_id)
        ],
    }


@router.post("/exceptions/{exception_id}/transitions")
def transition_exception(exception_id: str, payload: TransitionRequest, request: Request) -> dict:
    try:
        exception = operations.transition_exception(
            _connection(request), exception_id, payload.status, payload.actor_id, payload.reason
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))
    return asdict(exception)
