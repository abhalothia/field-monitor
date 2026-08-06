from __future__ import annotations

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
    return {"farmer_id": "reported-farmer-1"}


def test_farm_profile_returns_reviewed_truth_and_not_source_context(ffl_db, users, crop_allocation):
    grower = repository.create_person(ffl_db, "Asha Grower", "grower")
    repository.create_person_operating_relationship(
        ffl_db, grower.id, "crop_allocation", crop_allocation.id, "grower",
        "2026-06-01", provenance="reviewed contract", reviewed_by_person_id=users.manager.id,
    )

    profile = farm_profiles.farm_profile(ffl_db, crop_allocation.operational_block_id)

    assert profile["state"] == "reviewed"
    assert profile["kind"] == "farm"
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
        "current": {"crop_name": "Rice", "cultivar": "Pusa 1121"},
        "open_work_count": 0,
    }]


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


def test_command_centre_has_on_demand_profiles_and_muted_whatsapp_status():
    source = Path("apps/web/components/command-centre.tsx").read_text()

    assert 'readJson<FarmProfile>("/api/v1/farm-profiles/" + id)' in source
    assert 'readJson<FarmerProfile>("/api/v1/farmer-profiles/" + id)' in source
    assert "WhatsApp updates" in source
    assert "Coming soon" in source
    assert "disabled-connection" in source
    assert "canOpenProfiles={Boolean(state.session?.authenticated)}" in source
    assert 'aria-disabled="true">Manager access required' in source
    assert "new Map<string, ReviewedFarmCard>()" in source
    assert "allocation.operational_block_id" in source
    assert "peopleById.get(personId)" in source
    assert "isFarmer(person.role) &&" not in source
    assert "profileOpener.current = openerId" in source
    assert "document.getElementById(openerId)?.focus()" in source
    assert '<div className="disabled-connection" aria-disabled="true">' in source


def test_command_centre_renders_profile_context_without_field_worker_surface():
    source = Path("apps/web/components/command-centre.tsx").read_text()

    assert "Latest activity" in source
    assert "Photo references" in source
    assert "Linked farms" in source
    assert "Field record" in source
    assert "item.field_worker_name" not in source
