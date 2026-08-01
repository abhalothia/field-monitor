from dataclasses import asdict

import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from ffl.persistence import repository
from ffl.communications import persistence as communications_persistence
from ffl.communications import service as communications_service
from ffl.communications.auth import require_manager
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


class CommunicationPromptRequest(BaseModel):
    endpoint_id: str
    template_id: str
    idempotency_key: str


class CommunicationEndpointRequest(BaseModel):
    person_id: str
    provider: str
    address: str
    locale: str


class CommunicationConsentRequest(BaseModel):
    purpose: str
    evidence: str


class CommunicationTemplateRequest(BaseModel):
    template_key: str
    version: int
    locale: str
    purpose: str
    body: str
    provider_template_id: Optional[str] = None
    provider_approval_state: str = "not_required"


class CandidateAcceptRequest(BaseModel):
    signal_template_id: Optional[str] = None
    signal_template_version: Optional[int] = None
    exception_owner_id: Optional[str] = None
    exception_fallback_owner_id: Optional[str] = None
    severity: str = "medium"
    signal_values: Optional[Dict[str, Any]] = None
    evidence_artifact_id: Optional[str] = None


def _connection(request: Request):
    return request.app.state.conn


def _communication_provider(request: Request):
    return request.app.state.communication_provider


def _redact_endpoint(endpoint: dict) -> dict:
    return {"id": endpoint["id"], "person_id": endpoint["person_id"], "provider": endpoint["provider"], "address_last4": endpoint["address"][-4:], "locale": endpoint["locale"], "status": endpoint["status"]}


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


@router.post("/work-items/{work_item_id}/communication-prompts", status_code=status.HTTP_201_CREATED)
def create_communication_prompt(work_item_id: str, payload: CommunicationPromptRequest, request: Request, manager_id: str = Depends(require_manager)) -> dict:
    try:
        return communications_service.send_work_prompt(
            _connection(request), _communication_provider(request), work_item_id, payload.endpoint_id,
            payload.template_id, manager_id, payload.idempotency_key,
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


@router.post("/communication-endpoints", status_code=status.HTTP_201_CREATED)
def create_communication_endpoint(payload: CommunicationEndpointRequest, request: Request, manager_id: str = Depends(require_manager)) -> dict:
    try:
        return _redact_endpoint(communications_persistence.create_endpoint(_connection(request), payload.person_id, payload.provider, payload.address, payload.locale))
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


@router.post("/communication-endpoints/{endpoint_id}/consents")
def grant_communication_consent(endpoint_id: str, payload: CommunicationConsentRequest, request: Request, manager_id: str = Depends(require_manager)) -> dict:
    try:
        consent = communications_persistence.set_consent(_connection(request), endpoint_id, payload.purpose, True, payload.evidence, manager_id)
        return {key: consent[key] for key in ("id", "endpoint_id", "purpose", "status", "granted_at", "revoked_at")}
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


@router.post("/communication-endpoints/{endpoint_id}/consents/{purpose}/revoke")
def revoke_communication_consent(endpoint_id: str, purpose: str, payload: CommunicationConsentRequest, request: Request, manager_id: str = Depends(require_manager)) -> dict:
    try:
        consent = communications_persistence.set_consent(_connection(request), endpoint_id, purpose, False, payload.evidence, manager_id)
        return {key: consent[key] for key in ("id", "endpoint_id", "purpose", "status", "granted_at", "revoked_at")}
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


@router.post("/communication-templates", status_code=status.HTTP_201_CREATED)
def create_communication_template(payload: CommunicationTemplateRequest, request: Request, manager_id: str = Depends(require_manager)) -> dict:
    try:
        return communications_persistence.create_template(_connection(request), payload.template_key, payload.version, payload.locale, payload.purpose, payload.body, manager_id, payload.provider_template_id, payload.provider_approval_state)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


@router.post("/communication-templates/{template_id}/publish")
def publish_communication_template(template_id: str, request: Request, manager_id: str = Depends(require_manager)) -> dict:
    try:
        return communications_persistence.publish_template(_connection(request), template_id, manager_id)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


@router.post("/communications/loopmessage/webhook")
async def loopmessage_webhook(request: Request) -> dict:
    provider = _communication_provider(request)
    if not provider.verify_webhook(request.headers.get("authorization")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid LoopMessage webhook authorization")
    try:
        raw_body = await request.body()
        payload = json.loads(raw_body.decode("utf-8"))
        event, created = communications_service.receive_webhook(_connection(request), provider, payload)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        communications_persistence.quarantine(_connection(request), provider.name, str(error), raw_body if "raw_body" in locals() else b"")
        return {"status": "quarantined"}
    return {"status": "accepted" if created else "duplicate", "event_id": event["id"], "candidate_id": event.get("candidate_id")}


@router.get("/communications/inbox")
def communications_inbox(request: Request, manager_id: str = Depends(require_manager)) -> dict:
    return {"candidates": communications_persistence.inbox(_connection(request))}


@router.get("/communications/health")
def communications_health(request: Request, manager_id: str = Depends(require_manager)) -> dict:
    return communications_persistence.health(_connection(request))


@router.post("/communications/prompts/{prompt_id}/no-response")
def mark_communication_no_response(prompt_id: str, request: Request, manager_id: str = Depends(require_manager)) -> dict:
    try:
        return communications_service.mark_no_response(_connection(request), prompt_id, manager_id)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


@router.post("/communications/candidates/{candidate_id}/accept")
def accept_communication_candidate(candidate_id: str, payload: CandidateAcceptRequest, request: Request, manager_id: str = Depends(require_manager)) -> dict:
    try:
        return communications_service.accept_candidate(
            _connection(request), candidate_id, manager_id, payload.signal_template_id,
            payload.signal_template_version, payload.exception_owner_id, payload.exception_fallback_owner_id,
            payload.severity, payload.signal_values, payload.evidence_artifact_id,
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


@router.post("/communications/candidates/{candidate_id}/reject")
def reject_communication_candidate(candidate_id: str, request: Request, manager_id: str = Depends(require_manager)) -> dict:
    try:
        return communications_service.reject_candidate(_connection(request), candidate_id, manager_id)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))
