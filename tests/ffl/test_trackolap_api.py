from __future__ import annotations

from types import SimpleNamespace

import httpx

from ffl.integrations.trackolap.api import (
    TrackolapApiAdapter,
    TrackolapApiConfig,
    refresh_trackolap,
)
from ffl.integrations.trackolap.contracts import COMMON_FIELDS, REQUIRED_FIELDS
from ffl.persistence import repository
from ffl.services.trackolap_ingest import refresh_live_source


class RecordingTransport(httpx.BaseTransport):
    def __init__(self, handler):
        self.handler = handler
        self.requests = []

    def handle_request(self, request):
        self.requests.append(request)
        return self.handler(request)


def _config() -> TrackolapApiConfig:
    return TrackolapApiConfig.from_dict(
        {
            "tenant_id": "fortune-paddy",
            "base_url": "https://api.trackolap.example",
            "allowed_hosts": ["api.trackolap.example"],
            "reporting_timezone": "Asia/Kolkata",
            "read_only": True,
            "token_reference": "env://FFL_TRACKOLAP_API_TOKEN",
            "project_scope": {"project_id": "fortune-paddy-2026"},
            "mapping_manifest": {
                "version": "fortune-paddy-v1",
                "feeds": {
                    feed: {field: field for field in (*COMMON_FIELDS, *fields)}
                    for feed, fields in REQUIRED_FIELDS.items()
                },
            },
            "endpoints": {
                feed: {
                    "path": "/v1/" + feed,
                    "method": "GET",
                    "rows_path": "rows",
                    "next_cursor_path": "next_cursor",
                    "cursor_param": "cursor",
                    "page_size_param": "limit",
                    "page_size": 50,
                    "max_pages": 2,
                }
                for feed in REQUIRED_FIELDS
            },
        }
    )


SOURCE = SimpleNamespace(credentials_reference="env://FFL_TRACKOLAP_API_TOKEN")
CONFIG = _config()


def test_missing_token_is_unavailable_without_any_http_call():
    transport = RecordingTransport(lambda request: httpx.Response(500, request=request))

    result = refresh_trackolap(SOURCE, CONFIG, credential_resolver=lambda _: None, transport=transport)

    assert result.status == "unavailable"
    assert result.reason_code == "credentials_unavailable"
    assert transport.requests == []


def test_api_adapter_uses_only_get_and_advances_configured_cursor():
    def two_pages(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("cursor") == "cursor-2":
            payload = {"rows": [{"source_id": "visit-2"}], "next_cursor": "cursor-3"}
        else:
            payload = {"rows": [{"source_id": "visit-1"}], "next_cursor": "cursor-2"}
        return httpx.Response(200, json=payload, request=request)

    transport = RecordingTransport(two_pages)
    result = TrackolapApiAdapter().fetch(
        config=CONFIG,
        token="runtime-token",
        cursor="cursor-1",
        transport=transport,
    )

    assert result.cursor == "cursor-3"
    assert result.rows_received == 2
    assert [request.method for request in result.requests] == ["GET", "GET"]


def test_live_refresh_uses_the_shared_mapping_and_persists_no_raw_payload(ffl_db, owner):
    values = {
        "officers": {
            "source_id": "officers-1", "officer_id": "po-riya", "display_name": "Riya Singh",
            "role": "PO", "active_status": "active", "territory_owner_id": "po-riya",
            "effective_from": "2026-06-01",
        },
        "attendance": {
            "source_id": "attendance-1", "attendance_id": "attendance-1", "officer_id": "po-riya",
            "punch_status": "present", "observed_at": "2026-08-03T08:00:00+05:30",
        },
        "farmer_tasks": {
            "source_id": "task-1", "task_id": "task-1", "farmer_code": "farmer-1",
            "territory_owner_id": "po-riya", "village_key": "village-1", "task_status": "active",
            "kit_status": "taken",
        },
        "visits": {
            "source_id": "visit-1", "visit_id": "visit-1", "task_id": "task-1",
            "filing_officer_id": "po-riya", "performed_at": "2026-08-03T09:00:00+05:30",
            "submitted_at": "2026-08-03T09:05:00+05:30", "visit_status": "complete",
        },
        "issue_observations": {
            "source_id": "issue-1", "observation_id": "issue-1", "visit_id": "visit-1",
            "task_id": "task-1", "issue_code": "stem-borer", "severity": "high",
            "observed_at": "2026-08-03T09:00:00+05:30",
        },
        "pesticide_events": {
            "source_id": "event-1", "event_id": "event-1", "task_id": "task-1",
            "product_code": "product-1", "event_kind": "recommended",
            "occurred_at": "2026-08-03T09:00:00+05:30", "kit_version": "pb-1-2026",
        },
    }

    def one_page(request: httpx.Request) -> httpx.Response:
        feed = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(
            200,
            json={
                "rows": [{
                    **values[feed],
                    "tenant_id": "fortune-paddy",
                    "source_updated_at": "2026-08-03T09:05:00+05:30",
                    "provider_task_url": "https://must-not-be-persisted.example/task/1",
                }],
                "next_cursor": None,
            },
            request=request,
        )

    result = refresh_live_source(
        ffl_db,
        owner.id,
        config=CONFIG,
        credential_resolver=lambda _: "runtime-token",
        transport=RecordingTransport(one_page),
    )

    records = repository.list_trackolap_records(ffl_db, result.source.id)
    assert result.state == "succeeded"
    assert len(records) == 6
    assert all("provider_task_url" not in record.values for record in records)
