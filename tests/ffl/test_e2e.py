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


@pytest.fixture
def client(tmp_path: Path):
    app = create_app(str(tmp_path / "ffl.db"))
    with TestClient(app) as test_client:
        yield test_client


def test_golden_exception_resolution_loop(seeded_client):
    payload = {
        "allocation_id": seeded_client.seed["allocation_id"],
        "title": "Irrigation drainage issue",
        "severity": "high",
        "owner_id": seeded_client.seed["manager_id"],
        "fallback_owner_id": seeded_client.seed["lead_id"],
        "observed_at": "2026-07-10T08:00:00+00:00",
        "idempotency_key": "E-001",
    }
    reported = seeded_client.client.post("/api/v1/exceptions", json=payload).json()

    for status, actor, reason in [
        ("triaged", seeded_client.seed["manager_id"], "priority confirmed"),
        ("owned", seeded_client.seed["manager_id"], "manager assigned"),
        ("mitigated", seeded_client.seed["operator_id"], "drainage cleared"),
        ("monitoring", seeded_client.seed["manager_id"], "follow-up scheduled"),
        ("resolved", seeded_client.seed["manager_id"], "follow-up passed"),
    ]:
        response = seeded_client.client.post(
            "/api/v1/exceptions/{}/transitions".format(reported["id"]),
            json={"status": status, "actor_id": actor, "reason": reason},
        )
        assert response.status_code == 200

    detail = seeded_client.client.get("/api/v1/exceptions/{}".format(reported["id"])).json()

    assert detail["status"] == "resolved"
    assert [event["to_status"] for event in detail["audit_events"]] == [
        "triaged", "owned", "mitigated", "monitoring", "resolved"
    ]


def test_field_and_manager_surfaces_are_served(client):
    assert client.get("/field").status_code == 200
    assert "अपवाद दर्ज करें" in client.get("/field").text
    assert client.get("/manager").status_code == 200
    assert "Today." in client.get("/manager").text
    assert client.get("/assets/field.css").status_code == 200
    assert client.get("/field-service-worker.js").status_code == 200
    assert client.get("/assets/manager.js").status_code == 200
