"""Tests for the fail-closed person-to-allocation coverage gate."""

import sqlite3

import pytest

from ffl.persistence import repository
from ffl.services.allocation_relationship_coverage import active_person_allocation_coverage


def _establish(ffl_db, person_id, scope_type, scope_id, role="field_operator", starts_on="2026-06-01"):
    return repository.create_person_operating_relationship(
        ffl_db,
        person_id=person_id,
        scope_type=scope_type,
        scope_id=scope_id,
        role=role,
        starts_on=starts_on,
        provenance="reviewed operating roster",
    )


@pytest.mark.parametrize("scope_type", [
    "crop_allocation", "operational_block", "land_parcel", "operating_unit",
])
def test_active_explicit_scopes_cover_their_allocation(ffl_db, crop_allocation, users, scope_type):
    unit_row = ffl_db.execute(
        "SELECT id, name FROM operating_units WHERE id = ?", (crop_allocation.operating_unit_id,)
    ).fetchone()
    block_row = ffl_db.execute(
        "SELECT id, name FROM operational_blocks WHERE id = ?", (crop_allocation.operational_block_id,)
    ).fetchone()
    scope_id = {
        "crop_allocation": crop_allocation.id,
        "operational_block": crop_allocation.operational_block_id,
        "operating_unit": crop_allocation.operating_unit_id,
    }.get(scope_type)
    if scope_type == "land_parcel":
        parcel = repository.create_land_parcel(
            ffl_db, crop_allocation.operating_unit_id, "North title parcel", 5.0
        )
        repository.link_block_parcel(ffl_db, crop_allocation.operational_block_id, parcel.id)
        scope_id = parcel.id
    _establish(ffl_db, users.operator.id, scope_type, scope_id)  # type: ignore[arg-type]

    coverage = active_person_allocation_coverage(
        ffl_db, users.operator.id, crop_allocation.id, on_date="2026-07-01"
    )

    assert coverage.eligible is True
    assert coverage.allocation_id == crop_allocation.id
    assert coverage.allocation_name == "Rice · Pusa 1121 · Kharif 2026"
    assert coverage.block_id == block_row["id"]
    assert coverage.block_name == block_row["name"]
    assert coverage.operating_unit_id == unit_row["id"]
    assert coverage.operating_unit_name == unit_row["name"]
    assert [(match.scope_type, match.scope_id, match.role) for match in coverage.matching_scopes] == [
        (scope_type, scope_id, "field_operator")
    ]


def test_only_a_block_linked_to_the_allocation_can_extend_a_parcel_relationship(
    ffl_db, crop_allocation, users,
):
    other_block = repository.create_operational_block(
        ffl_db, crop_allocation.operating_unit_id, "South Block", 3.0
    )
    unrelated_parcel = repository.create_land_parcel(
        ffl_db, crop_allocation.operating_unit_id, "South title parcel", 3.0
    )
    repository.link_block_parcel(ffl_db, other_block.id, unrelated_parcel.id)
    _establish(ffl_db, users.operator.id, "land_parcel", unrelated_parcel.id)

    coverage = active_person_allocation_coverage(
        ffl_db, users.operator.id, crop_allocation.id, on_date="2026-07-01"
    )

    assert coverage.eligible is False
    assert coverage.allocation_id == crop_allocation.id
    assert coverage.matching_scopes == ()


def test_future_or_ended_relationship_never_covers_an_allocation(ffl_db, crop_allocation, users):
    _establish(
        ffl_db, users.operator.id, "crop_allocation", crop_allocation.id, starts_on="2026-08-01"
    )
    future = active_person_allocation_coverage(
        ffl_db, users.operator.id, crop_allocation.id, on_date="2026-07-01"
    )
    assert future.eligible is False

    repository.end_person_operating_relationship(
        ffl_db,
        repository.list_person_operating_relationships(
            ffl_db, person_id=users.operator.id, status="active"
        )[0].id,
        ends_on="2026-08-02",
        ended_by_person_id=users.manager.id,
        reason="Roster change",
    )
    ended = active_person_allocation_coverage(
        ffl_db, users.operator.id, crop_allocation.id, on_date="2026-08-03"
    )
    assert ended.eligible is False


def test_generic_person_role_or_unrelated_scope_never_grants_coverage(ffl_db, crop_allocation, users):
    unrelated_unit = repository.create_operating_unit(ffl_db, "Other unit")
    _establish(ffl_db, users.operator.id, "operating_unit", unrelated_unit.id, role="manager")

    coverage = active_person_allocation_coverage(
        ffl_db, users.operator.id, crop_allocation.id, on_date="2026-07-01"
    )

    assert coverage.eligible is False
    assert coverage.matching_scopes == ()


def test_multiple_explicit_scopes_are_returned_without_collapsing_the_relationships(
    ffl_db, crop_allocation, users,
):
    _establish(ffl_db, users.operator.id, "operating_unit", crop_allocation.operating_unit_id, role="grower")
    _establish(ffl_db, users.operator.id, "operational_block", crop_allocation.operational_block_id, role="agronomist")
    _establish(ffl_db, users.operator.id, "crop_allocation", crop_allocation.id, role="field_operator")

    coverage = active_person_allocation_coverage(
        ffl_db, users.operator.id, crop_allocation.id, on_date="2026-07-01"
    )

    assert coverage.eligible is True
    assert [(match.scope_type, match.role) for match in coverage.matching_scopes] == [
        ("crop_allocation", "field_operator"),
        ("operational_block", "agronomist"),
        ("operating_unit", "grower"),
    ]


def test_missing_relationship_table_fails_closed_without_any_context(ffl_db, crop_allocation, users):
    ffl_db.execute("DROP TABLE person_operating_relationships")
    ffl_db.commit()

    coverage = active_person_allocation_coverage(
        ffl_db, users.operator.id, crop_allocation.id, on_date="2026-07-01"
    )

    assert coverage.eligible is False
    assert coverage.allocation_id is None
    assert coverage.matching_scopes == ()


def test_bad_inputs_and_database_errors_fail_closed(ffl_db, crop_allocation, users):
    assert active_person_allocation_coverage(
        ffl_db, "", crop_allocation.id, on_date="not-a-date"
    ).eligible is False

    class BrokenConnection:
        def execute(self, *_args, **_kwargs):
            raise sqlite3.OperationalError("connection unavailable")

    assert active_person_allocation_coverage(
        BrokenConnection(), users.operator.id, crop_allocation.id, on_date="2026-07-01"
    ).eligible is False
