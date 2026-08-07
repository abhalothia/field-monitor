from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest

from ffl.integrations.trackolap.trackwick import (
    TrackwickApiAdapter,
    TrackwickApiConfig,
    TrackwickFetchResult,
    normalise_trackwick_basics,
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

CUSTOMER = {
    "id": "customer-row-1",
    "iden": "farmer-1",
    "name": "Fortune Farmer",
    "mobile": "9999999999",
    "geo": {"lat": 27.95, "lng": 78.27},
    "owner": "officer-1",
    "status": "ACTIVE",
    "tag": "PB1",
    "createdOn": 1785750000000,
}

REGISTRATION_TASK = {
    "id": "registration-1",
    "type": "New Farmer Registration",
    "status": "Completed",
    "customerIden": "farmer-1",
    "customerName": "Fortune Farmer",
    "employeeIden": "officer-1",
    "assignedTo": "Fortune Field Worker",
    "completed": 1785751200000,
    "formDetails": {
        "Village": "Dargava",
        "Block": "Gabhana",
        "District": "Aligarh",
        "Total Acre": "5.5",
        "Number of Plots": "2",
        "P.B-1 Acre": "3",
        "1718 Acre": "2.5",
        "Aadhar No": "111122223333",
        "Aadhar Card Photo": {"url": "https://provider.example/private-aadhaar-photo"},
        "Mobile No": "9999999999",
        "Farmer Signature": {"url": "https://provider.example/private-signature"},
        "Geo": {"lat": 27.95, "lng": 78.27},
    },
}


class RecordingTransport(httpx.BaseTransport):
    def __init__(self):
        self.requests = []

    def handle_request(self, request):
        self.requests.append(request)
        if request.url.path == "/cust/1/api/task/list":
            assert request.url.params["pn"] == "0"
            return httpx.Response(200, json={"s": True, "data": [TASK], "hm": False}, request=request)
        if request.url.path == "/cust/1/api/customer/list":
            assert request.url.params["pn"] == "0"
            return httpx.Response(200, json={"s": True, "data": [CUSTOMER], "hm": False}, request=request)
        if request.url.path == "/cust/1/api/asset/productivity":
            assert request.url.params["date"] == "2026-08-03"
            return httpx.Response(200, json={"s": True, "data": [ATTENDANCE], "hm": False}, request=request)
        return httpx.Response(404, request=request)


class TaskPayloadTransport(httpx.BaseTransport):
    def __init__(self, tasks):
        self.tasks = tasks

    def handle_request(self, request):
        if request.url.path == "/cust/1/api/task/list":
            return httpx.Response(
                200,
                json={"s": True, "data": self.tasks, "hm": False},
                request=request,
            )
        if request.url.path in {
            "/cust/1/api/customer/list",
            "/cust/1/api/asset/productivity",
        }:
            return httpx.Response(
                200, json={"s": True, "data": [], "hm": False}, request=request
            )
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

    assert [request.method for request in transport.requests] == ["GET", "GET", "GET"]
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


def test_trackwick_basics_are_allow_listed_and_never_include_contact_or_evidence_fields():
    basics = normalise_trackwick_basics(
        TrackwickFetchResult(tasks=(REGISTRATION_TASK,), customers=(CUSTOMER,), attendance=(), task_pages=1, customer_pages=1),
        CONFIG,
        as_of=datetime.fromisoformat("2026-08-03T10:00:00+05:30"),
    )

    profiles = [record.values for record in basics.records if record.feed == "farmer_profiles"]
    farms = [record.values for record in basics.records if record.feed == "farm_candidates"]
    workers = [record.values for record in basics.records if record.feed == "field_workers"]
    serialized = repr(basics.records)

    assert profiles == [{
        "farmer_id": "farmer-1",
        "display_name": "Fortune Farmer",
        "crm_status": "active",
        "territory_owner_id": "officer-1",
        "registered_at": "2026-08-03T15:10:00+05:30",
    }]
    assert farms == [{
        "farm_candidate_id": "registration-1",
        "farmer_id": "farmer-1",
        "village": "Dargava",
        "block": "Gabhana",
        "district": "Aligarh",
        "reported_area_acres": "5.5",
        "reported_plot_count": "2",
        "pb1_area_acres": "3",
        "var1718_area_acres": "2.5",
        "registration_status": "completed",
    }]
    assert workers == [{
        "worker_id": "officer-1",
        "display_name": "Fortune Field Worker",
        "last_activity_at": "2026-08-03T15:30:00+05:30",
        "activity_status": "completed",
    }]
    for forbidden in ("9999999999", "111122223333", "private-aadhaar-photo", "private-signature", "27.95", "formDetails"):
        assert forbidden not in serialized


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


def test_trackwick_uses_only_an_explicitly_configured_form_field_for_issue_severity():
    task = dict(TASK)
    task["formDetails"] = dict(TASK["formDetails"], **{"Issue severity": "High"})
    config = TrackwickApiConfig(
        customer_id="trackwick-tenant",
        tenant_id="fortune-paddy",
        api_key_reference="env://FFL_TRACKWICK_API_KEY",
        severity_form_key="Issue severity",
    )
    normalised = normalise_trackwick(
        TrackwickFetchResult(tasks=(task,), attendance=(), task_pages=1),
        config,
        as_of=datetime.fromisoformat("2026-08-03T10:00:00+05:30"),
    )

    issue_values = [record.values for record in normalised.records if record.feed == "issue_observations"]

    assert issue_values
    assert {record["severity"] for record in issue_values} == {"high"}


def test_trackwick_uses_only_the_leading_opaque_code_when_older_tasks_omit_customer_iden():
    task = dict(TASK)
    task.pop("customerIden")
    task["customerName"] = "FC-01734 (GAJENDRA SINGH)"

    normalised = normalise_trackwick(
        TrackwickFetchResult(tasks=(task,), attendance=(), task_pages=1),
        CONFIG,
        as_of=datetime.fromisoformat("2026-08-03T10:00:00+05:30"),
    )

    farmer_task = next(record for record in normalised.records if record.feed == "farmer_tasks")
    assert normalised.quarantined_rows == 0
    assert farmer_task.values["farmer_code"] == "FC-01734"
    assert "GAJENDRA" not in repr(normalised.records)


def test_trackwick_never_uses_a_name_without_an_opaque_customer_code():
    task = dict(TASK)
    task.pop("customerIden")
    task["customerName"] = "Gajendra Singh"

    normalised = normalise_trackwick(
        TrackwickFetchResult(tasks=(task,), attendance=(), task_pages=1),
        CONFIG,
        as_of=datetime.fromisoformat("2026-08-03T10:00:00+05:30"),
    )

    assert normalised.records == ()
    assert normalised.quarantined_rows == 1


def test_trackwick_rejects_an_unsafe_configured_severity_form_key():
    with pytest.raises(ValueError, match="SEVERITY_FORM_KEY"):
        TrackwickApiConfig.from_environment({
            "FFL_TRACKWICK_ENABLED": "true",
            "FFL_TRACKWICK_CUSTOMER_ID": "trackwick-tenant",
            "FFL_TRACKWICK_SEVERITY_FORM_KEY": "unsafe\nvalue",
        })


def test_trackwick_reads_only_an_explicit_safe_task_plot_reference_form_key():
    config = TrackwickApiConfig.from_environment({
        "FFL_TRACKWICK_ENABLED": "true",
        "FFL_TRACKWICK_CUSTOMER_ID": "trackwick-tenant",
        "FFL_TRACKWICK_TASK_PLOT_REFERENCE_FORM_KEY": "Gata reference",
    })

    assert config is not None
    assert config.task_plot_reference_form_key == "Gata reference"
    with pytest.raises(ValueError, match="TASK_PLOT_REFERENCE_FORM_KEY"):
        TrackwickApiConfig.from_environment({
            "FFL_TRACKWICK_ENABLED": "true",
            "FFL_TRACKWICK_CUSTOMER_ID": "trackwick-tenant",
            "FFL_TRACKWICK_TASK_PLOT_REFERENCE_FORM_KEY": "unsafe\nvalue",
        })


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


def test_delta_refresh_resolves_only_an_explicit_unique_task_plot_reference(
    ffl_db, owner
):
    config = TrackwickApiConfig(
        customer_id="trackwick-tenant",
        tenant_id="fortune-paddy",
        api_key_reference="env://FFL_TRACKWICK_API_KEY",
        task_plot_reference_form_key="Gata reference",
    )
    registration = {
        **REGISTRATION_TASK,
        "formDetails": {
            **REGISTRATION_TASK["formDetails"],
            "Number of Plots": "1",
            "Plot Details": [{
                "Gata No.": "Gata-123",
                "Plot Size (Bigha)": "2.5",
                "Plot Type": "Irrigated",
                "Village": "Dargava",
            }],
        },
    }
    visit = {
        **TASK,
        "formDetails": {**TASK["formDetails"], "Gata reference": "Gata-123"},
    }

    first = refresh_live_trackwick(
        ffl_db,
        owner.id,
        config=config,
        credential_resolver=lambda _: "runtime-key",
        transport=TaskPayloadTransport([registration]),
        as_of=datetime.fromisoformat("2026-08-03T10:00:00+05:30"),
    )
    assert first.state == "succeeded"
    assert ffl_db.execute(
        "SELECT COUNT(*) FROM trackwick_task_plot_links"
    ).fetchone()[0] == 0

    second = refresh_live_trackwick(
        ffl_db,
        owner.id,
        config=config,
        credential_resolver=lambda _: "runtime-key",
        transport=TaskPayloadTransport([visit]),
        as_of=datetime.fromisoformat("2026-08-04T10:00:00+05:30"),
    )

    assert second.state == "succeeded"
    association = ffl_db.execute(
        """SELECT association.association_kind, association.data_quality_status,
                  task.provider_task_id, task.provider_plot_reference,
                  plot.gata_number
           FROM trackwick_task_plot_links AS association
           JOIN trackwick_tasks AS task ON task.id = association.task_id
           JOIN trackwick_registration_plots AS plot ON plot.id = association.plot_id"""
    ).fetchone()
    assert dict(association) == {
        "association_kind": "source_explicit",
        "data_quality_status": "valid",
        "provider_task_id": "task-1",
        "provider_plot_reference": "Gata-123",
        "gata_number": "Gata-123",
    }

    changed_visit = {
        **visit,
        "formDetails": {**visit["formDetails"], "Gata reference": "Gata-999"},
    }
    third = refresh_live_trackwick(
        ffl_db,
        owner.id,
        config=config,
        credential_resolver=lambda _: "runtime-key",
        transport=TaskPayloadTransport([changed_visit]),
        as_of=datetime.fromisoformat("2026-08-05T10:00:00+05:30"),
    )
    stale_association = ffl_db.execute(
        """SELECT association.data_quality_status, task.provider_plot_reference
           FROM trackwick_task_plot_links AS association
           JOIN trackwick_tasks AS task ON task.id = association.task_id"""
    ).fetchone()

    assert third.state == "succeeded"
    assert dict(stale_association) == {
        "data_quality_status": "quarantined",
        "provider_plot_reference": "Gata-999",
    }


def test_refresh_refuses_to_guess_when_a_task_plot_reference_is_ambiguous(
    ffl_db, owner
):
    config = TrackwickApiConfig(
        customer_id="trackwick-tenant",
        tenant_id="fortune-paddy",
        api_key_reference="env://FFL_TRACKWICK_API_KEY",
        task_plot_reference_form_key="Gata reference",
    )
    registration = {
        **REGISTRATION_TASK,
        "formDetails": {
            **REGISTRATION_TASK["formDetails"],
            "Number of Plots": "2",
            "Plot Details": [
                {
                    "Gata No.": "Gata-123",
                    "Plot Size (Bigha)": "2.5",
                    "Plot Type": "Irrigated",
                    "Village": "Dargava",
                },
                {
                    "Gata No.": " gata-123 ",
                    "Plot Size (Bigha)": "1.5",
                    "Plot Type": "Irrigated",
                    "Village": "Dargava",
                },
            ],
        },
    }
    visit = {
        **TASK,
        "formDetails": {**TASK["formDetails"], "Gata reference": "GATA-123"},
    }

    refresh_live_trackwick(
        ffl_db,
        owner.id,
        config=config,
        credential_resolver=lambda _: "runtime-key",
        transport=TaskPayloadTransport([registration]),
        as_of=datetime.fromisoformat("2026-08-03T10:00:00+05:30"),
    )
    result = refresh_live_trackwick(
        ffl_db,
        owner.id,
        config=config,
        credential_resolver=lambda _: "runtime-key",
        transport=TaskPayloadTransport([visit]),
        as_of=datetime.fromisoformat("2026-08-04T10:00:00+05:30"),
    )

    assert result.state == "succeeded"
    assert ffl_db.execute(
        """SELECT COUNT(*) FROM trackwick_task_plot_links
           WHERE data_quality_status = 'valid'"""
    ).fetchone()[0] == 0


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


def test_trackwick_refresh_upserts_the_private_typed_evidence_graph(ffl_db, owner):
    as_of = datetime.fromisoformat("2026-08-03T10:00:00+05:30")
    first = refresh_live_trackwick(
        ffl_db, owner.id, config=CONFIG, credential_resolver=lambda _: "runtime-key",
        transport=RecordingTransport(), as_of=as_of,
    )

    tables = (
        "trackwick_parties", "trackwick_contact_points", "trackwick_tasks",
        "trackwick_visits", "trackwick_visit_findings", "trackwick_crop_inputs",
        "trackwick_location_observations", "trackwick_worker_days",
    )
    before = {
        table: ffl_db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
        for table in tables
    }
    task = ffl_db.execute(
        "SELECT task_status, farmer_party_id, field_worker_party_id FROM trackwick_tasks"
    ).fetchone()
    location_kinds = {
        row[0] for row in ffl_db.execute(
            "SELECT location_kind FROM trackwick_location_observations"
        ).fetchall()
    }

    replay = refresh_live_trackwick(
        ffl_db, owner.id, config=CONFIG, credential_resolver=lambda _: "runtime-key",
        transport=RecordingTransport(), as_of=as_of,
    )
    after = {
        table: ffl_db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
        for table in tables
    }

    assert first.state == replay.state == "succeeded"
    assert before == after
    assert before == {
        "trackwick_parties": 2,
        "trackwick_contact_points": 1,
        "trackwick_tasks": 1,
        "trackwick_visits": 1,
        "trackwick_visit_findings": 1,
        "trackwick_crop_inputs": 2,
        "trackwick_location_observations": 2,
        "trackwick_worker_days": 1,
    }
    assert task["task_status"] == "completed"
    assert task["farmer_party_id"] and task["field_worker_party_id"]
    assert location_kinds == {"crm", "task_completion"}


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


def test_trackwick_refresh_repairs_an_orphaned_private_history_before_using_delta(ffl_db, owner):
    as_of = datetime.fromisoformat("2026-08-03T10:00:00+05:30")
    refresh_live_trackwick(
        ffl_db, owner.id, config=CONFIG, credential_resolver=lambda _: "runtime-key",
        transport=RecordingTransport(), as_of=as_of,
    )
    # Mirror a cache written before its typed parent table existed.  The source
    # evidence remains, but a delta request cannot repair an old missing task.
    ffl_db.commit()
    ffl_db.execute("PRAGMA foreign_keys = OFF")
    ffl_db.execute("DELETE FROM trackwick_tasks")
    ffl_db.commit()
    ffl_db.execute("PRAGMA foreign_keys = ON")

    repair_transport = RecordingTransport()
    result = refresh_live_trackwick(
        ffl_db, owner.id, config=CONFIG, credential_resolver=lambda _: "runtime-key",
        transport=repair_transport, as_of=as_of,
    )

    assert result.state == "succeeded"
    assert "createDateBegin" not in repair_transport.requests[0].url.params
    assert ffl_db.execute("SELECT count(*) AS n FROM trackwick_tasks").fetchone()["n"] == 1


def test_trackwick_refresh_without_configuration_never_calls_provider(ffl_db, owner):
    result = refresh_live_trackwick(ffl_db, owner.id, config=None, credential_resolver=lambda _: "unused")

    assert result.state == "unavailable"
    assert result.reason_code == "configuration_unavailable"


def test_trackwick_refresh_requires_an_accountable_operations_owner(ffl_db):
    grower = repository.create_person(ffl_db, "Grower", "grower")

    with pytest.raises(ValueError, match="authorised Fortune operations lead"):
        refresh_live_trackwick(ffl_db, grower.id, config=CONFIG, credential_resolver=lambda _: "unused")


def test_trackwick_refresh_records_a_safe_persistence_failure_class(
    ffl_db, owner, monkeypatch
):
    def fail_private_evidence(*_args, **_kwargs):
        raise RuntimeError("provider data must never be logged here")

    monkeypatch.setattr(
        repository, "upsert_trackwick_private_records", fail_private_evidence
    )

    result = refresh_live_trackwick(
        ffl_db,
        owner.id,
        config=CONFIG,
        credential_resolver=lambda _: "runtime-key",
        transport=RecordingTransport(),
        as_of=datetime.fromisoformat("2026-08-03T10:00:00+05:30"),
    )

    assert result.state == "failed"
    assert result.reason_code == "persistence_runtimeerror"
    assert result.source_run.error_summary == "persistence_runtimeerror"
