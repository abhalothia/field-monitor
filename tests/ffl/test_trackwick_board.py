from __future__ import annotations

from datetime import datetime

from ffl.integrations.trackolap.trackwick import (
    PRIVATE_EVIDENCE_MAPPING_VERSION,
    TrackwickApiConfig,
    TrackwickFetchResult,
    normalise_trackwick_private_evidence,
)
from ffl.persistence import repository
from ffl.services.trackwick_board import manager_board_for_source


def test_manager_board_turns_private_trackwick_evidence_into_safe_operating_primitives(ffl_db, owner):
    source = repository.create_source_registry(
        ffl_db,
        source_key="trackwick-fortune-paddy",
        display_name="Fortune paddy visits (TrackWick)",
        source_type="trackwick",
        purpose="Fortune operating context",
        authority_level="partner",
        owner_id=owner.id,
        permitted_data_classes=["farm_candidate_context"],
        schema_version="trackwick-v3",
        mapping_version="trackwick-live-v4",
        default_coverage={},
        enabled=True,
    )
    run = repository.create_source_run(
        ffl_db,
        source.id,
        coverage={"input": "test"},
        mapping_version="trackwick-live-v4",
        status="succeeded",
        fetched_at="2026-08-03T10:00:00+05:30",
    )
    config = TrackwickApiConfig(
        customer_id="fortune-tenant",
        tenant_id="fortune-paddy",
        api_key_reference="env://FFL_TRACKWICK_API_KEY",
    )
    fetched = TrackwickFetchResult(
        tasks=(
            {
                "id": "registration-1",
                "type": "New Farmer Registration",
                "status": "Completed",
                "customerIden": "farmer-1",
                "customerName": "Ramesh Kumar",
                "employeeIden": "worker-1",
                "assignedTo": "Sanjay Singh",
                "completed": 1785751200000,
                "formDetails": {
                    "Village": "Dargava",
                    "Block": "Gabhana",
                    "District": "Aligarh",
                    "Total Acre": "5.5",
                    "Number of Plots": "2",
                    "P.B-1 Acre": "3",
                    "1718 Acre": "2.5",
                    "Geo": {"lat": 27.95, "lng": 78.27},
                    "Aadhar No": "111122223333",
                },
            },
            {
                "id": "visit-1",
                "type": "Farmer Visit",
                "status": "In Progress",
                "customerIden": "farmer-1",
                "customerName": "Ramesh Kumar",
                "employeeIden": "worker-1",
                "assignedTo": "Sanjay Singh",
                "created": 1785750000000,
                "completeGeo": {"lat": 27.951, "lng": 78.271},
                "formDetails": {"क्या किसान ने किट ले ली है?": "Yes"},
            },
        ),
        customers=(
            {
                "iden": "farmer-1",
                "name": "Ramesh Kumar",
                "mobile": "9999999999",
                "geo": {"lat": 27.95, "lng": 78.27},
                "owner": "worker-1",
                "status": "ACTIVE",
                "tag": "PB1",
                "createdOn": 1785750000000,
            },
        ),
        attendance=(
            {
                "id": "attendance-1",
                "empId": "worker-1",
                "name": "Sanjay Singh",
                "date": "2026-08-03",
                "startTime": "09:00",
            },
        ),
        task_pages=1,
        customer_pages=1,
    )
    evidence = normalise_trackwick_private_evidence(
        fetched,
        config,
        as_of=datetime.fromisoformat("2026-08-03T10:00:00+05:30"),
    )
    repository.upsert_trackwick_private_records(
        ffl_db,
        source.id,
        run.id,
        evidence.records,
        PRIVATE_EVIDENCE_MAPPING_VERSION,
        observed_at="2026-08-03T10:00:00+05:30",
    )

    board = manager_board_for_source(ffl_db, source_key=source.source_key)
    serialized = repr(board)

    assert board["counts"] == {
        "farmers": 1,
        "farm_candidates": 1,
        "field_workers": 1,
        "open_work": 1,
        "source_points": 3,
        "crop_photo_references": 0,
        "plot_photo_references": 0,
    }
    assert board["farms"] == [{
        "id": board["farms"][0]["id"],
        "farmer_name": "Ramesh Kumar",
        "place": "Dargava · Gabhana · Aligarh",
        "registration_status": "completed",
        "reported_area_acres": 5.5,
        "reported_plot_count": 2,
        "pb1_area_acres": 3.0,
        "var1718_area_acres": 2.5,
        "open_work": 1,
        "latest_activity_at": "2026-08-03T15:30:00+05:30",
        "location": {
            "latitude": 27.95,
            "longitude": 78.27,
            "kind": "registration",
            "confidence": "declared",
            "observed_at": "2026-08-03T15:30:00+05:30",
        },
        "plot_photo_references": 0,
        "crop_photo_references": 0,
        "record_kind": "reported_farm_candidate",
    }]
    assert board["farmers"][0]["name"] == "Ramesh Kumar"
    assert board["field_workers"][0]["name"] == "Sanjay Singh"
    assert board["inbox"][0]["task_type"] == "Farmer Visit"
    assert board["map"]["points"][0]["record_kind"] == "source_point"
    assert board["map"]["points"][0]["is_boundary"] is False
    assert "9999999999" not in serialized
    assert "111122223333" not in serialized
    assert "provider_identifier" not in serialized
    assert "remote_url" not in serialized


def test_manager_board_is_empty_and_honest_before_a_trackwick_source_exists(ffl_db):
    board = manager_board_for_source(ffl_db, source_key="trackwick-fortune-paddy")

    assert board["source"] == {"state": "not_configured", "last_synced_at": None}
    assert board["counts"]["farmers"] == 0
    assert board["farms"] == []
    assert board["map"]["points"] == []


def test_source_registry_uses_a_boolean_enabled_value(ffl_db, owner):
    source = repository.create_source_registry(
        ffl_db,
        source_key="trackwick-boolean-enabled",
        display_name="TrackWick",
        source_type="trackwick",
        purpose="Test source",
        authority_level="partner",
        owner_id=owner.id,
        permitted_data_classes=[],
        schema_version="v1",
        mapping_version="v1",
        default_coverage={},
        enabled=True,
    )

    assert source.enabled is True
