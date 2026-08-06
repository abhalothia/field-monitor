import sqlite3

import pytest


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
