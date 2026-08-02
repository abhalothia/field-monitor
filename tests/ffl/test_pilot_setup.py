import pytest

from ffl.services.pilot_setup import PilotSetupValidationError, validate_up_pilot_setup


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
        "allocations": [{"block_reference": "block-a", "crop_name": "Rice", "cultivar": "Pusa 1121", "area_hectares": 2.5}],
        "location": {
            "state_name": "UP", "district_name": "Meerut", "district_context_key": "up:meerut",
            "village_name": "Field verified village", "pincode": "250001",
        },
        "first_work": {
            "title": "Inspect irrigation readiness", "owner_reference": "field",
            "due_at": "2026-08-02T08:00:00+05:30", "required_evidence": ["field photo", "water source note"],
        },
    }


def test_up_pilot_setup_normalises_a_complete_real_farm_proposal_without_writing():
    result = validate_up_pilot_setup(_proposal())

    assert result["status"] == "ready_for_human_acceptance"
    assert result["persistence"] == "not_written_by_validation"
    assert result["location"]["state_name"] == "Uttar Pradesh"
    assert result["location"]["district_context_key"] == "up:meerut"
    assert result["first_work"]["due_at"] == "2026-08-02T02:30:00+00:00"
    assert result["allocations"][0]["area_hectares"] == 2.5


@pytest.mark.parametrize(
    "change, message",
    [
        (lambda draft: draft["location"].update({"state_name": "Bihar"}), "Uttar Pradesh only"),
        (lambda draft: draft["location"].update({"district_context_key": "meerut"}), "up:<district-slug>"),
        (lambda draft: draft["allocations"][0].update({"area_hectares": 2.6}), "exceed the area"),
        (lambda draft: draft["parcels"][0].update({"right_ends_on": "2026-10-01"}), "cover the proposed active season"),
        (lambda draft: draft["first_work"].update({"required_evidence": []}), "at least one evidence"),
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
