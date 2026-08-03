"""HTTP tests for the manager-owned field request boundary."""

from fastapi.testclient import TestClient

from ffl.app import create_app
from ffl.persistence import repository
from ffl.seed import seed_pilot
from ffl.services import relationships


def _request_payload(allocation_id: str, target_person_id: str) -> dict:
    return {
        "allocation_id": allocation_id,
        "target_person_id": target_person_id,
        "request_kind": "field_check",
        "evidence_required": True,
        "due_at": "2026-08-10T09:00:00+05:30",
        "request_copy_en": "Please inspect the field and send one photo before 9 AM.",
        "request_copy_hi": "कृपया खेत देखें और सुबह 9 बजे से पहले एक फोटो भेजें।",
        "idempotency_key": "coo-coverage-recovery:0001",
    }


def test_request_routes_are_manager_only_scoped_and_never_dispatch(tmp_path):
    app = create_app(str(tmp_path / "field-requests.db"), manager_api_token="manager-secret")
    with TestClient(app) as client:
        seed = seed_pilot(app.state.conn)
        app.state.manager_person_id = seed["manager_id"]
        operator = repository.create_person(app.state.conn, "Asha Field Officer", "field_operator")
        payload = _request_payload(seed["allocation_id"], operator.id)
        original_work_count = app.state.conn.execute("SELECT COUNT(*) FROM work_items").fetchone()[0]

        assert client.post("/api/v1/field-information-requests", json=payload).status_code == 403

        headers = {"X-FFL-Manager-Token": "manager-secret"}
        unscoped = client.post("/api/v1/field-information-requests", json=payload, headers=headers)
        assert unscoped.status_code == 422
        assert "active explicit relationship" in unscoped.json()["detail"]

        relationships.establish_person_operating_relationship(
            app.state.conn, operator.id, "crop_allocation", seed["allocation_id"], "field_operator",
            "2026-06-01", seed["manager_id"], provenance="reviewed Fortune field roster",
        )
        created = client.post("/api/v1/field-information-requests", json=payload, headers=headers)
        assert created.status_code == 201
        request_id = created.json()["id"]
        assert created.json()["status"] == "draft"
        assert created.json()["initiated_by_person_id"] == seed["manager_id"]
        assert created.json()["status"] != "dispatched"
        assert app.state.conn.execute("SELECT COUNT(*) FROM communication_deliveries").fetchone()[0] == 0

        replay = client.post("/api/v1/field-information-requests", json=payload, headers=headers)
        assert replay.status_code == 201
        assert replay.json()["id"] == request_id
        assert app.state.conn.execute("SELECT COUNT(*) FROM field_information_requests").fetchone()[0] == 1

        ready = client.post("/api/v1/field-information-requests/{}/ready".format(request_id), headers=headers)
        assert ready.status_code == 200
        assert ready.json()["status"] == "ready"

        detail = client.get("/api/v1/field-information-requests/{}".format(request_id), headers=headers)
        assert detail.status_code == 200
        assert [event["to_status"] for event in detail.json()["events"]] == ["draft", "ready"]
        assert app.state.conn.execute("SELECT COUNT(*) FROM field_signals").fetchone()[0] == 0
        assert app.state.conn.execute("SELECT COUNT(*) FROM work_items").fetchone()[0] == original_work_count


def test_request_ready_rechecks_current_scope_and_cancellation_is_append_only(tmp_path):
    app = create_app(str(tmp_path / "field-requests-scope.db"), manager_api_token="manager-secret")
    with TestClient(app) as client:
        seed = seed_pilot(app.state.conn)
        app.state.manager_person_id = seed["manager_id"]
        operator = repository.create_person(app.state.conn, "Asha Field Officer", "field_operator")
        relationship = relationships.establish_person_operating_relationship(
            app.state.conn, operator.id, "crop_allocation", seed["allocation_id"], "field_operator",
            "2026-06-01", seed["manager_id"], provenance="reviewed Fortune field roster",
        )
        headers = {"X-FFL-Manager-Token": "manager-secret"}
        created = client.post(
            "/api/v1/field-information-requests",
            json=_request_payload(seed["allocation_id"], operator.id), headers=headers,
        )
        request_id = created.json()["id"]
        relationships.end_person_operating_relationship(
            app.state.conn, relationship.id, "2026-08-01", seed["manager_id"], "reassigned"
        )

        denied = client.post("/api/v1/field-information-requests/{}/ready".format(request_id), headers=headers)
        assert denied.status_code == 422
        assert "active explicit relationship" in denied.json()["detail"]

        cancelled = client.post(
            "/api/v1/field-information-requests/{}/cancel".format(request_id),
            json={"reason": "field officer reassigned"}, headers=headers,
        )
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
        assert client.get("/api/v1/field-information-requests", headers=headers).json()[0]["id"] == request_id
