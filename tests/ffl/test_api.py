from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from ffl.app import create_app
from ffl.seed import seed_pilot


@pytest.fixture
def seeded_client(tmp_path: Path):
    app = create_app(str(tmp_path / "ffl.db"))
    connection = app.state.conn
    with TestClient(app) as client:
        seed = seed_pilot(connection)
        yield SimpleNamespace(client=client, seed=seed)

    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        connection.execute("SELECT 1")


def test_runtime_returns_seeded_pilot_state(seeded_client):
    response = seeded_client.client.get("/api/v1/runtime")

    assert response.status_code == 200
    payload = response.json()
    assert payload["operating_unit"]["id"] == seeded_client.seed["operating_unit_id"]
    assert payload["allocations"][0]["id"] == seeded_client.seed["allocation_id"]
    assert payload["work_items"]
    assert payload["exceptions"] == []


def test_exception_post_is_idempotent(seeded_client):
    payload = {
        "allocation_id": seeded_client.seed["allocation_id"],
        "title": "Water pooling in north edge",
        "severity": "high",
        "owner_id": seeded_client.seed["manager_id"],
        "fallback_owner_id": seeded_client.seed["lead_id"],
        "observed_at": "2026-07-10T08:00:00+00:00",
        "idempotency_key": "field-device-1:submission-2",
    }

    first = seeded_client.client.post("/api/v1/exceptions", json=payload)
    replay = seeded_client.client.post("/api/v1/exceptions", json=payload)

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.json()["id"] == first.json()["id"]


def test_invalid_work_transition_returns_422(seeded_client):
    work_id = seeded_client.client.get("/api/v1/runtime").json()["work_items"][0]["id"]

    response = seeded_client.client.post(
        "/api/v1/work-items/{}/transitions".format(work_id),
        json={"status": "accepted", "actor_id": seeded_client.seed["manager_id"], "reason": "reviewed"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "invalid work transition"


def test_exception_detail_and_transition_include_audit_events(seeded_client):
    reported = seeded_client.client.post(
        "/api/v1/exceptions",
        json={
            "allocation_id": seeded_client.seed["allocation_id"],
            "title": "Water pooling in north edge",
            "severity": "high",
            "owner_id": seeded_client.seed["manager_id"],
            "fallback_owner_id": seeded_client.seed["lead_id"],
            "observed_at": "2026-07-10T08:00:00+00:00",
            "idempotency_key": "field-device-1:submission-3",
        },
    ).json()

    transition = seeded_client.client.post(
        "/api/v1/exceptions/{}/transitions".format(reported["id"]),
        json={"status": "triaged", "actor_id": seeded_client.seed["manager_id"], "reason": "reviewed"},
    )
    detail = seeded_client.client.get("/api/v1/exceptions/{}".format(reported["id"]))

    assert transition.status_code == 200
    assert transition.json()["status"] == "triaged"
    assert detail.status_code == 200
    assert [event["to_status"] for event in detail.json()["audit_events"]] == ["triaged"]
