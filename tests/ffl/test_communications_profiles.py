from pathlib import Path

import pytest

from ffl.communications.persistence import (
    create_communication_profile,
    create_communications_schema,
    has_scoped_consent,
    profile_for_endpoint,
    set_scoped_consent,
    verify_endpoint,
)
from ffl.persistence import repository


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "db" / "postgres" / "0021_agro_communications_control_plane.sql"


@pytest.fixture
def seeded_portal(ffl_db, crop_allocation):
    create_communications_schema(ffl_db)
    farmer = repository.create_person(ffl_db, "Consent Farmer", "grower")
    admin = repository.create_person(ffl_db, "Consent Admin", "manager")
    other = repository.create_person(ffl_db, "Other Endpoint Person", "grower")
    now = "2026-08-07T12:00:00+00:00"
    ffl_db.execute(
        "INSERT INTO customer_portals VALUES (?, ?, ?, ?, 'active', ?)",
        ("portal-1", "portal-one", "Portal One", "portal-one.example.test", now),
    )
    ffl_db.execute(
        "INSERT INTO customer_portals VALUES (?, ?, ?, ?, 'active', ?)",
        ("portal-2", "portal-two", "Portal Two", "portal-two.example.test", now),
    )
    for membership_id, portal_id, person_id, role in (
        ("membership-farmer", "portal-1", farmer.id, "farmer"),
        ("membership-admin", "portal-1", admin.id, "admin"),
        ("membership-farmer-2", "portal-2", farmer.id, "farmer"),
    ):
        ffl_db.execute(
            """INSERT INTO portal_memberships
               (id, portal_id, person_id, identity_id, portal_role, membership_status,
                invited_at, activated_at, created_at)
               VALUES (?, ?, ?, NULL, ?, 'identity_pending', NULL, NULL, ?)""",
            (membership_id, portal_id, person_id, role, now),
        )
    relationship = repository.create_person_operating_relationship(
        ffl_db, farmer.id, "crop_allocation", crop_allocation.id, "grower",
        "2026-06-01", provenance="reviewed pilot register",
    )
    ffl_db.commit()
    return type(
        "SeededPortal",
        (),
        {
            "id": "portal-1",
            "other_portal_id": "portal-2",
            "farmer_id": farmer.id,
            "admin_id": admin.id,
            "other_person_id": other.id,
            "allocation_id": crop_allocation.id,
            "relationship_id": relationship.id,
        },
    )()


def test_postgres_migration_is_private_and_has_scoped_control_plane_constraints():
    sql = MIGRATION.read_text(encoding="utf-8")

    for table in (
        "agro_communication_profiles",
        "agro_communication_endpoint_verifications",
        "agro_communication_endpoint_scopes",
        "agro_communication_scoped_consents",
        "agro_communication_scoped_consent_events",
    ):
        assert "CREATE TABLE IF NOT EXISTS " + table in sql
        assert "REVOKE ALL ON TABLE " + table + " FROM PUBLIC" in sql
    assert "GRANT " not in sql
    assert "endpoint_id, purpose, scope_type, scope_id, channel" in sql
    assert "WHERE status = 'active'" in sql


def test_verified_endpoint_is_tenant_scoped_and_consent_is_scope_specific(ffl_db, seeded_portal):
    profile = create_communication_profile(
        ffl_db, seeded_portal.id, seeded_portal.farmer_id, "hi-IN", "Asia/Kolkata",
    )
    endpoint = verify_endpoint(
        ffl_db, profile["id"], "loopmessage", "+919876543210",
        "portal_invitation", seeded_portal.admin_id,
    )
    set_scoped_consent(
        ffl_db, profile["id"], endpoint["id"], "weekly_farmer_checkin",
        "crop_allocation", seeded_portal.allocation_id, True,
        "signed consent", seeded_portal.admin_id,
    )

    assert profile_for_endpoint(
        ffl_db, "loopmessage", "+919876543210", seeded_portal.id,
    )["id"] == profile["id"]
    assert profile_for_endpoint(
        ffl_db, "loopmessage", "+919876543210", seeded_portal.other_portal_id,
    ) is None
    assert has_scoped_consent(
        ffl_db, profile["id"], endpoint["id"], "weekly_farmer_checkin",
        "crop_allocation", seeded_portal.allocation_id,
    )
    assert not has_scoped_consent(
        ffl_db, profile["id"], endpoint["id"], "weekly_farmer_checkin",
        "crop_allocation", "allocation-2",
    )


def test_endpoint_verification_rejects_an_existing_endpoint_for_another_person(ffl_db, seeded_portal):
    profile = create_communication_profile(
        ffl_db, seeded_portal.id, seeded_portal.farmer_id, "hi-IN", "Asia/Kolkata",
    )
    from ffl.communications.persistence import create_endpoint

    create_endpoint(
        ffl_db, seeded_portal.other_person_id, "loopmessage", "+919876543210", "hi-IN",
    )

    with pytest.raises(ValueError, match="endpoint person does not match"):
        verify_endpoint(
            ffl_db, profile["id"], "loopmessage", "+919876543210",
            "portal_invitation", seeded_portal.admin_id,
        )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"purpose": "marketing"}, "communication purpose"),
        ({"scope_type": "portal"}, "communication scope"),
        ({"channel": "sms"}, "communication channel"),
    ],
)
def test_scoped_consent_rejects_unknown_vocabulary(ffl_db, seeded_portal, overrides, message):
    profile = create_communication_profile(
        ffl_db, seeded_portal.id, seeded_portal.farmer_id, "hi-IN", "Asia/Kolkata",
    )
    endpoint = verify_endpoint(
        ffl_db, profile["id"], "loopmessage", "+919876543210",
        "portal_invitation", seeded_portal.admin_id,
    )
    values = {
        "purpose": "weekly_farmer_checkin",
        "scope_type": "crop_allocation",
        "channel": "whatsapp",
    }
    values.update(overrides)

    with pytest.raises(ValueError, match=message):
        set_scoped_consent(
            ffl_db, profile["id"], endpoint["id"], values["purpose"],
            values["scope_type"], seeded_portal.allocation_id, True,
            "signed consent", seeded_portal.admin_id, channel=values["channel"],
        )


def test_scoped_consent_revocation_appends_event_and_retains_capture_evidence(ffl_db, seeded_portal):
    profile = create_communication_profile(
        ffl_db, seeded_portal.id, seeded_portal.farmer_id, "hi-IN", "Asia/Kolkata",
    )
    endpoint = verify_endpoint(
        ffl_db, profile["id"], "loopmessage", "+919876543210",
        "portal_invitation", seeded_portal.admin_id,
    )
    granted = set_scoped_consent(
        ffl_db, profile["id"], endpoint["id"], "weekly_farmer_checkin",
        "crop_allocation", seeded_portal.allocation_id, True,
        "signed consent", seeded_portal.admin_id,
    )
    revoked = set_scoped_consent(
        ffl_db, profile["id"], endpoint["id"], "weekly_farmer_checkin",
        "crop_allocation", seeded_portal.allocation_id, False,
        "farmer opted out", seeded_portal.admin_id,
    )
    events = ffl_db.execute(
        """SELECT status, evidence FROM communication_scoped_consent_events
           WHERE consent_id = ? ORDER BY created_at, id""",
        (granted["id"],),
    ).fetchall()

    assert revoked["id"] == granted["id"]
    assert revoked["status"] == "revoked"
    assert revoked["evidence"] == "signed consent"
    assert revoked["granted_at"] == granted["granted_at"]
    assert revoked["revoked_at"] is not None
    assert [dict(event) for event in events] == [
        {"status": "active", "evidence": "signed consent"},
        {"status": "revoked", "evidence": "farmer opted out"},
    ]
    assert not has_scoped_consent(
        ffl_db, profile["id"], endpoint["id"], "weekly_farmer_checkin",
        "crop_allocation", seeded_portal.allocation_id,
    )
    with pytest.raises(Exception, match="append-only"):
        ffl_db.execute(
            "DELETE FROM communication_scoped_consent_events WHERE consent_id = ?",
            (granted["id"],),
        )


def test_scoped_consent_requires_its_active_tenant_verification_and_scope_chain(ffl_db, seeded_portal):
    first_profile = create_communication_profile(
        ffl_db, seeded_portal.id, seeded_portal.farmer_id, "hi-IN", "Asia/Kolkata",
    )
    endpoint = verify_endpoint(
        ffl_db, first_profile["id"], "loopmessage", "+919876543210",
        "portal_invitation", seeded_portal.admin_id,
    )
    set_scoped_consent(
        ffl_db, first_profile["id"], endpoint["id"], "weekly_farmer_checkin",
        "crop_allocation", seeded_portal.allocation_id, True,
        "signed consent", seeded_portal.admin_id,
    )
    second_profile = create_communication_profile(
        ffl_db, seeded_portal.other_portal_id, seeded_portal.farmer_id,
        "hi-IN", "Asia/Kolkata",
    )
    verify_endpoint(
        ffl_db, second_profile["id"], "loopmessage", "+919876543210",
        "portal_invitation", seeded_portal.admin_id,
    )

    assert not has_scoped_consent(
        ffl_db, second_profile["id"], endpoint["id"], "weekly_farmer_checkin",
        "crop_allocation", seeded_portal.allocation_id,
    )

    ffl_db.execute(
        "UPDATE communication_profiles SET status = 'revoked' WHERE id = ?",
        (first_profile["id"],),
    )
    assert not has_scoped_consent(
        ffl_db, first_profile["id"], endpoint["id"], "weekly_farmer_checkin",
        "crop_allocation", seeded_portal.allocation_id,
    )

    ffl_db.execute(
        "UPDATE communication_profiles SET status = 'active' WHERE id = ?",
        (first_profile["id"],),
    )
    ffl_db.execute(
        """UPDATE communication_endpoint_verifications
           SET status = 'revoked', revoked_at = ?
           WHERE profile_id = ? AND endpoint_id = ? AND status = 'active'""",
        ("2026-08-07T13:00:00+00:00", first_profile["id"], endpoint["id"]),
    )
    assert not has_scoped_consent(
        ffl_db, first_profile["id"], endpoint["id"], "weekly_farmer_checkin",
        "crop_allocation", seeded_portal.allocation_id,
    )

    ffl_db.execute(
        """UPDATE communication_endpoint_verifications
           SET status = 'active', revoked_at = NULL
           WHERE profile_id = ? AND endpoint_id = ?""",
        (first_profile["id"], endpoint["id"]),
    )
    ffl_db.execute(
        """UPDATE communication_endpoint_scopes
           SET status = 'revoked', ends_on = '2026-08-07'
           WHERE profile_id = ? AND scope_type = ? AND scope_id = ?""",
        (first_profile["id"], "crop_allocation", seeded_portal.allocation_id),
    )
    assert not has_scoped_consent(
        ffl_db, first_profile["id"], endpoint["id"], "weekly_farmer_checkin",
        "crop_allocation", seeded_portal.allocation_id,
    )


def test_scoped_consent_rejects_revocation_without_a_prior_grant(ffl_db, seeded_portal):
    profile = create_communication_profile(
        ffl_db, seeded_portal.id, seeded_portal.farmer_id, "hi-IN", "Asia/Kolkata",
    )
    endpoint = verify_endpoint(
        ffl_db, profile["id"], "loopmessage", "+919876543210",
        "portal_invitation", seeded_portal.admin_id,
    )

    with pytest.raises(ValueError, match="before grant"):
        set_scoped_consent(
            ffl_db, profile["id"], endpoint["id"], "weekly_farmer_checkin",
            "crop_allocation", seeded_portal.allocation_id, False,
            "unverified opt-out", seeded_portal.admin_id,
        )

    assert ffl_db.execute("SELECT count(*) FROM communication_scoped_consents").fetchone()[0] == 0
    assert ffl_db.execute("SELECT count(*) FROM communication_scoped_consent_events").fetchone()[0] == 0
