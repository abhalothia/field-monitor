"""Communications identity and dispatch policy stay inside reviewed authority."""

from datetime import datetime, timezone

import pytest

from ffl.communications.identity import resolve_communication_endpoint
from ffl.communications.persistence import (
    create_communication_profile,
    create_communications_schema,
    create_endpoint,
    set_scoped_consent,
    verify_endpoint,
)
from ffl.communications.policy import may_dispatch
from ffl.persistence import repository


@pytest.fixture
def portal_context(ffl_db, crop_allocation):
    create_communications_schema(ffl_db)
    now = "2026-08-07T12:00:00+00:00"
    ffl_db.execute(
        "INSERT INTO customer_portals VALUES (?, ?, ?, ?, 'active', ?)",
        ("portal-resolution", "portal-resolution", "Resolution Portal", "resolution.example.test", now),
    )

    people = {}
    for role in ("owner", "admin", "farmer", "field_worker"):
        person = repository.create_person(ffl_db, "Resolution " + role, "grower")
        identity_id = "identity-" + role
        ffl_db.execute(
            """INSERT INTO portal_identities
               (id, person_id, phone_e164, auth_subject, identity_status, invited_at,
                verified_at, last_authenticated_at, created_at)
               VALUES (?, ?, ?, ?, 'active', ?, ?, NULL, ?)""",
            (identity_id, person.id, "+91970000000" + str(len(people) + 1), "auth-" + role, now, now, now),
        )
        ffl_db.execute(
            """INSERT INTO portal_memberships
               (id, portal_id, person_id, identity_id, portal_role, membership_status,
                invited_at, activated_at, created_at)
               VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?)""",
            ("membership-" + role, "portal-resolution", person.id, identity_id, role, now, now, now),
        )
        people[role] = person

    repository.create_person_operating_relationship(
        ffl_db, people["farmer"].id, "crop_allocation", crop_allocation.id,
        "grower", "2026-06-01", provenance="reviewed farmer roster",
    )
    repository.create_person_operating_relationship(
        ffl_db, people["field_worker"].id, "crop_allocation", crop_allocation.id,
        "field_operator", "2026-06-01", provenance="reviewed worker roster",
    )
    ffl_db.commit()
    return type("PortalContext", (), {
        "id": "portal-resolution",
        "people": people,
        "allocation_id": crop_allocation.id,
        "admin_id": people["admin"].id,
    })()


def _verified(ffl_db, context, role, address):
    profile = create_communication_profile(
        ffl_db, context.id, context.people[role].id, "hi-IN", "Asia/Kolkata",
    )
    endpoint = verify_endpoint(
        ffl_db, profile["id"], "loopmessage", address,
        "reviewed portal invitation", context.admin_id,
    )
    return profile, endpoint


def test_resolution_requires_verified_endpoint_active_membership_and_scope(ffl_db, portal_context):
    address = "+919876543210"
    assert resolve_communication_endpoint(
        ffl_db, "loopmessage", address, portal_context.id,
    ).state == "unknown"

    create_endpoint(
        ffl_db, portal_context.people["farmer"].id, "loopmessage", address, "hi-IN",
    )
    assert resolve_communication_endpoint(
        ffl_db, "loopmessage", address, portal_context.id,
    ).state == "known_unverified"

    profile, endpoint = _verified(ffl_db, portal_context, "farmer", address)
    resolution = resolve_communication_endpoint(
        ffl_db, "loopmessage", address, portal_context.id, received_at="2026-08-07T08:00:00Z",
    )
    assert resolution.state == "eligible_farmer"
    assert resolution.person_id == portal_context.people["farmer"].id
    assert resolution.portal_id == portal_context.id
    assert resolution.endpoint_id == endpoint["id"]
    assert resolution.allocation_ids == (portal_context.allocation_id,)
    assert resolution.locale == "hi-IN"

    ffl_db.execute(
        "UPDATE portal_memberships SET membership_status = 'suspended' WHERE portal_id = ? AND person_id = ?",
        (portal_context.id, portal_context.people["farmer"].id),
    )
    assert resolve_communication_endpoint(
        ffl_db, "loopmessage", address, portal_context.id,
    ).state == "known_ineligible"
    assert profile["portal_id"] == portal_context.id


@pytest.mark.parametrize("role", ["owner", "admin", "farmer", "field_worker"])
def test_resolution_maps_only_the_active_portal_membership_role(ffl_db, portal_context, role):
    address = "+91981110000" + str(["owner", "admin", "farmer", "field_worker"].index(role))
    _verified(ffl_db, portal_context, role, address)

    resolution = resolve_communication_endpoint(
        ffl_db, "loopmessage", address, portal_context.id, received_at="2026-08-07T00:00:00Z",
    )

    assert resolution.state == "eligible_" + role


def test_field_context_requires_current_allocation_coverage(ffl_db, portal_context):
    address = "+919876543211"
    _verified(ffl_db, portal_context, "farmer", address)

    resolution = resolve_communication_endpoint(
        ffl_db, "loopmessage", address, portal_context.id,
        allocation_id="allocation-outside-scope", received_at="2026-08-07T00:00:00Z",
    )

    assert resolution.state == "ambiguous_scope"
    assert resolution.allocation_ids == ()


def test_field_resolution_never_guesses_between_allocations_but_exact_context_resolves(
    ffl_db, portal_context,
):
    first = ffl_db.execute(
        "SELECT operating_unit_id, operational_block_id, season_id FROM crop_allocations WHERE id = ?",
        (portal_context.allocation_id,),
    ).fetchone()
    second_block = repository.create_operational_block(
        ffl_db, first["operating_unit_id"], "Second allocation block", 2.0,
    )
    second = repository.create_crop_allocation(
        ffl_db, first["operating_unit_id"], second_block.id, first["season_id"],
        "Wheat", None, 2.0,
    )
    repository.create_person_operating_relationship(
        ffl_db, portal_context.people["farmer"].id, "crop_allocation", second.id,
        "grower", "2026-06-01", provenance="reviewed second allocation",
    )
    address = "+919876543212"
    _verified(ffl_db, portal_context, "farmer", address)

    ambiguous = resolve_communication_endpoint(
        ffl_db, "loopmessage", address, portal_context.id, received_at="2026-08-07T00:00:00Z",
    )
    exact = resolve_communication_endpoint(
        ffl_db, "loopmessage", address, portal_context.id,
        allocation_id=second.id, received_at="2026-08-07T00:00:00Z",
    )

    assert ambiguous.state == "ambiguous_scope"
    assert ambiguous.allocation_ids == tuple(sorted((portal_context.allocation_id, second.id)))
    assert exact.state == "eligible_farmer"
    assert exact.allocation_ids == (second.id,)


def test_resolution_uses_the_event_date_for_relationship_coverage(ffl_db, portal_context):
    address = "+919876543213"
    _verified(ffl_db, portal_context, "farmer", address)
    ffl_db.execute(
        "UPDATE person_operating_relationships SET starts_on = '2026-08-08' WHERE person_id = ?",
        (portal_context.people["farmer"].id,),
    )

    before = resolve_communication_endpoint(
        ffl_db, "loopmessage", address, portal_context.id,
        allocation_id=portal_context.allocation_id,
        received_at=datetime(2026, 8, 7, 23, 59, tzinfo=timezone.utc),
    )
    after = resolve_communication_endpoint(
        ffl_db, "loopmessage", address, portal_context.id,
        allocation_id=portal_context.allocation_id, received_at="2026-08-08T00:00:00+00:00",
    )

    assert before.state == "ambiguous_scope"
    assert after.state == "eligible_farmer"


def test_policy_rechecks_every_current_authority_before_dispatch(ffl_db, portal_context):
    address = "+919876543214"
    profile, endpoint = _verified(ffl_db, portal_context, "farmer", address)
    resolution = resolve_communication_endpoint(
        ffl_db, "loopmessage", address, portal_context.id,
        allocation_id=portal_context.allocation_id, received_at="2026-08-07T00:00:00Z",
    )
    policy_args = (
        ffl_db, resolution, "weekly_farmer_checkin", "crop_allocation", portal_context.allocation_id,
    )

    assert may_dispatch(*policy_args, dispatch_at="2026-08-07T12:00:00+00:00").code == "consent_not_active"
    set_scoped_consent(
        ffl_db, profile["id"], endpoint["id"], "weekly_farmer_checkin",
        "crop_allocation", portal_context.allocation_id, True,
        "signed field consent", portal_context.admin_id,
    )
    assert may_dispatch(*policy_args, dispatch_at="2026-08-07T12:00:00+00:00").allowed is True

    updates = (
        (
            "UPDATE communication_endpoint_verifications SET status = 'revoked', revoked_at = ? WHERE profile_id = ?",
            ("2026-08-07T12:01:00+00:00", profile["id"]), "endpoint_not_verified",
        ),
        (
            "UPDATE portal_memberships SET membership_status = 'suspended' WHERE portal_id = ? AND person_id = ?",
            (portal_context.id, portal_context.people["farmer"].id), "membership_inactive",
        ),
        (
            "UPDATE communication_profiles SET status = 'disabled' WHERE id = ?",
            (profile["id"],), "profile_inactive",
        ),
        (
            "UPDATE person_operating_relationships SET status = 'ended', ends_on = '2026-08-06' WHERE person_id = ?",
            (portal_context.people["farmer"].id,), "scope_not_covered",
        ),
    )
    restores = (
        (
            "UPDATE communication_endpoint_verifications SET status = 'active', revoked_at = NULL WHERE profile_id = ?",
            (profile["id"],),
        ),
        (
            "UPDATE portal_memberships SET membership_status = 'active' WHERE portal_id = ? AND person_id = ?",
            (portal_context.id, portal_context.people["farmer"].id),
        ),
        ("UPDATE communication_profiles SET status = 'active' WHERE id = ?", (profile["id"],)),
        (
            "UPDATE person_operating_relationships SET status = 'active', ends_on = NULL WHERE person_id = ?",
            (portal_context.people["farmer"].id,),
        ),
    )
    for (statement, params, code), (restore, restore_params) in zip(updates, restores):
        ffl_db.execute(statement, params)
        assert may_dispatch(*policy_args, dispatch_at="2026-08-07T12:00:00+00:00").code == code
        ffl_db.execute(restore, restore_params)


def test_policy_enforces_quiet_hours_and_frequency_cap(ffl_db, portal_context):
    address = "+919876543215"
    profile, endpoint = _verified(ffl_db, portal_context, "farmer", address)
    resolution = resolve_communication_endpoint(
        ffl_db, "loopmessage", address, portal_context.id,
        allocation_id=portal_context.allocation_id, received_at="2026-08-07T00:00:00Z",
    )
    set_scoped_consent(
        ffl_db, profile["id"], endpoint["id"], "weekly_farmer_checkin",
        "crop_allocation", portal_context.allocation_id, True,
        "signed field consent", portal_context.admin_id,
    )
    args = (ffl_db, resolution, "weekly_farmer_checkin", "crop_allocation", portal_context.allocation_id)

    quiet = may_dispatch(
        *args, dispatch_at="2026-08-07T18:00:00+00:00", quiet_hours=("22:00", "06:00"),
    )
    capped = may_dispatch(
        *args, dispatch_at="2026-08-07T12:00:00+00:00", messages_sent=2, frequency_cap=2,
    )
    allowed = may_dispatch(
        *args, dispatch_at="2026-08-07T12:00:00+00:00",
        quiet_hours=("22:00", "06:00"), messages_sent=1, frequency_cap=2,
    )

    assert quiet.code == "quiet_hours"
    assert capped.code == "frequency_cap"
    assert allowed.allowed is True
    assert allowed.code == "allowed"


def test_policy_binds_consent_scope_to_the_effective_allocation(ffl_db, portal_context):
    allocation = ffl_db.execute(
        "SELECT operating_unit_id, season_id FROM crop_allocations WHERE id = ?",
        (portal_context.allocation_id,),
    ).fetchone()
    other_block = repository.create_operational_block(
        ffl_db, allocation["operating_unit_id"], "Other consent block", 2.0,
    )
    other_allocation = repository.create_crop_allocation(
        ffl_db, allocation["operating_unit_id"], other_block.id, allocation["season_id"],
        "Wheat", None, 2.0,
    )
    repository.create_person_operating_relationship(
        ffl_db, portal_context.people["farmer"].id, "crop_allocation", other_allocation.id,
        "grower", "2026-06-01", provenance="reviewed other allocation",
    )
    address = "+919876543216"
    profile, endpoint = _verified(ffl_db, portal_context, "farmer", address)
    resolution = resolve_communication_endpoint(
        ffl_db, "loopmessage", address, portal_context.id,
        allocation_id=portal_context.allocation_id, received_at="2026-08-07T00:00:00Z",
    )
    set_scoped_consent(
        ffl_db, profile["id"], endpoint["id"], "weekly_farmer_checkin",
        "crop_allocation", other_allocation.id, True,
        "consent for the other allocation", portal_context.admin_id,
    )

    decision = may_dispatch(
        ffl_db, resolution, "weekly_farmer_checkin", "crop_allocation", other_allocation.id,
        allocation_id=portal_context.allocation_id,
        dispatch_at="2026-08-07T12:00:00+00:00",
    )

    assert decision.allowed is False
    assert decision.code == "scope_not_covered"


@pytest.mark.parametrize("scope_type", ["operating_unit", "operational_block", "land_parcel"])
def test_policy_proves_broader_consent_scope_contains_the_allocation(
    ffl_db, portal_context, scope_type,
):
    allocation = ffl_db.execute(
        "SELECT operating_unit_id, operational_block_id FROM crop_allocations WHERE id = ?",
        (portal_context.allocation_id,),
    ).fetchone()
    scope_id = {
        "operating_unit": allocation["operating_unit_id"],
        "operational_block": allocation["operational_block_id"],
    }.get(scope_type)
    if scope_type == "land_parcel":
        parcel = repository.create_land_parcel(
            ffl_db, allocation["operating_unit_id"], "Consent title parcel", 5.0,
        )
        repository.link_block_parcel(
            ffl_db, allocation["operational_block_id"], parcel.id,
        )
        scope_id = parcel.id
    repository.create_person_operating_relationship(
        ffl_db, portal_context.people["farmer"].id, scope_type,
        scope_id, "grower", "2026-06-01",
        provenance="reviewed whole-unit relationship",
    )
    address = "+919876543217"
    profile, endpoint = _verified(ffl_db, portal_context, "farmer", address)
    resolution = resolve_communication_endpoint(
        ffl_db, "loopmessage", address, portal_context.id,
        allocation_id=portal_context.allocation_id, received_at="2026-08-07T00:00:00Z",
    )
    set_scoped_consent(
        ffl_db, profile["id"], endpoint["id"], "weekly_farmer_checkin",
        scope_type, scope_id, True, "reviewed broader-scope consent", portal_context.admin_id,
    )

    decision = may_dispatch(
        ffl_db, resolution, "weekly_farmer_checkin", scope_type,
        scope_id, allocation_id=portal_context.allocation_id,
        dispatch_at="2026-08-07T12:00:00+00:00",
    )

    assert decision.allowed is True


def test_equivalent_instants_use_one_utc_coverage_date_and_naive_time_fails_closed(
    ffl_db, portal_context,
):
    address = "+919876543218"
    profile, endpoint = _verified(ffl_db, portal_context, "farmer", address)
    prior_resolution = resolve_communication_endpoint(
        ffl_db, "loopmessage", address, portal_context.id,
        allocation_id=portal_context.allocation_id, received_at="2026-08-07T12:00:00Z",
    )
    set_scoped_consent(
        ffl_db, profile["id"], endpoint["id"], "weekly_farmer_checkin",
        "crop_allocation", portal_context.allocation_id, True,
        "time-bound consent", portal_context.admin_id,
    )
    ffl_db.execute(
        "UPDATE person_operating_relationships SET starts_on = '2026-08-08' WHERE person_id = ?",
        (portal_context.people["farmer"].id,),
    )
    offset_instant = "2026-08-08T00:30:00+05:30"
    utc_instant = "2026-08-07T19:00:00Z"

    offset_resolution = resolve_communication_endpoint(
        ffl_db, "loopmessage", address, portal_context.id,
        allocation_id=portal_context.allocation_id, received_at=offset_instant,
    )
    utc_resolution = resolve_communication_endpoint(
        ffl_db, "loopmessage", address, portal_context.id,
        allocation_id=portal_context.allocation_id, received_at=utc_instant,
    )
    naive_resolution = resolve_communication_endpoint(
        ffl_db, "loopmessage", address, portal_context.id,
        allocation_id=portal_context.allocation_id, received_at="2026-08-07T19:00:00",
    )

    assert offset_resolution == utc_resolution
    assert utc_resolution.state == "ambiguous_scope"
    assert naive_resolution.state == "known_ineligible"

    args = (
        ffl_db, prior_resolution, "weekly_farmer_checkin", "crop_allocation",
        portal_context.allocation_id,
    )
    offset_decision = may_dispatch(*args, dispatch_at=offset_instant)
    utc_decision = may_dispatch(*args, dispatch_at=utc_instant)
    naive_decision = may_dispatch(*args, dispatch_at="2026-08-07T19:00:00")

    assert offset_decision == utc_decision
    assert utc_decision.code == "scope_not_covered"
    assert naive_decision.code == "scope_not_covered"
