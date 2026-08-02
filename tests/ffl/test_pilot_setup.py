import copy

import pytest

from ffl.services.pilot_setup import (
    PilotSetupValidationError,
    accept_up_pilot_setup,
    validate_quick_start,
    validate_up_pilot_setup,
)


def _proposal():
    return {
        "farm_name": "Fortune UP Pilot",
        "people": [
            {"reference": "manager", "name": "Farm Manager", "role": "farm_manager"},
            {"reference": "field", "name": "Field Operator", "role": "field_operator"},
        ],
        "parcels": [{
            "reference": "parcel-a", "name": "North parcel", "area_hectares": 2.5,
            "right_type": "lease", "right_starts_on": "2026-06-01", "right_ends_on": "2026-11-30",
        }],
        "blocks": [{
            "reference": "block-a", "name": "North block", "area_hectares": 2.5,
            "parcel_references": ["parcel-a"],
        }],
        "season": {"name": "Kharif 2026", "starts_on": "2026-06-01", "ends_on": "2026-11-30"},
        "allocations": [{
            "reference": "rice-2026", "block_reference": "block-a", "crop_name": "Rice",
            "cultivar": "Pusa 1121", "area_hectares": 2.5,
        }],
        "location": {
            "state_name": "UP", "district_name": "Meerut", "district_context_key": "up:meerut",
            "village_name": "Field verified village", "pincode": "250001",
            "verified_at": "2026-08-01T07:30:00+05:30",
        },
        "first_work": {
            "title": "Inspect irrigation readiness", "owner_reference": "field",
            "allocation_reference": "rice-2026", "due_at": "2026-08-02T08:00:00+05:30",
            "required_evidence": ["field photo", "water source note"],
        },
    }


def test_up_pilot_setup_normalises_a_complete_real_farm_proposal_without_writing():
    result = validate_up_pilot_setup(_proposal())

    assert result["status"] == "ready_for_human_acceptance"
    assert result["persistence"] == "not_written_by_validation"
    assert result["location"]["state_name"] == "Uttar Pradesh"
    assert result["location"]["district_context_key"] == "up:meerut"
    assert result["location"]["verified_at"] == "2026-08-01T02:00:00+00:00"
    assert result["first_work"]["due_at"] == "2026-08-02T02:30:00+00:00"
    assert result["first_work"]["allocation_reference"] == "rice-2026"
    assert result["allocations"][0]["area_hectares"] == 2.5


def test_quick_start_only_checks_the_few_facts_needed_to_begin():
    result = validate_quick_start({
        "farm_name": "Fortune UP Pilot",
        "manager_name": "Farm Manager",
        "field_name": "North block",
        "crop_name": "Pusa basmati",
        "area_hectares": 2.5,
        "state_name": "UP",
        "district_name": "Meerut",
        "pincode": "250001",
    })

    assert result["farm"] == {"name": "Fortune UP Pilot"}
    assert result["field"]["name"] == "North block"
    assert result["location"] == {
        "state_name": "Uttar Pradesh",
        "district_name": "Meerut",
        "village_name": None,
        "pincode": "250001",
    }
    assert result["writes"] is False
    assert "land or operating right" in result["still_needed_before_acceptance"][0]


@pytest.mark.parametrize(
    "change, message",
    [
        (lambda draft: draft.pop("village_name"), "village or PIN"),
        (lambda draft: draft.update({"pincode": "2500"}), "six-digit"),
        (lambda draft: draft.update({"area_hectares": 0}), "finite positive"),
        (lambda draft: draft.update({"state_name": "Bihar"}), "Uttar Pradesh only"),
    ],
)
def test_quick_start_rejects_missing_or_unsafe_basics(change, message):
    draft = {
        "farm_name": "Fortune UP Pilot",
        "manager_name": "Farm Manager",
        "field_name": "North block",
        "crop_name": "Pusa basmati",
        "area_hectares": 2.5,
        "state_name": "Uttar Pradesh",
        "district_name": "Meerut",
        "village_name": "Kheri",
    }
    change(draft)

    with pytest.raises(PilotSetupValidationError, match=message):
        validate_quick_start(draft)


@pytest.mark.parametrize(
    "change, message",
    [
        (lambda draft: draft["location"].update({"state_name": "Bihar"}), "Uttar Pradesh only"),
        (lambda draft: draft["location"].update({"district_context_key": "meerut"}), "up:<district-slug>"),
        (lambda draft: draft["allocations"][0].update({"area_hectares": 2.6}), "exceed the area"),
        (lambda draft: draft["parcels"][0].update({"right_ends_on": "2026-10-01"}), "cover the proposed active season"),
        (lambda draft: draft["first_work"].update({"required_evidence": []}), "at least one evidence"),
        (lambda draft: draft["first_work"].update({"allocation_reference": "missing"}), "proposed allocation"),
        (lambda draft: draft["location"].pop("verified_at"), "location.verified_at"),
    ],
)
def test_up_pilot_setup_refuses_unsafe_or_incomplete_proposals(change, message):
    draft = _proposal()
    change(draft)

    with pytest.raises(PilotSetupValidationError, match=message):
        validate_up_pilot_setup(draft)


def test_up_pilot_setup_route_only_validates_and_never_creates_a_farm(tmp_path):
    from fastapi.testclient import TestClient

    from ffl.app import create_app

    with TestClient(create_app(str(tmp_path / "validation.db"))) as client:
        response = client.post("/api/v1/pilot/setup/validate", json=_proposal())

        assert response.status_code == 200
        assert response.json()["persistence"] == "not_written_by_validation"
        assert client.get("/api/v1/pilot/readiness").json()["counts"]["operating_units"] == 0


def test_quick_start_route_writes_nothing(tmp_path):
    from fastapi.testclient import TestClient

    from ffl.app import create_app

    payload = {
        "farm_name": "Fortune UP Pilot",
        "manager_name": "Farm Manager",
        "field_name": "North block",
        "crop_name": "Pusa basmati",
        "area_hectares": 2.5,
        "state_name": "UP",
        "district_name": "Meerut",
        "village_name": "Kheri",
    }
    with TestClient(create_app(str(tmp_path / "quick-start.db"))) as client:
        response = client.post("/api/v1/pilot/quick-start/validate", json=payload)

        assert response.status_code == 200
        assert response.json()["writes"] is False
        assert client.get("/api/v1/pilot/readiness").json()["counts"]["operating_units"] == 0


def test_up_pilot_setup_acceptance_is_atomic_and_idempotent(tmp_path):
    from fastapi.testclient import TestClient

    from ffl.app import create_app

    app = create_app(
        str(tmp_path / "acceptance.db"),
        pilot_setup_approval_token="setup-approval-test",
    )
    payload = _proposal()
    payload.update({"idempotency_key": "up-pilot-setup-0001", "approving_manager_reference": "manager"})
    with TestClient(app) as client:
        denied = client.post("/api/v1/pilot/setup/accept", json=payload)
        assert denied.status_code == 403

        accepted = client.post(
            "/api/v1/pilot/setup/accept",
            json=payload,
            headers={"x-ffl-pilot-setup-approval": "setup-approval-test"},
        )
        assert accepted.status_code == 201
        accepted_body = accepted.json()
        assert accepted_body["status"] == "accepted"
        assert accepted_body["idempotent"] is False

        replay = client.post(
            "/api/v1/pilot/setup/accept",
            json=payload,
            headers={"x-ffl-pilot-setup-approval": "setup-approval-test"},
        )
        assert replay.status_code == 200
        assert replay.json() == {**accepted_body, "idempotent": True}

        connection = app.state.conn
        assert connection.execute("SELECT COUNT(*) FROM operating_units").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM people").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM rights_to_operate").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM crop_allocations").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM pilot_setup_acceptances").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM pilot_setup_bootstrap_guard").fetchone()[0] == 1
        location = connection.execute("SELECT verified_at FROM operating_unit_locations").fetchone()
        assert location["verified_at"] == "2026-08-01T02:00:00+00:00"
        work = connection.execute("SELECT status FROM work_items").fetchone()
        assert work["status"] == "planned"
        audit = connection.execute("SELECT actor_id, reason FROM audit_events").fetchone()
        assert audit["actor_id"] == accepted_body["manager_person_id"]
        assert audit["reason"] == "bootstrap_setup_accepted"


def test_up_pilot_setup_rejects_changed_replay_and_any_second_first_farm(tmp_path):
    from ffl.persistence.database import open_connection
    from ffl.persistence.schema import create_schema

    connection = open_connection(str(tmp_path / "second-acceptance.db"))
    create_schema(connection)
    proposal = _proposal()
    first = accept_up_pilot_setup(
        connection, proposal, idempotency_key="up-pilot-setup-0002", approving_manager_reference="manager"
    )
    changed = copy.deepcopy(proposal)
    changed["farm_name"] = "A different farm"
    with pytest.raises(PilotSetupValidationError, match="idempotency key"):
        accept_up_pilot_setup(
            connection, changed, idempotency_key="up-pilot-setup-0002", approving_manager_reference="manager"
        )
    with pytest.raises(PilotSetupValidationError, match="already been accepted"):
        accept_up_pilot_setup(
            connection, proposal, idempotency_key="up-pilot-setup-0003", approving_manager_reference="manager"
        )
    assert connection.execute("SELECT COUNT(*) FROM operating_units").fetchone()[0] == 1
    assert connection.execute("SELECT COUNT(*) FROM pilot_setup_acceptances").fetchone()[0] == 1
    assert first["idempotent"] is False
