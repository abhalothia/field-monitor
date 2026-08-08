from __future__ import annotations

from datetime import datetime

from ffl.integrations.trackolap.trackwick import (
    PRIVATE_EVIDENCE_MAPPING_VERSION,
    TrackwickApiConfig,
    TrackwickFetchResult,
    normalise_trackwick_basics,
    normalise_trackwick_private_evidence,
)
from ffl.persistence import repository
from ffl.services.operating_enrichment import (
    place_summaries_for_source,
    refresh_source_snapshots,
)
from ffl.services.trackwick_board import command_centre_board_for_source, manager_board_for_source


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
    basics = normalise_trackwick_basics(
        fetched, config, as_of=datetime.fromisoformat("2026-08-03T10:00:00+05:30"),
    )
    repository.create_trackolap_records(
        ffl_db, source.id, run.id, None,
        [
            (record.feed, record.source_id, record.source_updated_at, record.tenant_id, dict(record.values))
            for record in basics.records
        ],
        status="published",
    )
    visit_task = ffl_db.execute(
        "SELECT id FROM trackwick_tasks WHERE source_id = ? AND provider_task_id = 'visit-1'",
        (source.id,),
    ).fetchone()
    ffl_db.execute(
        """INSERT INTO trackwick_visits (
            task_id, source_id, observed_at, kit_status, source_fingerprint, mapping_version,
            data_quality_status, first_seen_at, last_seen_at, created_at
        ) VALUES (?, ?, ?, 'unknown', ?, ?, 'valid', ?, ?, ?)""",
        (
            visit_task["id"], source.id, "2026-08-03T15:30:00+05:30", "b" * 64,
            PRIVATE_EVIDENCE_MAPPING_VERSION, "2026-08-03T15:30:00+05:30",
            "2026-08-03T15:30:00+05:30", "2026-08-03T15:30:00+05:30",
        ),
    )
    ffl_db.execute(
        """INSERT INTO trackwick_visit_findings (
            id, visit_task_id, source_id, finding_kind, reported_value, source_field,
            declared_severity, observed_at, source_fingerprint, mapping_version,
            data_quality_status, first_seen_at, last_seen_at, created_at
        ) VALUES ('finding-1', ?, ?, 'disease', 'PRIVATE DISEASE VALUE 7731',
                  'private source field', 'high', ?, ?, ?, 'valid', ?, ?, ?)""",
        (
            visit_task["id"], source.id, "2026-08-03T15:30:00+05:30", "a" * 64,
            PRIVATE_EVIDENCE_MAPPING_VERSION, "2026-08-03T15:30:00+05:30",
            "2026-08-03T15:30:00+05:30", "2026-08-03T15:30:00+05:30",
        ),
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
        "reported_visits": 1,
        "reported_input_events": 0,
        "reported_signals": 1,
        "geotagged_evidence": 3,
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

    safe_board = command_centre_board_for_source(ffl_db, source_key=source.source_key)
    safe_serialized = repr(safe_board).lower()
    assert set(safe_board) == {
        "source", "counts", "farms", "farmers", "field_workers", "signals", "inbox", "map", "limitations",
    }
    assert set(safe_board["farms"][0]) == {
        "id", "farmer_name", "place", "reported_area_acres", "reported_plot_count",
        "open_work", "latest_activity_at", "plot_photo_references", "crop_photo_references",
    }
    assert set(safe_board["farmers"][0]) == {
        "id", "name", "farm_candidates", "reported_area_acres", "open_work",
        "latest_activity_at", "crop_photo_references",
    }
    assert safe_board["field_workers"] == [{
        "id": board["field_workers"][0]["id"],
        "name": "Sanjay Singh",
        "reported_farmer_reach": 1,
        "open_work": 1,
        "completed_work": 1,
        "latest_activity_at": "2026-08-03T15:30:00+05:30",
        "latest_attendance_on": "2026-08-03",
    }]
    assert safe_board["counts"] == {
        "farmers": 1,
        "farm_candidates": 1,
        "field_workers": 1,
        "open_work": 1,
        "crop_photo_references": 0,
        "plot_photo_references": 0,
        "reported_visits": 1,
        "reported_input_events": 0,
        "reported_signals": 1,
        "geotagged_evidence": 3,
    }
    assert safe_board["signals"] == [{
        "id": "finding-1",
        "finding_kind": "disease",
        "declared_severity": "high",
        "observed_at": "2026-08-03T15:30:00+05:30",
        "farmer_name": "Ramesh Kumar",
    }]
    assert safe_board["inbox"][0]["label"] == "Field work"
    assert "task_type" not in safe_board["inbox"][0]
    assert "Farmer Visit" not in repr(safe_board)
    assert safe_board["map"]["points"][0]["subject"]["kind"] == "reported_farm"
    worker_visit_point = next(point for point in safe_board["map"]["points"] if point["subject"]["kind"] == "field_worker")
    assert worker_visit_point["has_disease"] is True
    assert worker_visit_point["related_farm"] == {
        "id": safe_board["farms"][0]["id"],
        "name": "Dargava · Gabhana · Aligarh",
        "place": "Dargava · Gabhana · Aligarh",
        "farmer_name": "Ramesh Kumar",
    }
    assert safe_board["map"]["places"] == []
    for forbidden in ("crm_status", "provider_tag", "registration_status", "pb1", "1718", "9999999999", "111122223333", "private disease value 7731", "private source field"):
        assert forbidden not in safe_serialized

    # The snapshot is a private read model: it adds only factual metrics and
    # derived tags to the already-safe board, never a raw source field.
    assert refresh_source_snapshots(
        ffl_db, source.id, source_run_id=run.id, refreshed_at="2026-08-04T10:00:00+05:30",
    ) == 3
    enriched_board = command_centre_board_for_source(ffl_db, source_key=source.source_key)
    farmer_snapshot = enriched_board["farmers"][0]["operating"]
    worker_snapshot = enriched_board["field_workers"][0]["operating"]
    farm_snapshot = enriched_board["farms"][0]["operating"]
    assert farmer_snapshot["metrics"]["open_task_count"] == 1
    assert farmer_snapshot["metrics"]["disease_report_count"] == 1
    assert worker_snapshot["metrics"]["farmer_count"] == 1
    assert farm_snapshot["metrics"]["reported_area_acres"] == 5.5
    assert farm_snapshot["categories"]["crop_profile"] == "mixed"
    assert farm_snapshot["categories"]["linked_place_count"] == 1
    assert farm_snapshot["categories"]["latest_activity_kind"] == "location"
    assert farm_snapshot["categories"]["coverage"] == {
        "location_recorded": True,
        "photo_recorded": False,
        "visit_recorded": False,
        "issue_recorded": False,
        "area_recorded": True,
        "crop_recorded": True,
    }
    assert farm_snapshot["categories"]["workload"] == "no_open_tasks"
    assert farmer_snapshot["categories"]["linked_place_count"] == 1
    assert worker_snapshot["categories"]["linked_place_count"] == 1
    assert "needs_attention" in {tag["key"] for tag in farmer_snapshot["tags"]}
    assert "crop_mixed" in {tag["key"] for tag in farm_snapshot["tags"]}
    assert ffl_db.execute(
        "SELECT COUNT(*) FROM place_catalog WHERE source_id = ?", (source.id,)
    ).fetchone()[0] == 1
    taxonomy = {
        row["task_type_key"]: row["task_kind"]
        for row in ffl_db.execute(
            "SELECT task_type_key, task_kind FROM task_type_taxonomy WHERE source_id = ?",
            (source.id,),
        ).fetchall()
    }
    assert taxonomy == {
        "farmer-visit": "visit",
        "new-farmer-registration": "registration",
    }
    place_summaries = place_summaries_for_source(ffl_db, source.id)
    assert place_summaries == [{
        "id": "dargava|gabhana|aligarh",
        "place": "Dargava · Gabhana · Aligarh",
        "metrics": {
            "reported_farm_count": 1,
            "farmer_count": 1,
            "field_worker_count": 1,
            "open_task_count": 1,
            "visit_count": 0,
            "issue_report_count": 0,
            "location_evidence_count": 1,
            "photo_reference_count": 0,
            "latest_activity_at": "2026-08-03T15:30:00+05:30",
            "refreshed_at": "2026-08-04T10:00:00+05:30",
        },
    }]
    assert enriched_board["map"]["places"] == place_summaries
    assert "PRIVATE DISEASE VALUE 7731" not in repr(enriched_board)

    # Production's populated source cache can predate the typed task table.
    # Published normalized follow-ups keep the browser board useful and safe.
    ffl_db.commit()
    ffl_db.execute("PRAGMA foreign_keys = OFF")
    ffl_db.execute("DROP TABLE trackwick_tasks")
    fallback_board = command_centre_board_for_source(ffl_db, source_key=source.source_key)

    assert fallback_board["counts"]["farm_candidates"] == 1
    assert fallback_board["counts"]["open_work"] == 1
    assert fallback_board["inbox"][0]["label"] == "Field work"
    assert "Farmer Visit" not in repr(fallback_board)


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
