from __future__ import annotations

import pytest

from ffl.persistence import repository
from ffl.services import farm_profiles


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
