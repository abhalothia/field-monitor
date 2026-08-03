"""Focused tests for the time-bounded person operating relationship spine."""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ffl.app import create_app
from ffl.persistence import repository
from ffl.persistence.schema import create_schema
from ffl.seed import seed_pilot
from ffl.services import relationships


def _scope_records(conn):
    unit = repository.create_operating_unit(conn, "Relationship Farm")
    parcel = repository.create_land_parcel(conn, unit.id, "Survey Parcel A", 4.0)
    block = repository.create_operational_block(conn, unit.id, "North Block", 4.0)
    season = repository.create_season(conn, unit.id, "Kharif 2026", "2026-06-01", "2026-11-30")
    allocation = repository.create_crop_allocation(
        conn, unit.id, block.id, season.id, "Rice", "Pusa 1121", 4.0
    )
    person = repository.create_person(conn, "Asha Grower", "field_operator")
    reviewer = repository.create_person(conn, "Farm Manager", "farm_manager")
    return unit, parcel, block, allocation, person, reviewer


def test_sqlite_schema_adds_relationship_table_when_an_existing_preview_reopens(ffl_db):
    # The fixture already created the legacy preview schema. Re-running the
    # schema bootstrap must add this new isolated table without rebuilding the
    # established operating records.
    unit = repository.create_operating_unit(ffl_db, "Existing Preview Farm")

    create_schema(ffl_db)

    columns = {row["name"] for row in ffl_db.execute("PRAGMA table_info(person_operating_relationships)")}
    assert {"person_id", "scope_type", "role", "starts_on", "ends_on", "provenance"} <= columns
    assert repository.get_operating_unit(ffl_db, unit.id) == unit


@pytest.mark.parametrize(
    ("scope_type", "scope_index"),
    [
        ("operating_unit", 0),
        ("land_parcel", 1),
        ("operational_block", 2),
        ("crop_allocation", 3),
    ],
)
def test_relationship_links_one_existing_scope_with_reviewed_history(ffl_db, scope_type, scope_index):
    scopes = _scope_records(ffl_db)
    person, reviewer = scopes[4:]
    scope = scopes[scope_index]

    relationship = repository.create_person_operating_relationship(
        ffl_db, person.id, scope_type, scope.id, "grower", "2026-06-01",
        provenance="reviewed field-register import", reviewed_by_person_id=reviewer.id,
    )

    assert relationship.scope_type == scope_type
    assert relationships.relationship_scope_id(relationship) == scope.id
    assert relationship.status == "active"
    assert relationship.ends_on is None
    assert relationship.reviewed_by_person_id == reviewer.id
    assert sum(value is not None for value in (
        relationship.operating_unit_id,
        relationship.land_parcel_id,
        relationship.operational_block_id,
        relationship.crop_allocation_id,
    )) == 1


def test_database_requires_exactly_one_matching_scope_and_review_or_provenance(ffl_db):
    unit, parcel, _block, _allocation, person, reviewer = _scope_records(ffl_db)
    with pytest.raises(sqlite3.IntegrityError):
        ffl_db.execute(
            """INSERT INTO person_operating_relationships (
                id, person_id, scope_type, operating_unit_id, land_parcel_id, role,
                starts_on, status, reviewed_by_person_id, created_at
            ) VALUES (?, ?, 'operating_unit', ?, ?, 'grower', '2026-06-01', 'active', ?, ?)""",
            ("two-scopes", person.id, unit.id, parcel.id, reviewer.id, "2026-06-01T00:00:00+00:00"),
        )
    with pytest.raises(sqlite3.IntegrityError):
        ffl_db.execute(
            """INSERT INTO person_operating_relationships (
                id, person_id, scope_type, operating_unit_id, role, starts_on, status, created_at
            ) VALUES (?, ?, 'operating_unit', ?, 'grower', '2026-06-01', 'active', ?)""",
            ("unreviewed", person.id, unit.id, "2026-06-01T00:00:00+00:00"),
        )


def test_relationship_validates_dates_people_scope_role_and_active_duplicate(ffl_db):
    unit, _parcel, _block, allocation, person, reviewer = _scope_records(ffl_db)

    with pytest.raises(ValueError, match="person does not exist"):
        repository.create_person_operating_relationship(
            ffl_db, "missing", "operating_unit", unit.id, "grower", "2026-06-01", provenance="register"
        )
    with pytest.raises(ValueError, match="scope does not exist"):
        repository.create_person_operating_relationship(
            ffl_db, person.id, "crop_allocation", "missing", "grower", "2026-06-01", provenance="register"
        )
    with pytest.raises(ValueError, match="ends_on must be on or after"):
        repository.create_person_operating_relationship(
            ffl_db, person.id, "crop_allocation", allocation.id, "grower", "2026-06-02",
            ends_on="2026-06-01", provenance="register"
        )
    with pytest.raises(ValueError, match="role must be"):
        repository.create_person_operating_relationship(
            ffl_db, person.id, "crop_allocation", allocation.id, "owner", "2026-06-01", provenance="register"
        )
    with pytest.raises(ValueError, match="provenance or reviewed_by_person_id"):
        repository.create_person_operating_relationship(
            ffl_db, person.id, "crop_allocation", allocation.id, "grower", "2026-06-01"
        )

    first = repository.create_person_operating_relationship(
        ffl_db, person.id, "crop_allocation", allocation.id, "grower", "2026-06-01",
        reviewed_by_person_id=reviewer.id,
    )
    with pytest.raises(ValueError, match="active relationship already exists"):
        repository.create_person_operating_relationship(
            ffl_db, person.id, "crop_allocation", allocation.id, "grower", "2026-06-02",
            reviewed_by_person_id=reviewer.id,
        )
    assert repository.get_person_operating_relationship(ffl_db, first.id) == first


def test_end_transition_preserves_relationship_history_and_records_audit(ffl_db):
    _unit, _parcel, _block, allocation, person, reviewer = _scope_records(ffl_db)
    original = repository.create_person_operating_relationship(
        ffl_db, person.id, "crop_allocation", allocation.id, "grower", "2026-06-01",
        reviewed_by_person_id=reviewer.id,
    )

    ended = repository.end_person_operating_relationship(
        ffl_db, original.id, "2026-11-30", reviewer.id, "contract period complete"
    )
    replacement = repository.create_person_operating_relationship(
        ffl_db, person.id, "crop_allocation", allocation.id, "grower", "2026-12-01",
        reviewed_by_person_id=reviewer.id,
    )

    assert ended.id == original.id
    assert ended.status == "ended"
    assert ended.ends_on == "2026-11-30"
    assert ended.ended_by_person_id == reviewer.id
    assert ended.ended_at is not None
    assert replacement.status == "active"
    assert [item.id for item in repository.list_person_operating_relationships(
        ffl_db, person_id=person.id, scope_type="crop_allocation", scope_id=allocation.id
    )] == [replacement.id, original.id]
    audit = repository.list_audit_events(ffl_db, "person_operating_relationship", original.id)
    assert [(event.from_status, event.to_status, event.actor_id, event.reason) for event in audit] == [
        ("active", "ended", reviewer.id, "contract period complete")
    ]
    with pytest.raises(ValueError, match="only an active"):
        repository.end_person_operating_relationship(
            ffl_db, original.id, "2026-12-01", reviewer.id, "cannot end twice"
        )


def test_service_uses_server_derived_manager_as_the_reviewer(ffl_db):
    unit, _parcel, _block, _allocation, person, reviewer = _scope_records(ffl_db)

    relationship = relationships.establish_person_operating_relationship(
        ffl_db, person.id, "operating_unit", unit.id, "grower", "2026-06-01", reviewer.id
    )

    assert relationship.reviewed_by_person_id == reviewer.id
    assert relationships.relationship_summary(relationship)["scope_id"] == unit.id


def test_manager_routes_fail_closed_and_do_not_accept_a_caller_supplied_reviewer(tmp_path: Path):
    app = create_app(str(tmp_path / "relationships.db"), manager_api_token="manager-secret")
    with TestClient(app) as client:
        seed = seed_pilot(app.state.conn)
        app.state.manager_person_id = seed["manager_id"]
        grower = repository.create_person(app.state.conn, "Asha Grower", "field_operator")
        payload = {
            "person_id": grower.id,
            "scope_type": "crop_allocation",
            "scope_id": seed["allocation_id"],
            "role": "grower",
            "starts_on": "2026-06-01",
            "provenance": "reviewed contract register",
        }
        assert client.post("/api/v1/person-operating-relationships", json=payload).status_code == 403

        forbidden_reviewer = client.post(
            "/api/v1/person-operating-relationships",
            json={**payload, "reviewed_by_person_id": grower.id},
            headers={"X-FFL-Manager-Token": "manager-secret"},
        )
        assert forbidden_reviewer.status_code == 422

        created = client.post(
            "/api/v1/person-operating-relationships", json=payload,
            headers={"X-FFL-Manager-Token": "manager-secret"},
        )
        assert created.status_code == 201
        relationship = created.json()
        assert relationship["reviewed_by_person_id"] == seed["manager_id"]
        assert relationship["scope_id"] == seed["allocation_id"]
        assert relationship["status"] == "active"

        listed = client.get(
            "/api/v1/person-operating-relationships",
            params={"scope_type": "crop_allocation", "scope_id": seed["allocation_id"]},
            headers={"X-FFL-Manager-Token": "manager-secret"},
        )
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()] == [relationship["id"]]

        ended = client.post(
            "/api/v1/person-operating-relationships/{}/end".format(relationship["id"]),
            json={"ends_on": "2026-11-30", "reason": "season closed"},
            headers={"X-FFL-Manager-Token": "manager-secret"},
        )
        assert ended.status_code == 200
        assert ended.json()["ended_by_person_id"] == seed["manager_id"]

        detail = client.get(
            "/api/v1/person-operating-relationships/{}".format(relationship["id"]),
            headers={"X-FFL-Manager-Token": "manager-secret"},
        )
        assert detail.status_code == 200
        assert detail.json()["audit_events"][0]["to_status"] == "ended"
        assert client.delete(
            "/api/v1/person-operating-relationships/{}".format(relationship["id"]),
            headers={"X-FFL-Manager-Token": "manager-secret"},
        ).status_code == 405
