import sqlite3

import pytest

from ffl.persistence import repository


@pytest.fixture
def fields(ffl_db, crop_allocation):
    first = type("Field", (), {"id": crop_allocation.operational_block_id})()
    second = repository.create_operational_block(
        ffl_db, crop_allocation.operating_unit_id, "South Block", 2.0,
    )
    return [first, second]


@pytest.fixture
def farm(ffl_db, users, crop_allocation, fields):
    result = repository.create_farm(
        ffl_db, crop_allocation.operating_unit_id, "FFL Pilot", users.manager.id,
    )
    for field in fields:
        repository.assign_field_to_farm(
            ffl_db, result.id, field.id, "2026-08-06", users.manager.id,
        )
    return result


def _insert_person(conn, identifier="manager"):
    conn.execute(
        "INSERT INTO people (id, name, role, created_at) VALUES (?, ?, ?, ?)",
        (identifier, "Farm Manager", "farm_manager", "2026-08-06T00:00:00+00:00"),
    )


def _insert_operating_unit(conn, identifier):
    conn.execute(
        "INSERT INTO operating_units (id, name, created_at) VALUES (?, ?, ?)",
        (identifier, identifier, "2026-08-06T00:00:00+00:00"),
    )


def _insert_farm(conn, identifier, operating_unit_id, reviewer_id="manager"):
    conn.execute(
        """INSERT INTO farms
           (id, operating_unit_id, name, status, reviewed_by_person_id, created_at)
           VALUES (?, ?, ?, 'active', ?, ?)""",
        (identifier, operating_unit_id, identifier, reviewer_id, "2026-08-06T00:00:00+00:00"),
    )


def _insert_field(conn, identifier, operating_unit_id):
    conn.execute(
        """INSERT INTO operational_blocks
           (id, operating_unit_id, name, area_hectares, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (identifier, operating_unit_id, identifier, 1.5, "2026-08-06T00:00:00+00:00"),
    )


def _assign(conn, identifier, farm_id, field_id, status="active", ends_on=None):
    conn.execute(
        """INSERT INTO farm_fields
           (id, farm_id, operational_block_id, starts_on, ends_on, status,
            reviewed_by_person_id, created_at)
           VALUES (?, ?, ?, '2026-08-06', ?, ?, 'manager', '2026-08-06T00:00:00+00:00')""",
        (identifier, farm_id, field_id, ends_on, status),
    )


def test_farm_has_many_fields_but_field_has_one_active_farm(ffl_db):
    _insert_person(ffl_db)
    _insert_operating_unit(ffl_db, "unit")
    _insert_farm(ffl_db, "farm", "unit")
    _insert_farm(ffl_db, "other-farm", "unit")
    _insert_field(ffl_db, "north-1", "unit")
    _insert_field(ffl_db, "north-2", "unit")

    _assign(ffl_db, "farm-field-1", "farm", "north-1")
    _assign(ffl_db, "farm-field-2", "farm", "north-2")

    rows = ffl_db.execute(
        "SELECT operational_block_id FROM farm_fields WHERE farm_id = ? AND status = 'active' ORDER BY id",
        ("farm",),
    ).fetchall()
    assert [row["operational_block_id"] for row in rows] == ["north-1", "north-2"]
    with pytest.raises(sqlite3.IntegrityError):
        _assign(ffl_db, "duplicate-active-field", "other-farm", "north-1")


def test_ended_membership_allows_reassignment_and_cross_unit_membership_is_rejected(ffl_db):
    _insert_person(ffl_db)
    _insert_operating_unit(ffl_db, "north-unit")
    _insert_operating_unit(ffl_db, "south-unit")
    _insert_farm(ffl_db, "north-farm", "north-unit")
    _insert_farm(ffl_db, "south-farm", "south-unit")
    _insert_field(ffl_db, "north-field", "north-unit")

    _assign(ffl_db, "ended-membership", "north-farm", "north-field", "ended", "2026-08-07")
    _assign(ffl_db, "current-membership", "north-farm", "north-field")

    with pytest.raises(sqlite3.IntegrityError, match="same operating unit"):
        _assign(ffl_db, "cross-unit-membership", "south-farm", "north-field")


def test_field_worker_and_farmer_can_each_span_many_fields(ffl_db, users, farm, fields, crop_allocation):
    worker = repository.create_person(ffl_db, "Nisha Field Worker", "field_operator")
    farmer = repository.create_person(ffl_db, "Ravi Farmer", "grower")

    repository.create_person_operating_relationship(
        ffl_db, worker.id, "operational_block", fields[0].id, "field_operator",
        "2026-08-06", reviewed_by_person_id=users.manager.id,
    )
    repository.create_person_operating_relationship(
        ffl_db, farmer.id, "crop_allocation", crop_allocation.id, "grower",
        "2026-08-06", reviewed_by_person_id=users.manager.id,
    )

    members = repository.list_people_for_farm(ffl_db, farm.id)
    assert {(item.name, item.role) for item in members} == {
        ("Nisha Field Worker", "field_operator"), ("Ravi Farmer", "grower"),
    }


def test_ending_a_membership_hides_its_field_and_allows_a_reassignment(
    ffl_db, users, farm, fields,
):
    active = repository.list_active_farm_fields(ffl_db, farm.id)
    ending = next(item for item in active if item.operational_block_id == fields[1].id)

    ended = repository.end_farm_field_assignment(
        ffl_db, ending.id, "2026-08-07", users.manager.id,
    )

    assert ended.status == "ended"
    assert ended.ends_on == "2026-08-07"
    assert [item.operational_block_id for item in repository.list_active_farm_fields(ffl_db, farm.id)] == [
        fields[0].id,
    ]
    reassigned = repository.assign_field_to_farm(
        ffl_db, farm.id, fields[1].id, "2026-08-08", users.manager.id,
    )
    assert reassigned.status == "active"


def test_farm_people_excludes_unreviewed_and_ended_relationships(
    ffl_db, users, farm, fields, crop_allocation,
):
    unreviewed = repository.create_person(ffl_db, "Unreviewed Worker", "field_operator")
    ended = repository.create_person(ffl_db, "Former Grower", "grower")
    reviewed = repository.create_person(ffl_db, "Reviewed Grower", "grower")
    repository.create_person_operating_relationship(
        ffl_db, unreviewed.id, "operational_block", fields[0].id, "field_operator",
        "2026-08-06", provenance="source:trackwick",
    )
    repository.create_person_operating_relationship(
        ffl_db, ended.id, "crop_allocation", crop_allocation.id, "grower",
        "2026-08-06", ends_on="2026-08-07", reviewed_by_person_id=users.manager.id,
    )
    repository.create_person_operating_relationship(
        ffl_db, reviewed.id, "crop_allocation", crop_allocation.id, "grower",
        "2026-08-06", reviewed_by_person_id=users.manager.id,
    )

    assert [(item.name, item.role) for item in repository.list_people_for_farm(ffl_db, farm.id)] == [
        ("Reviewed Grower", "grower"),
    ]
