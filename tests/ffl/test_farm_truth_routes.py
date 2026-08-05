from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from ffl.app import create_app
from ffl.persistence import repository
from tests.ffl.test_farm_truth_service import (
    _all_keys,
    _seed_candidate,
    _seed_sensitive_private_rows,
)


TOKEN = {"X-FFL-Manager-Token": "manager-secret"}


@pytest.fixture
def farm_truth_api(tmp_path):
    app = create_app(
        str(tmp_path / "farm-truth-routes.db"),
        manager_api_token="manager-secret",
    )
    with TestClient(app) as client:
        manager = repository.create_person(
            app.state.conn, "Fortune reviewer", "operations_lead"
        )
        source_owner = repository.create_person(
            app.state.conn, "TrackWick source owner", "agronomist"
        )
        app.state.manager_person_id = manager.id
        unit = repository.create_operating_unit(app.state.conn, "Fortune Farm")
        season = repository.create_season(
            app.state.conn, unit.id, "Kharif 2026", "2026-06-01", "2026-11-30"
        )
        source = repository.create_source_registry(
            app.state.conn,
            source_key="trackwick-fortune-paddy",
            display_name="TrackWick",
            source_type="trackwick",
            purpose="Private typed farm evidence",
            authority_level="partner",
            owner_id=source_owner.id,
            permitted_data_classes=["farm_candidate_context"],
            schema_version="trackwick-v3",
            mapping_version="trackwick-live-v4",
            default_coverage={},
            enabled=True,
        )
        _registration_id, _plot_id, farmer_id = _seed_candidate(
            app.state.conn, source.id, "route", open_work=1
        )
        _seed_sensitive_private_rows(
            app.state.conn, source.id, farmer_id, "visit-route-0"
        )
        yield app, client, manager, unit, season, source


def _refresh(client, unit, season):
    return client.post(
        "/api/v1/farm-truth/refresh",
        json={"operating_unit_id": unit.id, "season_id": season.id},
        headers=TOKEN,
    )


def _context(unit, season):
    return {"operating_unit_id": unit.id, "season_id": season.id}


def _acceptance(unit, season, **overrides):
    values = {
        **_context(unit, season),
        "field_name": "Village route field",
        "managed_area_hectares": 1.25,
        "crop_name": "Rice",
        "cultivar": "PB1",
        "grower_effective_on": "2026-06-01",
        "right_type": "managed",
        "right_starts_on": "2026-06-01",
        "right_ends_on": "2026-11-30",
        "field_worker_party_id": None,
    }
    values.update(overrides)
    return values


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", "/api/v1/farm-truth/refresh", {"operating_unit_id": "x", "season_id": "y"}),
        ("get", "/api/v1/farm-truth/cases?operating_unit_id=x&season_id=y", None),
        ("get", "/api/v1/farm-truth/cases/case?operating_unit_id=x&season_id=y", None),
        ("post", "/api/v1/farm-truth/cases/case/accept", {}),
        ("post", "/api/v1/farm-truth/cases/case/needs-evidence", {}),
        ("post", "/api/v1/farm-truth/cases/case/reject", {}),
    ],
)
def test_every_farm_truth_endpoint_requires_manager_authorization(
    farm_truth_api, method, path, body
):
    _app, client, _manager, _unit, _season, _source = farm_truth_api

    response = getattr(client, method)(path, json=body) if body is not None else getattr(client, method)(path)

    assert response.status_code == 403


def test_refresh_list_and_detail_return_only_allowlisted_safe_shapes(farm_truth_api):
    _app, client, _manager, unit, season, _source = farm_truth_api

    refreshed = _refresh(client, unit, season)
    listed = client.get(
        "/api/v1/farm-truth/cases",
        params={**_context(unit, season), "status": "open", "limit": 50},
        headers=TOKEN,
    )
    case_id = refreshed.json()[0]["id"]
    detail = client.get(
        f"/api/v1/farm-truth/cases/{case_id}",
        params=_context(unit, season),
        headers=TOKEN,
    )

    assert refreshed.status_code == listed.status_code == detail.status_code == 200
    assert refreshed.json() == listed.json() == [detail.json()]
    assert set(detail.json()) == {
        "id", "status", "place", "area", "registration", "crop_timing", "people", "evidence"
    }
    serialized = json.dumps([refreshed.json(), listed.json(), detail.json()])
    assert set(_all_keys(detail.json())) & {
        "source_id", "registration_id", "plot_id", "candidate_fingerprint",
        "provider_identifier", "provider_task_id", "latitude", "longitude",
        "remote_url", "raw_payload", "reviewed_by_person_id", "owner_person_id",
    } == set()
    for secret in (
        "9999999999", "111122223333", "27.951234", "78.271234",
        "secret.jpg", "Secret raw address", "unsafe raw form field",
    ):
        assert secret not in serialized


@pytest.mark.parametrize("injected", ["reviewed_by_person_id", "owner_person_id"])
@pytest.mark.parametrize("action", ["refresh", "accept", "needs-evidence", "reject"])
def test_request_bodies_cannot_set_reviewer_or_owner(farm_truth_api, action, injected):
    _app, client, manager, unit, season, _source = farm_truth_api
    case_id = _refresh(client, unit, season).json()[0]["id"]
    payloads = {
        "refresh": _context(unit, season),
        "accept": _acceptance(unit, season),
        "needs-evidence": {
            **_context(unit, season),
            "missing_evidence_kind": "plot_area",
            "reason": "Confirm surveyed area",
        },
        "reject": {**_context(unit, season), "reason": "Outside the programme"},
    }
    paths = {
        "refresh": "/api/v1/farm-truth/refresh",
        "accept": f"/api/v1/farm-truth/cases/{case_id}/accept",
        "needs-evidence": f"/api/v1/farm-truth/cases/{case_id}/needs-evidence",
        "reject": f"/api/v1/farm-truth/cases/{case_id}/reject",
    }

    response = client.post(
        paths[action], json={**payloads[action], injected: manager.id}, headers=TOKEN
    )

    assert response.status_code == 422


def test_accept_uses_manager_identity_and_returns_only_stable_canonical_ids(farm_truth_api):
    app, client, manager, unit, season, _source = farm_truth_api
    case_id = _refresh(client, unit, season).json()[0]["id"]

    accepted = client.post(
        f"/api/v1/farm-truth/cases/{case_id}/accept",
        json=_acceptance(unit, season, field_worker_party_id="worker-route"),
        headers=TOKEN,
    )
    replayed = client.post(
        f"/api/v1/farm-truth/cases/{case_id}/accept",
        json=_acceptance(unit, season, field_worker_party_id="worker-route"),
        headers=TOKEN,
    )

    assert accepted.status_code == replayed.status_code == 200
    assert accepted.json() == replayed.json()
    assert set(accepted.json()) == {
        "id", "status", "land_parcel_id", "operational_block_id",
        "crop_allocation_id", "grower_person_id", "field_worker_person_id",
    }
    assert accepted.json()["status"] == "accepted"
    assert all(accepted.json().values())
    stored = repository.get_farm_truth_case(app.state.conn, case_id)
    assert stored.reviewed_by_person_id == manager.id
    assert "worker-route" not in json.dumps(accepted.json())


@pytest.mark.parametrize(
    "overrides",
    [
        {"field_name": ""},
        {"field_name": "x" * 161},
        {"managed_area_hectares": 0},
        {"crop_name": ""},
        {"cultivar": "x" * 161},
        {"grower_effective_on": "2026-02-30"},
        {"right_starts_on": "2026-12-01", "right_ends_on": "2026-11-30"},
        {"field_worker_party_id": "unsupported-worker"},
        {"unknown": "forbidden"},
    ],
)
def test_accept_rejects_invalid_or_unsupported_inputs_without_writes(farm_truth_api, overrides):
    app, client, _manager, unit, season, _source = farm_truth_api
    case_id = _refresh(client, unit, season).json()[0]["id"]

    response = client.post(
        f"/api/v1/farm-truth/cases/{case_id}/accept",
        json=_acceptance(unit, season, **overrides),
        headers=TOKEN,
    )

    assert response.status_code == 422
    assert repository.get_farm_truth_case(app.state.conn, case_id).status == "open"
    assert app.state.conn.execute("SELECT COUNT(*) FROM land_parcels").fetchone()[0] == 0


def test_accept_validates_operating_unit_season_membership_and_effective_dates(farm_truth_api):
    app, client, _manager, unit, season, _source = farm_truth_api
    case_id = _refresh(client, unit, season).json()[0]["id"]
    other_unit = repository.create_operating_unit(app.state.conn, "Other unit")

    wrong_membership = client.post(
        f"/api/v1/farm-truth/cases/{case_id}/accept",
        json=_acceptance(other_unit, season),
        headers=TOKEN,
    )
    outside_season = client.post(
        f"/api/v1/farm-truth/cases/{case_id}/accept",
        json=_acceptance(unit, season, grower_effective_on="2027-01-01"),
        headers=TOKEN,
    )

    assert wrong_membership.status_code == outside_season.status_code == 422
    assert repository.get_farm_truth_case(app.state.conn, case_id).status == "open"


@pytest.mark.parametrize("reason", ["", "   ", "x" * 501])
@pytest.mark.parametrize("action", ["needs-evidence", "reject"])
def test_nonacceptance_decisions_require_nonempty_bounded_reasons(
    farm_truth_api, action, reason
):
    app, client, _manager, unit, season, _source = farm_truth_api
    case_id = _refresh(client, unit, season).json()[0]["id"]
    payload = {**_context(unit, season), "reason": reason}
    if action == "needs-evidence":
        payload["missing_evidence_kind"] = "plot_area"

    response = client.post(
        f"/api/v1/farm-truth/cases/{case_id}/{action}", json=payload, headers=TOKEN
    )

    assert response.status_code == 422
    assert repository.get_farm_truth_case(app.state.conn, case_id).status == "open"


def test_needs_evidence_derives_owner_and_reject_derives_reviewer(farm_truth_api):
    app, client, manager, unit, season, source = farm_truth_api
    first_case = _refresh(client, unit, season).json()[0]["id"]
    needs = client.post(
        f"/api/v1/farm-truth/cases/{first_case}/needs-evidence",
        json={
            **_context(unit, season),
            "missing_evidence_kind": "farmer_identity",
            "reason": "Confirm the grower identity",
        },
        headers=TOKEN,
    )
    _seed_candidate(app.state.conn, source.id, "reject")
    second_case = next(
        item["id"] for item in _refresh(client, unit, season).json() if item["id"] != first_case
    )
    rejected = client.post(
        f"/api/v1/farm-truth/cases/{second_case}/reject",
        json={**_context(unit, season), "reason": "Outside the programme"},
        headers=TOKEN,
    )

    assert needs.status_code == rejected.status_code == 200
    assert needs.json() == {
        "id": first_case,
        "status": "needs_evidence",
        "missing_evidence_kind": "farmer_identity",
    }
    assert rejected.json() == {"id": second_case, "status": "rejected"}
    needs_case = repository.get_farm_truth_case(app.state.conn, first_case)
    reject_case = repository.get_farm_truth_case(app.state.conn, second_case)
    assert needs_case.owner_person_id == needs_case.reviewed_by_person_id == manager.id
    assert reject_case.reviewed_by_person_id == manager.id


@pytest.mark.parametrize("terminal_action", ["claim", "needs", "reject"])
@pytest.mark.parametrize("decision", ["accept", "needs-evidence", "reject"])
def test_decisions_return_conflict_for_claimed_or_terminal_cases(
    farm_truth_api, terminal_action, decision
):
    app, client, manager, unit, season, _source = farm_truth_api
    case_id = _refresh(client, unit, season).json()[0]["id"]
    if terminal_action == "claim":
        repository.claim_farm_truth_case(app.state.conn, case_id)
        app.state.conn.commit()
    elif terminal_action == "needs":
        repository.mark_farm_truth_case_needs_evidence(
            app.state.conn, case_id, manager.id, "plot_area", "Confirm area"
        )
    else:
        repository.mark_farm_truth_case_rejected(
            app.state.conn, case_id, manager.id, "Outside programme"
        )
    payload = {
        "accept": _acceptance(unit, season),
        "needs-evidence": {
            **_context(unit, season), "missing_evidence_kind": "plot_area", "reason": "Confirm area"
        },
        "reject": {**_context(unit, season), "reason": "Outside programme"},
    }[decision]

    response = client.post(
        f"/api/v1/farm-truth/cases/{case_id}/{decision}", json=payload, headers=TOKEN
    )

    assert response.status_code == 409


def test_decisions_return_conflict_when_open_case_is_stale(farm_truth_api):
    app, client, _manager, unit, season, _source = farm_truth_api
    case_id = _refresh(client, unit, season).json()[0]["id"]
    app.state.conn.execute(
        "UPDATE trackwick_visits SET observed_at = '2026-05-01T00:00:00+00:00' "
        "WHERE task_id = 'visit-route-0'"
    )
    app.state.conn.commit()
    assert _refresh(client, unit, season).json() == []

    for decision, payload in (
        ("accept", _acceptance(unit, season)),
        (
            "needs-evidence",
            {**_context(unit, season), "missing_evidence_kind": "plot_area", "reason": "Confirm area"},
        ),
        ("reject", {**_context(unit, season), "reason": "Outside programme"}),
    ):
        response = client.post(
            f"/api/v1/farm-truth/cases/{case_id}/{decision}", json=payload, headers=TOKEN
        )
        assert response.status_code == 409
