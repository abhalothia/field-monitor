from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ffl.app import create_app
from ffl.persistence import repository
from ffl.services import farm_profiles


class _ColumnGrantConnection:
    """Exercise profile SQL under the two Task 5 column grants."""

    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, params=()):
        if "count(*)" in " ".join(sql.split()).lower():
            raise PermissionError("aggregate must reference a granted work_items column")
        return self.connection.execute(sql, params)


@pytest.fixture
def populated_trackwick_source(ffl_db, owner):
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
    ffl_db.execute(
        """INSERT INTO trackwick_parties (
            id, source_id, party_kind, provider_identifier, display_name, crm_status,
            provider_tag, source_fingerprint, mapping_version, data_quality_status,
            first_seen_at, last_seen_at, created_at
        ) VALUES (?, ?, 'farmer', ?, ?, 'active', 'PB1', ?, ?, 'valid', ?, ?, ?)""",
        (
            "reported-farmer-1", source.id, "provider-farmer-1", "Ramesh Kumar",
            "a" * 64, "trackwick-live-v4", "2026-08-03T10:00:00+05:30",
            "2026-08-03T10:00:00+05:30", "2026-08-03T10:00:00+05:30",
        ),
    )
    ffl_db.execute(
        """INSERT INTO trackwick_contact_points (
            id, party_id, source_id, contact_kind, contact_value, value_fingerprint,
            consent_status, source_fingerprint, mapping_version, data_quality_status,
            first_seen_at, last_seen_at, created_at
        ) VALUES (?, ?, ?, 'mobile', ?, ?, 'unknown', ?, ?, 'valid', ?, ?, ?)""",
        (
            "private-contact-1", "reported-farmer-1", source.id, "9999999999", "b" * 64,
            "c" * 64, "trackwick-live-v4", "2026-08-03T10:00:00+05:30",
            "2026-08-03T10:00:00+05:30", "2026-08-03T10:00:00+05:30",
        ),
    )
    ffl_db.execute(
        """INSERT INTO trackwick_parties (
            id, source_id, party_kind, provider_identifier, display_name,
            source_fingerprint, mapping_version, data_quality_status,
            first_seen_at, last_seen_at, created_at
        ) VALUES (?, ?, 'field_worker', ?, ?, ?, ?, 'valid', ?, ?, ?)""",
        (
            "reported-worker-1", source.id, "provider-worker-1", "Sanjay Singh",
            "e" * 64, "trackwick-live-v4", "2026-08-03T10:00:00+05:30",
            "2026-08-03T10:00:00+05:30", "2026-08-03T10:00:00+05:30",
        ),
    )
    ffl_db.execute(
        """INSERT INTO trackwick_tasks (
            id, source_id, provider_task_id, farmer_party_id, field_worker_party_id,
            task_type, task_status, provider_created_at, source_fingerprint,
            mapping_version, data_quality_status, first_seen_at, last_seen_at, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'in_progress', ?, ?, ?, 'valid', ?, ?, ?)""",
        (
            "reported-worker-task-1", source.id, "provider-worker-task-1", "reported-farmer-1",
            "reported-worker-1", "private worker task", "2026-08-04T10:00:00+05:30",
            "f" * 64, "trackwick-live-v4", "2026-08-04T10:00:00+05:30",
            "2026-08-04T10:00:00+05:30", "2026-08-04T10:00:00+05:30",
        ),
    )
    ffl_db.execute(
        """INSERT INTO trackwick_worker_days (
            id, source_id, field_worker_party_id, observed_on, attendance_status,
            source_fingerprint, mapping_version, data_quality_status,
            first_seen_at, last_seen_at, created_at
        ) VALUES (?, ?, ?, '2026-08-04', 'present', ?, ?, 'valid', ?, ?, ?)""",
        (
            "reported-worker-day-1", source.id, "reported-worker-1", "1" * 64,
            "trackwick-live-v4", "2026-08-04T10:00:00+05:30",
            "2026-08-04T10:00:00+05:30", "2026-08-04T10:00:00+05:30",
        ),
    )
    ffl_db.execute(
        """INSERT INTO trackwick_location_observations (
            id, source_id, party_id, provider_location_key, location_kind, location_confidence, latitude, longitude,
            observed_at, source_fingerprint, mapping_version, data_quality_status,
            first_seen_at, last_seen_at, created_at
        ) VALUES (?, ?, ?, ?, 'crm', 'declared', 27.95, 78.27, ?, ?, ?, 'valid', ?, ?, ?)""",
        (
            "private-location-1", source.id, "reported-farmer-1", "provider-location-1", "2026-08-03T10:00:00+05:30",
            "d" * 64, "trackwick-live-v4", "2026-08-03T10:00:00+05:30",
            "2026-08-03T10:00:00+05:30", "2026-08-03T10:00:00+05:30",
        ),
    )
    ffl_db.commit()
    return {"farmer_id": "reported-farmer-1", "worker_id": "reported-worker-1"}


@pytest.fixture
def farm(ffl_db, users, crop_allocation):
    result = repository.create_farm(
        ffl_db, crop_allocation.operating_unit_id, "FFL Pilot", users.manager.id,
    )
    repository.assign_field_to_farm(
        ffl_db, result.id, crop_allocation.operational_block_id, "2026-06-01", users.manager.id,
    )
    return result


@pytest.fixture
def worker(ffl_db, users, farm, crop_allocation):
    result = repository.create_person(ffl_db, "Nisha Field Worker", "field_operator")
    repository.create_person_operating_relationship(
        ffl_db, result.id, "crop_allocation", crop_allocation.id, "field_operator",
        "2026-06-02", reviewed_by_person_id=users.manager.id,
    )
    return result


def test_farm_record_has_four_sections_and_labels_reported_events(ffl_db, farm):
    record = farm_profiles.farm_record(ffl_db, farm.id)

    assert set(record) == {
        "state", "kind", "id", "name", "now", "people", "updates", "context", "limitations",
    }
    assert record["kind"] == "farm"
    assert all(item["state"] in {"reviewed", "reported"} for item in record["updates"])
    assert record["context"] == {
        "state": "not_attributed",
        "message": "Historical purchase cohorts are not attributed to this farm.",
    }
    assert "contact_value" not in repr(record)
    assert "provider_identifier" not in repr(record)
    assert "longitude" not in repr(record)


def test_farm_directory_activity_filters_and_orders_are_deterministic():
    now = datetime.now(timezone.utc)
    items = [
        {"id": "older", "name": "Older Farm", "open_work_count": 4, "latest_update_at": (now - timedelta(days=31)).isoformat()},
        {"id": "current", "name": "Current Farm", "open_work_count": 1, "latest_update_at": (now - timedelta(hours=1)).isoformat()},
        {"id": "missing", "name": "Missing Farm", "open_work_count": 0, "latest_update_at": None},
    ]

    assert [item["id"] for item in farm_profiles._filter_and_order_farm_directory(items, set(), "open_tasks")] == ["older", "current", "missing"]
    assert [item["id"] for item in farm_profiles._filter_and_order_farm_directory(items, set(), "recently_updated")] == ["current", "older", "missing"]
    assert [item["id"] for item in farm_profiles._filter_and_order_farm_directory(items, {"updated_week"}, "name")] == ["current"]
    assert [item["id"] for item in farm_profiles._filter_and_order_farm_directory(items, {"no_recent_update"}, "name")] == ["missing", "older"]


def test_field_worker_context_lists_safe_assignments(ffl_db, worker):
    profile = farm_profiles.person_context(ffl_db, worker.id, "field_worker")

    assert profile["kind"] == "field_worker"
    assert profile["name"] == "Nisha Field Worker"
    assert all(set(row) == {
        "farm_id", "farm_name", "field_id", "field_name", "role", "starts_on",
    } for row in profile["assignments"])
    assert profile["assignments"][0]["role"] == "field_operator"
    with pytest.raises(ValueError, match="kind must be farmer or field_worker"):
        farm_profiles.person_context(ffl_db, worker.id, "grower")


def test_farm_and_field_people_do_not_promote_unit_or_parcel_relationships(
    ffl_db, users, farm, crop_allocation,
):
    parcel = repository.create_land_parcel(
        ffl_db, crop_allocation.operating_unit_id, "North Parcel", 5.0,
    )
    repository.link_block_parcel(ffl_db, crop_allocation.operational_block_id, parcel.id)
    unit_worker = repository.create_person(ffl_db, "Unit Worker", "field_operator")
    parcel_farmer = repository.create_person(ffl_db, "Parcel Farmer", "grower")
    repository.create_person_operating_relationship(
        ffl_db, unit_worker.id, "operating_unit", crop_allocation.operating_unit_id,
        "field_operator", "2026-06-01", reviewed_by_person_id=users.manager.id,
    )
    repository.create_person_operating_relationship(
        ffl_db, parcel_farmer.id, "land_parcel", parcel.id, "grower", "2026-06-01",
        reviewed_by_person_id=users.manager.id,
    )

    farm_people = farm_profiles.farm_record(ffl_db, farm.id)["people"]
    field_people = farm_profiles.field_record(
        ffl_db, crop_allocation.operational_block_id,
    )["people"]

    assert unit_worker.id not in {person["id"] for person in farm_people}
    assert parcel_farmer.id not in {person["id"] for person in farm_people}
    assert unit_worker.id not in {person["id"] for person in field_people}
    assert parcel_farmer.id not in {person["id"] for person in field_people}
    assert farm_profiles.person_context(ffl_db, unit_worker.id, "field_worker") is None
    assert farm_profiles.person_context(ffl_db, parcel_farmer.id, "farmer") is None


def test_field_record_has_reviewed_geometry_state_and_crop_seasons(
    ffl_db, farm, crop_allocation,
):
    record = farm_profiles.field_record(ffl_db, crop_allocation.operational_block_id)

    assert record["state"] == "reviewed"
    assert record["kind"] == "field"
    assert record["farm"] == {"id": farm.id, "name": farm.name}
    assert record["geometry"] == {
        "state": "boundary_evidence_required",
        "message": "A reviewed field boundary is required before this Field can appear on a map.",
    }
    assert record["allocations"] == [{
        "id": crop_allocation.id,
        "season_id": crop_allocation.season_id,
        "season_name": "Kharif 2026",
        "crop_name": "Rice",
        "cultivar": "Pusa 1121",
        "area_hectares": 5.0,
        "status": "active",
        "starts_on": "2026-06-01",
        "ends_on": "2026-11-30",
    }]


def test_farm_updates_are_parsed_ordered_bounded_and_keep_canonical_details_private(
    ffl_db, users, farm, crop_allocation,
):
    template = repository.create_signal_template(
        ffl_db, "Bounded observation", 1, "published", "[]", users.lead.id,
        "2026-08-01T00:00:00+00:00",
    )
    for index in range(31):
        repository.create_field_signal(
            ffl_db, crop_allocation.id, template.id, 1,
            "2026-08-{0:02d}T09:00:00+05:30".format(index % 28 + 1),
            users.operator.id, {"raw_private_value": "never return this"},
        )
    repository.create_field_signal(
        ffl_db, crop_allocation.id, template.id, 1,
        "2026-08-03T04:00:00+00:00", users.operator.id, {},
    )

    updates = farm_profiles.farm_record(ffl_db, farm.id)["updates"]

    assert len(updates) == 30
    assert updates[0]["occurred_at"] == "2026-08-28T09:00:00+05:30"
    assert "never return this" not in repr(updates)
    instants = [farm_profiles._timestamp_instant(item["occurred_at"]) for item in updates]
    assert instants == sorted(instants, reverse=True)


def test_reported_updates_require_reviewed_allocation_link_and_redact_source_values(
    ffl_db, owner, users, farm, crop_allocation,
):
    source = repository.create_source_registry(
        ffl_db, "profile-trackwick", "Profile TrackWick", "trackwick", "reported context",
        "partner", owner.id, ["farm_candidate_context"], "v1", "v1", {}, enabled=True,
    )
    now = "2026-08-04T10:00:00+05:30"
    for task_id, link_status in (("reviewed-task", "reviewed"), ("proposed-task", "proposed")):
        ffl_db.execute(
            """INSERT INTO trackwick_tasks (
                id, source_id, provider_task_id, task_type, task_status,
                provider_completed_at, source_fingerprint, mapping_version,
                data_quality_status, first_seen_at, last_seen_at, created_at
            ) VALUES (?, ?, ?, ?, 'completed', ?, ?, 'v1', 'valid', ?, ?, ?)""",
            (
                task_id, source.id, "private-provider-" + task_id,
                "RAW SENTINEL TASK TYPE 8842", now, "a" * 64, now, now, now,
            ),
        )
        ffl_db.execute(
            """INSERT INTO trackwick_visits (
                task_id, source_id, observed_at, kit_status, source_fingerprint,
                mapping_version, data_quality_status, first_seen_at, last_seen_at, created_at
            ) VALUES (?, ?, ?, 'unknown', ?, 'v1', 'valid', ?, ?, ?)""",
            (task_id, source.id, now, "b" * 64, now, now, now),
        )
        ffl_db.execute(
            """INSERT INTO trackwick_visit_findings (
                id, visit_task_id, source_id, finding_kind, reported_value, source_field,
                declared_severity, observed_at, source_fingerprint, mapping_version,
                data_quality_status, first_seen_at, last_seen_at, created_at
            ) VALUES (?, ?, ?, 'disease', ?, ?, 'high', ?, ?, 'v1', 'valid', ?, ?, ?)""",
            (
                "finding-" + task_id, task_id, source.id, "raw-disease-value",
                "raw-source-field", now, "c" * 64, now, now, now,
            ),
        )
        ffl_db.execute(
            """INSERT INTO trackwick_task_allocation_links (
                id, task_id, crop_allocation_id, link_status, reviewed_by_person_id,
                reviewed_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                "allocation-link-" + task_id, task_id, crop_allocation.id, link_status,
                users.manager.id if link_status == "reviewed" else None,
                now if link_status == "reviewed" else None, now,
            ),
        )
    ffl_db.commit()
    # Match the current Fortune cache: reviewed links, visits, and findings can
    # exist even when the legacy typed task relation is not deployed.
    ffl_db.execute("PRAGMA foreign_keys = OFF")
    ffl_db.execute("DROP TABLE trackwick_tasks")

    updates = farm_profiles.farm_record(ffl_db, farm.id)["updates"]
    source_updates = [item for item in updates if item["state"] == "reported"]
    field_updates = farm_profiles.field_record(
        ffl_db, crop_allocation.operational_block_id,
    )["updates"]

    assert {item["kind"] for item in source_updates} == {
        "trackwick_task", "trackwick_visit", "disease_finding",
    }
    assert {item["id"] for item in source_updates} == {
        "reviewed-task", "visit-reviewed-task", "finding-reviewed-task",
    }
    assert all(item["state"] == "reported" for item in source_updates)
    finding = next(item for item in source_updates if item["kind"] == "disease_finding")
    assert finding["summary"] == "High disease finding reported"
    assert finding["finding_kind"] == "disease"
    assert finding["declared_severity"] == "high"
    serialized = repr(source_updates)
    assert "RAW SENTINEL TASK TYPE 8842" not in serialized
    assert "RAW SENTINEL TASK TYPE 8842" not in repr(field_updates)
    assert next(item for item in source_updates if item["kind"] == "trackwick_task")["summary"] == (
        "TrackWick task reported"
    )
    assert "raw-disease-value" not in serialized
    assert "raw-source-field" not in serialized
    assert "private-provider" not in serialized


@pytest.mark.parametrize("start,end", [
    ("2026-08-02", "2026-08-01"),
    ("not-a-date", "2026-08-01"),
    ("2025-01-01", "2026-08-02"),
])
def test_farm_record_rejects_invalid_date_window(ffl_db, start, end):
    with pytest.raises(ValueError):
        farm_profiles.farm_record(ffl_db, "missing", start, end)


def test_entity_directory_is_bounded_and_rejects_invalid_filters(ffl_db, farm):
    directory = farm_profiles.list_entity_directory(ffl_db, "farm", query="Pilot", limit=1)

    assert len(directory) == 1
    assert {key: directory[0][key] for key in ("state", "kind", "id", "name")} == {
        "state": "reviewed", "kind": "farm", "id": farm.id, "name": "FFL Pilot",
    }
    with pytest.raises(ValueError, match="query must be at most 80 characters"):
        farm_profiles.list_entity_directory(ffl_db, "farm", query="x" * 81)
    with pytest.raises(ValueError, match="limit must be between 1 and 100"):
        farm_profiles.list_entity_directory(ffl_db, "farm", limit=101)


def test_reported_directory_uses_source_registrations_without_promoting_farms(
    tmp_path,
):
    app = create_app(str(tmp_path / "source-only-directory.db"), manager_api_token="manager-secret")
    ffl_db = app.state.conn
    owner = repository.create_person(ffl_db, "Fortune COO", "operations_lead")
    app.state.manager_person_id = owner.id
    source = repository.create_source_registry(
        ffl_db, "trackwick-fortune-paddy", "TrackWick", "trackwick", "reported context",
        "partner", owner.id, ["farm_candidate_context"], "v1", "v1", {}, enabled=True,
    )
    now = "2026-08-03T10:00:00+05:30"
    ffl_db.execute(
        """INSERT INTO trackwick_parties (
            id, source_id, party_kind, provider_identifier, display_name,
            source_fingerprint, mapping_version, data_quality_status,
            first_seen_at, last_seen_at, created_at
        ) VALUES ('source-farmer', ?, 'farmer', 'provider-farmer', 'Ramesh Kumar',
                  ?, 'v1', 'valid', ?, ?, ?)""",
        (source.id, "a" * 64, now, now, now),
    )
    ffl_db.execute(
        """INSERT INTO trackwick_tasks (
            id, source_id, provider_task_id, farmer_party_id, task_type, task_status,
            provider_created_at, source_fingerprint, mapping_version, data_quality_status,
            first_seen_at, last_seen_at, created_at
        ) VALUES ('source-registration-task', ?, 'provider-task', 'source-farmer',
                  'RAW DIRECTORY SENTINEL 9217', 'completed', ?, ?, 'v1', 'valid', ?, ?, ?)""",
        (source.id, now, "b" * 64, now, now, now),
    )
    ffl_db.execute(
        """INSERT INTO trackwick_registrations (
            id, task_id, source_id, farmer_party_id, registration_status,
            village_name, block_name, district_name, reported_total_area_acres,
            reported_plot_count, source_fingerprint, mapping_version, data_quality_status,
            first_seen_at, last_seen_at, created_at
        ) VALUES ('source-registration', 'source-registration-task', ?, 'source-farmer',
                  'completed', 'Dargava', 'Gabhana', 'Aligarh', 5.5, 2,
                  ?, 'v1', 'valid', ?, ?, ?)""",
        (source.id, "c" * 64, now, now, now),
    )
    ffl_db.commit()
    ffl_db.execute("PRAGMA foreign_keys = OFF")
    ffl_db.execute("DROP TABLE trackwick_tasks")
    ffl_db.commit()

    before = ffl_db.execute("SELECT count(id) AS count FROM farms").fetchone()["count"]
    reported = farm_profiles.list_entity_directory(
        ffl_db, "farm", state="reported", query="Dargava",
    )
    all_states = farm_profiles.list_entity_directory(
        ffl_db, "farm", state="all", query="Dargava",
    )
    canonical = farm_profiles.list_entity_directory(ffl_db, "farm")
    after = ffl_db.execute("SELECT count(id) AS count FROM farms").fetchone()["count"]
    with TestClient(app) as client:
        headers = {"X-FFL-Manager-Token": "manager-secret"}
        reported_response = client.get(
            "/api/v1/farms?state=reported&query=Dargava", headers=headers,
        )
        canonical_response = client.get("/api/v1/farms", headers=headers)

    assert before == after == 0
    assert canonical == []
    assert reported == [{
        "state": "reported",
        "kind": "reported_farm_candidate",
        "id": "source-registration",
        "name": "Dargava · Gabhana · Aligarh",
        "reported_farmer_name": "Ramesh Kumar",
        "reported_area_acres": 5.5,
        "reported_plot_count": 2,
        "open_work_count": 0,
        "latest_update_at": now,
        "destination": {"kind": "review_reported_farm", "id": "source-registration"},
    }]
    assert all_states == reported
    assert reported_response.status_code == 200
    assert reported_response.json() == reported
    assert canonical_response.json() == []
    assert "RAW DIRECTORY SENTINEL 9217" not in repr(reported)


def test_farm_profile_returns_reviewed_truth_and_not_source_context(ffl_db, users, crop_allocation):
    grower = repository.create_person(ffl_db, "Asha Grower", "grower")
    repository.create_person_operating_relationship(
        ffl_db, grower.id, "crop_allocation", crop_allocation.id, "grower",
        "2026-06-01", provenance="reviewed contract", reviewed_by_person_id=users.manager.id,
    )

    profile = farm_profiles.farm_profile(ffl_db, crop_allocation.operational_block_id)

    assert profile["state"] == "reviewed"
    assert profile["kind"] == "farm"
    assert profile["compatibility"] == {
        "state": "noncanonical",
        "id_kind": "operational_block",
        "message": "Compatibility response: this id identifies a Field, not a canonical Farm.",
    }
    assert profile["current"] == {"crop_name": "Rice", "cultivar": "Pusa 1121"}
    assert profile["people"] == [{
        "id": grower.id, "name": "Asha Grower", "role": "grower", "starts_on": "2026-06-01",
    }]
    assert profile["location"] == {"state": "not_published"}
    assert "provenance" not in repr(profile)
    assert "source" not in repr(profile)


def test_reported_farmer_profile_is_safe_context_not_a_login(ffl_db, populated_trackwick_source):
    profile = farm_profiles.reported_farmer_profile(ffl_db, populated_trackwick_source["farmer_id"])

    assert profile["state"] == "reported"
    assert profile["kind"] == "farmer"
    assert profile["account"] == {"state": "not_created"}
    assert set(profile) == {"state", "kind", "id", "name", "reported", "account", "limitations"}
    serialized = repr(profile)
    assert "9999999999" not in serialized
    assert "latitude" not in serialized
    assert "remote_url" not in serialized


def test_reported_field_worker_profile_is_safe_context_not_an_assignment(
    ffl_db, populated_trackwick_source,
):
    profile = farm_profiles.reported_field_worker_profile(
        ffl_db, populated_trackwick_source["worker_id"],
    )

    assert profile == {
        "state": "reported",
        "kind": "field_worker",
        "id": "reported-worker-1",
        "name": "Sanjay Singh",
        "reported": {
            "reported_farmer_reach": 1,
            "open_work": 1,
                "completed_work": 0,
                "latest_activity_at": "2026-08-04T10:00:00+05:30",
                "latest_attendance_on": "2026-08-04",
                "source_activity": {
                    "source_work": 1,
                    "completed_source_work": 0,
                    "reported_visits": 0,
                    "reported_disease": 0,
                    "reported_pest": 0,
                    "reported_input_events": 0,
                    "geotagged_evidence": 0,
                    "latest_crop_context": None,
                },
        },
        "account": {"state": "not_created"},
        "limitations": [
            "Reported source work is not a reviewed field-worker assignment or sign-in."
        ],
    }
    serialized = repr(profile)
    assert "private worker task" not in serialized
    assert "9999999999" not in serialized


def test_reviewed_farmer_profile_lists_linked_farm_crop_and_open_work(
    ffl_db, users, crop_allocation
):
    grower = repository.create_person(ffl_db, "Asha Grower", "operations_lead")
    repository.create_person_operating_relationship(
        ffl_db,
        grower.id,
        "crop_allocation",
        crop_allocation.id,
        "grower",
        "2026-06-01",
        provenance="reviewed",
        reviewed_by_person_id=users.manager.id,
    )

    profile = farm_profiles.farmer_profile(ffl_db, grower.id)

    assert profile["relationships"] == [{
        "scope_type": "crop_allocation",
        "scope_name": "North Block",
        "role": "grower",
        "starts_on": "2026-06-01",
    }]
    assert profile["farms"] == [{
        "id": crop_allocation.operational_block_id,
        "name": "North Block",
        "compatibility_kind": "operational_block_not_canonical_farm",
        "current": {"crop_name": "Rice", "cultivar": "Pusa 1121"},
        "open_work_count": 0,
    }]
    assert profile["compatibility"] == {
        "state": "noncanonical",
        "farms_id_kind": "operational_block",
        "message": "Compatibility response: farms entries identify Fields, not canonical Farms.",
    }


def test_reviewed_farm_profile_context_uses_only_non_draft_signal_timestamp(
    ffl_db, users, crop_allocation
):
    template = repository.create_signal_template(
        ffl_db,
        "Profile observation",
        1,
        "published",
        "[]",
        users.lead.id,
        "2026-08-01T00:00:00+00:00",
    )
    repository.create_field_signal(
        ffl_db,
        crop_allocation.id,
        template.id,
        1,
        "2026-08-03T09:15:00+00:00",
        users.operator.id,
        {"private_detail": "canonical payload stays private"},
        status="submitted",
    )
    repository.create_field_signal(
        ffl_db,
        crop_allocation.id,
        template.id,
        1,
        "2026-08-04T10:30:00+00:00",
        users.operator.id,
        {"private_detail": "draft payload stays private"},
        status="draft",
    )

    profile = farm_profiles.farm_profile(ffl_db, crop_allocation.operational_block_id)

    assert profile["record"] == {
        "latest_observed_at": "2026-08-03T09:15:00+00:00",
        "limitation": "Latest activity reflects canonical non-draft field signals only.",
    }
    assert "private_detail" not in repr(profile)
    assert "canonical payload" not in repr(profile)


def test_farm_profile_latest_observation_compares_instants_not_sqlite_text_order(
    ffl_db, users, crop_allocation
):
    template = repository.create_signal_template(
        ffl_db,
        "Offset profile observation",
        1,
        "published",
        "[]",
        users.lead.id,
        "2026-08-01T00:00:00+00:00",
    )
    repository.create_field_signal(
        ffl_db,
        crop_allocation.id,
        template.id,
        1,
        "2026-08-01T10:00:00+05:30",
        users.operator.id,
        {},
    )
    repository.create_field_signal(
        ffl_db,
        crop_allocation.id,
        template.id,
        1,
        "2026-08-01T09:30:00+00:00",
        users.operator.id,
        {},
    )

    profile = farm_profiles.farm_profile(ffl_db, crop_allocation.operational_block_id)

    assert profile["record"]["latest_observed_at"] == "2026-08-01T09:30:00+00:00"


def test_profile_runtime_grant_keeps_work_summary_within_granted_columns(
    ffl_db, users, crop_allocation
):
    work = repository.create_work_item(
        ffl_db,
        crop_allocation.id,
        "Inspect irrigation",
        users.manager.id,
        "2026-08-10T09:00:00+00:00",
    )

    profile = farm_profiles.farm_profile(ffl_db, crop_allocation.operational_block_id)

    assert profile["work"] == [{
        "id": work.id,
        "title": "Inspect irrigation",
        "status": "in_progress",
    }]
    assert users.manager.id not in repr(profile["work"])


def test_profile_runtime_grant_open_work_count_references_granted_id(
    ffl_db, users, crop_allocation
):
    grower = repository.create_person(ffl_db, "Granted Grower", "operations_lead")
    repository.create_person_operating_relationship(
        ffl_db,
        grower.id,
        "crop_allocation",
        crop_allocation.id,
        "grower",
        "2026-06-01",
        reviewed_by_person_id=users.manager.id,
    )

    profile = farm_profiles.farmer_profile(_ColumnGrantConnection(ffl_db), grower.id)

    assert profile["farms"][0]["open_work_count"] == 0


def test_profile_routes_require_manager_and_distinguish_absence(tmp_path):
    app = create_app(str(tmp_path / "profiles.db"), manager_api_token="manager-secret")
    with TestClient(app) as client:
        manager = repository.create_person(app.state.conn, "Fortune COO", "operations_lead")
        app.state.manager_person_id = manager.id
        denied = client.get("/api/v1/farm-profiles/missing")
        absent = client.get(
            "/api/v1/farm-profiles/missing", headers={"X-FFL-Manager-Token": "manager-secret"}
        )

    assert denied.status_code == 403
    assert absent.status_code == 404
    assert absent.json() == {"detail": "farm profile not found"}


def test_entity_routes_require_manager_validate_bounds_and_return_safe_records(tmp_path):
    app = create_app(str(tmp_path / "entities.db"), manager_api_token="manager-secret")
    manager = repository.create_person(app.state.conn, "Fortune COO", "operations_lead")
    app.state.manager_person_id = manager.id
    unit = repository.create_operating_unit(app.state.conn, "Fortune operating unit")
    block = repository.create_operational_block(app.state.conn, unit.id, "North Field", 5.0)
    season = repository.create_season(
        app.state.conn, unit.id, "Kharif 2026", "2026-06-01", "2026-11-30",
    )
    allocation = repository.create_crop_allocation(
        app.state.conn, unit.id, block.id, season.id, "Rice", "Pusa 1121", 5.0,
    )
    farm = repository.create_farm(app.state.conn, unit.id, "Fortune Farm", manager.id)
    repository.assign_field_to_farm(app.state.conn, farm.id, block.id, "2026-06-01", manager.id)
    worker = repository.create_person(app.state.conn, "Nisha Field Worker", "field_operator")
    repository.create_person_operating_relationship(
        app.state.conn, worker.id, "crop_allocation", allocation.id, "field_operator",
        "2026-06-01", reviewed_by_person_id=manager.id,
    )
    grower = repository.create_person(app.state.conn, "Asha Grower", "grower")
    repository.create_person_operating_relationship(
        app.state.conn, grower.id, "crop_allocation", allocation.id, "grower",
        "2026-06-01", reviewed_by_person_id=manager.id,
    )
    parcel = repository.create_land_parcel(app.state.conn, unit.id, "North Parcel", 5.0)
    repository.link_block_parcel(app.state.conn, block.id, parcel.id)
    unit_only = repository.create_person(app.state.conn, "Unit-only Grower", "grower")
    parcel_only = repository.create_person(app.state.conn, "Parcel-only Grower", "grower")
    repository.create_person_operating_relationship(
        app.state.conn, unit_only.id, "operating_unit", unit.id, "grower",
        "2026-06-01", reviewed_by_person_id=manager.id,
    )
    repository.create_person_operating_relationship(
        app.state.conn, parcel_only.id, "land_parcel", parcel.id, "grower",
        "2026-06-01", reviewed_by_person_id=manager.id,
    )
    headers = {"X-FFL-Manager-Token": "manager-secret"}

    with TestClient(app) as client:
        denied = client.get("/api/v1/farms")
        denied_people = client.get("/api/v1/people?kind=farmer")
        invalid_person_kind = client.get("/api/v1/people/unknown/person-1", headers=headers)
        invalid_kind = client.get("/api/v1/farms?kind=unknown", headers=headers)
        invalid_query = client.get("/api/v1/farms?query=" + "x" * 81, headers=headers)
        invalid_crop = client.get("/api/v1/farms?crop=" + "x" * 81, headers=headers)
        invalid_limit = client.get("/api/v1/farms?limit=101", headers=headers)
        invalid_dates = client.get(
            "/api/v1/farms?date_from=2026-08-02&date_to=2026-08-01", headers=headers,
        )
        directory = client.get("/api/v1/farms?query=Fortune&crop=Rice", headers=headers)
        filtered_directory = client.get(
            "/api/v1/farms?state=reviewed,reported&activity=open_tasks,updated_week&order=least_updated",
            headers=headers,
        )
        invalid_order = client.get("/api/v1/farms?order=unknown", headers=headers)
        farm_record = client.get("/api/v1/farms/" + farm.id, headers=headers)
        field_record = client.get("/api/v1/fields/" + block.id, headers=headers)
        person_record = client.get(
            "/api/v1/people/field_worker/" + worker.id, headers=headers,
        )
        farmer_record = client.get("/api/v1/people/farmer/" + grower.id, headers=headers)
        farmer_directory = client.get("/api/v1/people?kind=farmer", headers=headers)
        invalid_people_kind = client.get("/api/v1/people?kind=unknown", headers=headers)
        linked_farm_records = [
            client.get("/api/v1/farms/" + assignment["farm_id"], headers=headers)
            for assignment in farmer_record.json()["assignments"]
        ]
        absent_farm = client.get("/api/v1/farms/missing", headers=headers)
        absent_field = client.get("/api/v1/fields/missing", headers=headers)
        absent_person = client.get("/api/v1/people/farmer/missing", headers=headers)
        legacy_farm = client.get("/api/v1/farm-profiles/" + block.id, headers=headers)
        legacy_farmer = client.get("/api/v1/farmer-profiles/" + grower.id, headers=headers)

    assert denied.status_code == denied_people.status_code == 403
    assert all(response.status_code == 422 for response in (
        invalid_person_kind, invalid_kind, invalid_query, invalid_crop, invalid_limit, invalid_dates,
    ))
    assert directory.json() == [{
        "state": "reviewed", "kind": "farm", "id": farm.id, "name": "Fortune Farm",
        "field_count": 1, "crops": ["Rice"], "open_work_count": 0, "latest_update_at": None,
    }]
    assert filtered_directory.status_code == 200
    assert invalid_order.status_code == 422
    assert farm_record.status_code == field_record.status_code == person_record.status_code == 200
    assert farmer_record.status_code == 200
    assert invalid_people_kind.status_code == 422
    assert farmer_directory.json() == [{
        "state": "reviewed", "kind": "farmer", "id": grower.id,
        "name": "Asha Grower", "assignment_count": 1,
    }]
    assert unit_only.id not in repr(farmer_directory.json())
    assert parcel_only.id not in repr(farmer_directory.json())
    assert linked_farm_records and all(response.status_code == 200 for response in linked_farm_records)
    assert {response.json()["id"] for response in linked_farm_records} == {farm.id}
    assert legacy_farm.json()["compatibility"]["id_kind"] == "operational_block"
    assert legacy_farm.json()["compatibility"]["state"] == "noncanonical"
    assert legacy_farmer.json()["compatibility"]["farms_id_kind"] == "operational_block"
    assert legacy_farmer.json()["farms"][0]["compatibility_kind"] == (
        "operational_block_not_canonical_farm"
    )
    assert "provider_identifier" not in repr([
        farm_record.json(), field_record.json(), person_record.json(), directory.json(),
    ])
    assert "contact_value" not in repr([
        farm_record.json(), field_record.json(), person_record.json(), directory.json(),
    ])
    assert absent_farm.json() == {"detail": "farm record not found"}
    assert absent_field.json() == {"detail": "field record not found"}
    assert absent_person.json() == {"detail": "person record not found"}


def test_command_centre_has_on_demand_profiles_and_muted_whatsapp_status():
    source = Path("apps/web/components/command-centre.tsx").read_text()

    assert 'readJson<FarmRecord>("/api/v1/farms/" + id)' in source
    assert 'readJson<FieldRecord>("/api/v1/fields/" + id)' in source
    assert 'readJson<PersonContext>("/api/v1/people/" + kind + "/" + id)' in source
    assert 'readJson<PersonContext>("/api/v1/people/" + kind + "/" + id)' in source
    assert 'readJson<ReportedFarmProfile>("/api/v1/reported-farm-profiles/" + id)' in source
    assert "WhatsApp updates" in source
    assert "Coming soon" in source
    assert "disabled-connection" in source
    assert "canOpenProfiles={Boolean(state.session?.authenticated)}" in source
    assert 'className="profile-locked" href="/login">Sign in to open' in source
    assert "directoryOpener.current = openerId" in source
    assert "document.getElementById(openerId)?.focus()" in source
    assert '<div className="disabled-connection" aria-disabled="true">' in source


def test_command_centre_uses_farm_first_entity_profiles():
    source = Path("apps/web/components/command-centre.tsx").read_text()

    assert 'readJson<FarmDirectory>("/api/v1/farms?" + params)' in source
    assert 'readJson<FarmRecord>("/api/v1/farms/" + id)' in source
    assert 'readJson<FieldRecord>("/api/v1/fields/" + id)' in source
    assert 'readJson<PersonContext>("/api/v1/people/" + kind + "/" + id)' in source
    for heading in ("Now", "People", "Updates", "Context"):
        assert f">{heading}<" in source


def test_reported_farm_profile_is_simple_and_reviewable():
    source = Path("apps/web/components/command-centre.tsx").read_text()

    assert "Farm details" in source
    assert "Activity" in source
    assert "Make it a Farm" in source
    assert "Create Farm" in source
    assert "TrackWick reported this candidate" not in source


def test_command_centre_renders_safe_entity_context_and_reported_disease_event():
    source = Path("apps/web/components/command-centre.tsx").read_text()

    assert "Latest activity" in source
    assert "Photos" in source
    assert "Canonical Farms" in source
    assert "Crop seasons" in source
    assert "Assignments" in source
    assert "item.field_worker_name" not in source
    assert 'readJson<TrackwickBoard>("/api/v1/trackwick/command-centre-board")' in source
    assert '"/api/v1/trackwick/board"' not in source
    assert "reviewed_farms" in source
    assert 'session: { authenticated: false }' in source
    assert '<a href="/manager">Re-authenticate in Farm Truth</a>' in source
    assert "Disease &amp; pest" in source
    assert "Filter field issues" in source
    assert "PersonContextPanel" in source
    assert "FieldRecordPanel" in source
    assert "A reviewed field boundary is required before this Field can appear on a map." in source
    assert "A Field boundary is added only when it is confirmed." in source
    assert 'return <Link id={controlId} className="profile-locked" href="/login">Sign in to open</Link>;' in source


def test_primary_ui_uses_canonical_farmer_and_farm_routes_and_safe_source_label():
    source = Path("apps/web/components/command-centre.tsx").read_text()

    assert 'readJson<PersonContext>("/api/v1/people/" + kind + "/" + id)' in source
    assert 'readJson<ReviewedFarmerCard[]>("/api/v1/people?kind=farmer&limit=100")' in source
    assert 'readJson<FarmRecord>("/api/v1/farms/" + id)' in source
    assert 'readJson<FarmerProfile>("/api/v1/farmer-profiles/" + id)' not in source
    assert 'href={`/farms?farm=${encodeURIComponent(farm.id)}`}' in source
    assert 'readJson<ReportedFarmProfile>("/api/v1/reported-farm-profiles/" + id)' in source
    assert 'readJson<ReportedFieldWorkerProfile>("/api/v1/reported-field-worker-profiles/" + id)' in source
    assert "to review" in source
    assert "Field workers" in source
    assert "item.label" in source
    assert "item.task_type" not in source
    assert "runtime?.person_operating_relationships" not in source


def test_command_centre_mobile_farm_facts_are_one_column_with_row_dividers():
    css = Path("apps/web/app/globals.css").read_text()
    mobile = css.split("@media (max-width: 520px) {", 1)[1]

    assert ".farm-directory-card dl { grid-template-columns: 1fr; }" in mobile
    assert ".farm-directory-card dl > div { border-top: 1px solid" in mobile
    assert "border-left: 0" in mobile
    assert "repeat(3, minmax(0, 1fr))" not in mobile


def test_command_centre_session_expiry_restores_focus_to_opener_or_boundary():
    source = Path("apps/web/components/command-centre.tsx").read_text()

    assert "if (expired) pendingManagerExpiryFocus.current = true;" in source
    assert "if (canOpenProfiles || panel || !pendingManagerExpiryFocus.current) return;" in source
    assert "restoreFocusAfterManagerExpiry();" in source
    assert "document.getElementById(MANAGER_ACCESS_BOUNDARY_ID)" in source
    assert "target?.focus()" in source
    assert "focusId={MANAGER_ACCESS_BOUNDARY_ID}" in source


def test_command_centre_uses_authenticated_cache_and_directory_skeleton_before_session_resolves():
    source = Path("apps/web/components/command-centre.tsx").read_text()

    assert "if (!value.session?.authenticated) return;" in source
    assert 'session: { authenticated: true }, loading: false, error: null' in source
    assert "if (!state.session?.authenticated || !state.profile || !state.trackwick) return;" in source
    assert 'function DirectoryLoadingState({ label }: { label: string })' in source
    assert '!accessResolved\n      ? <DirectoryLoadingState label="Opening farms" />' in source
    assert '!accessResolved ? <DirectoryLoadingState label="Opening farmers" />' in source


def test_command_centre_revalidates_saved_data_without_blank_workspace_states():
    source = Path("apps/web/components/command-centre.tsx").read_text()

    assert 'window.addEventListener("focus", revalidate);' in source
    assert 'window.addEventListener("online", revalidate);' in source
    assert 'document.addEventListener("visibilitychange", revalidate);' in source
    assert "Showing saved data while we reconnect." in source
    assert 'function MapLoadingState({ label }: { label: string })' in source
    assert '<MapLoadingState label="Opening the field map" />' in source


def test_farmer_profile_requires_an_active_reviewed_grower_relationship(ffl_db, users, crop_allocation):
    person = repository.create_person(ffl_db, "Not a grower", "operations_lead")
    repository.create_person_operating_relationship(
        ffl_db, person.id, "crop_allocation", crop_allocation.id, "field_operator", "2026-06-01",
        reviewed_by_person_id=users.manager.id,
    )
    assert farm_profiles.farmer_profile(ffl_db, person.id) is None


def test_farm_profile_people_include_reviewed_operating_unit_roles(ffl_db, users, crop_allocation):
    operator = repository.create_person(ffl_db, "Unit Operator", "field_operator")
    repository.create_person_operating_relationship(
        ffl_db, operator.id, "operating_unit", crop_allocation.operating_unit_id, "field_operator", "2026-06-01",
        reviewed_by_person_id=users.manager.id,
    )

    profile = farm_profiles.farm_profile(ffl_db, crop_allocation.operational_block_id)

    assert {person["id"] for person in profile["people"]} == {operator.id}
