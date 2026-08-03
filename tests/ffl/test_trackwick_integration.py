from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest

from ffl.integrations.trackolap.trackwick import (
    TrackwickApiAdapter,
    TrackwickApiConfig,
    TrackwickFetchResult,
    normalise_trackwick,
)
from ffl.persistence import repository
from ffl.services.trackolap_metrics import dashboard_metrics_for_source
from ffl.services.trackwick_ingest import SOURCE_KEY, refresh_live_trackwick


CONFIG = TrackwickApiConfig(
    customer_id="trackwick-tenant",
    tenant_id="fortune-paddy",
    api_key_reference="env://FFL_TRACKWICK_API_KEY",
)

TASK = {
    "id": "task-1",
    "type": "Farmer Visit",
    "status": "Completed",
    "customerIden": "farmer-1",
    "customerName": "Must Never Be Persisted",
    "customerMobile": "9999999999",
    "employeeIden": "officer-1",
    "completed": 1785751200000,
    "created": 1785750000000,
    "completeGeo": {"lat": 27.95, "lng": 78.27},
    "formDetails": {
        "क्या किसान ने किट ले ली है?": "Yes",
        "स्थान": "Dargava",
        "क्या फसल में कोई कीट है ?": ["Stem Borer", "None"],
        "क्या फसल में कोई रोग है ?": ["None"],
        "जिस कीटनाशक (Pesticide) का छिड़काव किया गया है , सूची में उसका चयन करें ?": ["Product A"],
        "कृपया उस कीटनाशक (Pesticide) का चयन करें, जिसका सुझाव आपने किसानों को दिया है।": ["Product B"],
        "फसल की फोटो": {"url": "https://provider.example/private-photo"},
    },
}

ATTENDANCE = {
    "id": "attendance-provider-1",
    "empId": "officer-1",
    "name": "Must Never Be Persisted",
    "email": "private@example.com",
    "date": "2026-08-03",
    "startTime": "09:00",
}


class RecordingTransport(httpx.BaseTransport):
    def __init__(self):
        self.requests = []

    def handle_request(self, request):
        self.requests.append(request)
        if request.url.path == "/cust/1/api/task/list":
            assert request.url.params["form-type"] == "CUSTOMER"
            assert request.url.params["form-title"] == "Farmer Visit"
            assert request.url.params["pn"] == "0"
            return httpx.Response(200, json={"s": True, "data": [TASK], "hm": False}, request=request)
        if request.url.path == "/cust/1/api/asset/productivity":
            assert request.url.params["date"] == "2026-08-03"
            return httpx.Response(200, json={"s": True, "data": [ATTENDANCE], "hm": False}, request=request)
        return httpx.Response(404, request=request)


def test_trackwick_adapter_uses_verified_get_contract_and_keeps_raw_rows_in_memory():
    transport = RecordingTransport()

    fetched = TrackwickApiAdapter().fetch(
        CONFIG,
        api_key="runtime-key",
        as_of=datetime.fromisoformat("2026-08-03T10:00:00+05:30"),
        transport=transport,
    )
    normalised = normalise_trackwick(fetched, CONFIG, as_of=datetime.fromisoformat("2026-08-03T10:00:00+05:30"))

    assert [request.method for request in transport.requests] == ["GET", "GET"]
    assert all(request.headers["platform"] == "API" for request in transport.requests)
    assert all(request.headers["tlp-cid"] == "trackwick-tenant" for request in transport.requests)
    assert normalised.quarantined_rows == 0
    assert {record.feed for record in normalised.records} == {
        "attendance", "farmer_tasks", "issue_observations", "officers", "pesticide_events", "visits"
    }
    serialized = repr(normalised.records)
    assert "Must Never Be Persisted" not in serialized
    assert "9999999999" not in serialized
    assert "27.95" not in serialized
    assert "private-photo" not in serialized


def test_trackwick_adapter_uses_verified_epoch_creation_window_when_requested():
    transport = RecordingTransport()
    start = datetime(2026, 8, 2, tzinfo=ZoneInfo("Asia/Kolkata"))
    end = datetime(2026, 8, 4, tzinfo=ZoneInfo("Asia/Kolkata"))

    TrackwickApiAdapter().fetch(
        CONFIG,
        api_key="runtime-key",
        as_of=datetime.fromisoformat("2026-08-03T10:00:00+05:30"),
        created_since=start,
        created_until=end,
        transport=transport,
    )

    task_request = transport.requests[0]
    assert task_request.url.params["createDateBegin"] == "1785609000000"
    assert task_request.url.params["createDateEnd"] == "1785781800000"


def test_trackwick_refresh_publishes_only_safe_aggregate_context(ffl_db, owner):
    transport = RecordingTransport()

    result = refresh_live_trackwick(
        ffl_db,
        owner.id,
        config=CONFIG,
        credential_resolver=lambda _: "runtime-key",
        transport=transport,
        as_of=datetime.fromisoformat("2026-08-03T10:00:00+05:30"),
    )

    source = repository.get_source_registry_by_key(ffl_db, SOURCE_KEY)
    records = repository.list_trackolap_records(ffl_db, result.source.id, statuses=("published",))
    snapshot = dashboard_metrics_for_source(
        ffl_db, source_key=SOURCE_KEY, as_of="2026-08-03T18:00:00+05:30"
    )

    assert result.state == "succeeded"
    assert source is not None and source.credentials_reference == "env://FFL_TRACKWICK_API_KEY"
    assert source.endpoint == "https://app.trackolap.com/cust/1/api"
    assert records
    assert "customerName" not in repr(records)
    assert "customerMobile" not in repr(records)
    assert "completeGeo" not in repr(records)
    assert "formDetails" not in repr(records)
    assert snapshot["coverage"] == {
        "taken_kit": 1,
        "visited": 1,
        "recent": 1,
        "overdue": 0,
        "never_visited": 0,
    }
    assert snapshot["visits"]["filed_on_reporting_day"] == 1
    assert snapshot["issues"]["observation_count"] == 1


def test_trackwick_replay_is_idempotent_with_an_overlapping_window(ffl_db, owner):
    as_of = datetime.fromisoformat("2026-08-03T10:00:00+05:30")
    first = refresh_live_trackwick(
        ffl_db, owner.id, config=CONFIG, credential_resolver=lambda _: "runtime-key",
        transport=RecordingTransport(), as_of=as_of,
    )
    before = len(repository.list_trackolap_records(ffl_db, first.source.id, statuses=("published",)))

    replay = refresh_live_trackwick(
        ffl_db, owner.id, config=CONFIG, credential_resolver=lambda _: "runtime-key",
        transport=RecordingTransport(), as_of=as_of,
    )
    after = len(repository.list_trackolap_records(ffl_db, replay.source.id, statuses=("published",)))

    assert replay.state == "succeeded"
    assert after == before


def test_trackwick_refresh_uses_a_delta_window_after_the_first_baseline(ffl_db, owner):
    first_transport = RecordingTransport()
    as_of = datetime.fromisoformat("2026-08-03T10:00:00+05:30")
    refresh_live_trackwick(
        ffl_db, owner.id, config=CONFIG, credential_resolver=lambda _: "runtime-key",
        transport=first_transport, as_of=as_of,
    )
    assert "createDateBegin" not in first_transport.requests[0].url.params

    delta_transport = RecordingTransport()
    result = refresh_live_trackwick(
        ffl_db, owner.id, config=CONFIG, credential_resolver=lambda _: "runtime-key",
        transport=delta_transport, as_of=as_of,
    )

    assert result.state == "succeeded"
    assert delta_transport.requests[0].url.params["createDateBegin"] == "1785609000000"
    assert delta_transport.requests[0].url.params["createDateEnd"] == "1785781800000"


def test_trackwick_refresh_without_configuration_never_calls_provider(ffl_db, owner):
    result = refresh_live_trackwick(ffl_db, owner.id, config=None, credential_resolver=lambda _: "unused")

    assert result.state == "unavailable"
    assert result.reason_code == "configuration_unavailable"


def test_trackwick_refresh_requires_an_accountable_operations_owner(ffl_db):
    grower = repository.create_person(ffl_db, "Grower", "grower")

    with pytest.raises(ValueError, match="authorised Fortune operations lead"):
        refresh_live_trackwick(ffl_db, grower.id, config=CONFIG, credential_resolver=lambda _: "unused")
