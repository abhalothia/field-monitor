"""Fail-closed native field-capture vertical tests.

The browser is never allowed to name a person, allocation, template, reviewer,
or canonical farm record.  A manager issues a short-lived opaque pass against a
reviewed information request; the server derives the remaining scope.
"""

import base64

from fastapi.testclient import TestClient

from ffl.app import create_app
from ffl.persistence import repository
from ffl.seed import seed_pilot
from ffl.services import relationships, templates


class FakeEvidenceStore:
    def __init__(self):
        self.puts = []

    def put_content_addressed(self, content_hash, content, media_type):
        self.puts.append((content_hash, content, media_type))
        return "fake-private://field-evidence/" + content_hash


def _request_payload(allocation_id, person_id):
    return {
        "allocation_id": allocation_id,
        "target_person_id": person_id,
        "request_kind": "evidence_photo",
        "evidence_required": True,
        "due_at": "2026-08-10T09:00:00+05:30",
        "request_copy_en": "Inspect the rice and attach one clear photo.",
        "request_copy_hi": "धान देखें और एक साफ फोटो लगाएं।",
        "idempotency_key": "field-capture-request:0001",
    }


def _field_payload():
    return {
        "idempotency_key": "field-device-observation:0001",
        "observed_at": "2026-08-03T07:30:00+05:30",
        "values": {"condition": "watch", "note": "Water standing at the edge."},
        "evidence": {
            "content_base64": base64.b64encode(b"private field photo bytes").decode("ascii"),
            "media_type": "image/jpeg",
            "filename": "north-edge.jpg",
        },
    }


def _setup(tmp_path):
    store = FakeEvidenceStore()
    app = create_app(
        str(tmp_path / "field-capture.db"),
        manager_api_token="manager-secret",
        field_capture_signing_key="field-capture-signing-secret-for-tests",
        evidence_store=store,
    )
    client = TestClient(app)
    seed = seed_pilot(app.state.conn)
    app.state.manager_person_id = seed["manager_id"]
    operator = repository.create_person(app.state.conn, "Asha Field Officer", "field_operator")
    relationships.establish_person_operating_relationship(
        app.state.conn,
        operator.id,
        "crop_allocation",
        seed["allocation_id"],
        "field_operator",
        "2026-06-01",
        seed["manager_id"],
        provenance="reviewed Fortune field roster",
    )
    template = templates.publish_signal_template(
        app.state.conn,
        "field-photo-observation",
        1,
        [
            {"key": "condition", "type": "choice", "options": ["clear", "watch"], "required": True},
            {"key": "note", "type": "text", "required": True},
        ],
        seed["manager_id"],
    )
    headers = {"X-FFL-Manager-Token": "manager-secret"}
    requested = client.post(
        "/api/v1/field-information-requests",
        json=_request_payload(seed["allocation_id"], operator.id),
        headers=headers,
    )
    assert requested.status_code == 201
    request_id = requested.json()["id"]
    assert client.post(
        "/api/v1/field-information-requests/{}/ready".format(request_id), headers=headers
    ).status_code == 200
    return app, client, seed, operator, template, store, headers, request_id


def _issue_pass(client, headers, request_id, template):
    response = client.post(
        "/api/v1/field-capture/passes",
        json={
            "field_information_request_id": request_id,
            "signal_template_id": template.id,
            "signal_template_version": template.version,
            "expires_at": "2026-08-11T09:00:00+05:30",
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def test_capture_requires_a_manager_issued_scoped_pass_and_submits_review_only_candidate(tmp_path):
    app, client, seed, operator, template, store, headers, request_id = _setup(tmp_path)
    try:
        assert client.post("/api/v1/field-capture/submissions", json=_field_payload()).status_code == 403
        assert client.post(
            "/api/v1/field-capture/passes",
            json={
                "field_information_request_id": request_id,
                "signal_template_id": template.id,
                "signal_template_version": template.version,
                "expires_at": "2026-08-11T09:00:00+05:30",
                "target_person_id": seed["manager_id"],
            },
            headers=headers,
        ).status_code == 422

        issued = _issue_pass(client, headers, request_id, template)
        assert set(issued) == {"access_token", "expires_at", "field_information_request_id"}
        assert operator.id not in repr(issued)
        assert issued["access_token"] not in repr(
            app.state.conn.execute("SELECT token_hash FROM field_capture_passes").fetchone()[0]
        )

        field_headers = {"Authorization": "Bearer " + issued["access_token"]}
        context = client.get("/api/v1/field-capture/context", headers=field_headers)
        assert context.status_code == 200
        assert context.json() == {
            "assignment": {
                "allocation": {"block_name": "North Block", "crop_name": "Rice", "cultivar": "Pusa 1121"},
                "request": {
                    "kind": "evidence_photo",
                    "evidence_required": True,
                    "due_at": "2026-08-10T09:00:00+05:30",
                    "copy_en": "Inspect the rice and attach one clear photo.",
                    "copy_hi": "धान देखें और एक साफ फोटो लगाएं।",
                },
                "template": {
                    "name": "field-photo-observation",
                    "version": 1,
                    "fields": [
                        {"key": "condition", "type": "choice", "options": ["clear", "watch"], "required": True},
                        {"key": "note", "type": "text", "required": True},
                    ],
                },
            }
        }

        captured = client.post("/api/v1/field-capture/submissions", json=_field_payload(), headers=field_headers)
        assert captured.status_code == 201
        candidate = captured.json()
        assert candidate["status"] == "review"
        assert candidate["evidence"] == {"present": True, "media_type": "image/jpeg", "size_bytes": 25}
        assert "values" not in candidate
        assert "storage_reference" not in repr(candidate)
        assert len(store.puts) == 1
        assert app.state.conn.execute("SELECT COUNT(*) FROM field_signals").fetchone()[0] == 0
        assert app.state.conn.execute("SELECT COUNT(*) FROM exception_records").fetchone()[0] == 0
        assert app.state.conn.execute(
            "SELECT status FROM work_items WHERE allocation_id = ?", (seed["allocation_id"],)
        ).fetchone()[0] == "planned"

        replay = client.post("/api/v1/field-capture/submissions", json=_field_payload(), headers=field_headers)
        assert replay.status_code == 200
        assert replay.json()["id"] == candidate["id"]
        assert len(store.puts) == 1

        reviewed = client.get("/api/v1/field-capture/candidates/{}".format(candidate["id"]), headers=headers)
        assert reviewed.status_code == 200
        assert reviewed.json()["values"] == _field_payload()["values"]
        assert reviewed.json()["actor"] == {"name": "Asha Field Officer", "role": "field_operator"}
        assert reviewed.json()["evidence"]["id"]
        assert "storage_reference" not in repr(reviewed.json())
    finally:
        client.close()


def test_capture_requires_evidence_and_manager_acceptance_revalidates_the_canonical_template(tmp_path):
    app, client, seed, _operator, template, _store, headers, request_id = _setup(tmp_path)
    try:
        issued = _issue_pass(client, headers, request_id, template)
        field_headers = {"Authorization": "Bearer " + issued["access_token"]}
        no_evidence = _field_payload()
        no_evidence.pop("evidence")
        assert client.post("/api/v1/field-capture/submissions", json=no_evidence, headers=field_headers).status_code == 422

        # A failed input validation never creates a candidate or a canonical signal.
        invalid = _field_payload()
        invalid["values"]["condition"] = "invented"
        assert client.post("/api/v1/field-capture/submissions", json=invalid, headers=field_headers).status_code == 422
        assert app.state.conn.execute("SELECT COUNT(*) FROM field_capture_candidates").fetchone()[0] == 0
        assert app.state.conn.execute("SELECT COUNT(*) FROM field_signals").fetchone()[0] == 0

        captured = client.post("/api/v1/field-capture/submissions", json=_field_payload(), headers=field_headers)
        candidate_id = captured.json()["id"]
        assert client.post("/api/v1/field-capture/candidates/{}/accept".format(candidate_id)).status_code == 403
        accepted = client.post("/api/v1/field-capture/candidates/{}/accept".format(candidate_id), headers=headers)
        assert accepted.status_code == 200
        assert accepted.json()["status"] == "accepted"
        signal = app.state.conn.execute("SELECT * FROM field_signals").fetchone()
        assert signal["allocation_id"] == seed["allocation_id"]
        assert signal["actor_id"] != seed["manager_id"]
        assert signal["status"] == "submitted"
        assert signal["evidence_artifact_id"] is not None
        assert app.state.conn.execute(
            "SELECT status FROM work_items WHERE allocation_id = ?", (seed["allocation_id"],)
        ).fetchone()[0] == "planned"
    finally:
        client.close()


def test_capture_fails_closed_if_assignment_is_no_longer_explicitly_active(tmp_path):
    app, client, seed, operator, template, _store, headers, request_id = _setup(tmp_path)
    try:
        issued = _issue_pass(client, headers, request_id, template)
        relationship = app.state.conn.execute(
            "SELECT id FROM person_operating_relationships WHERE person_id = ?", (operator.id,)
        ).fetchone()[0]
        relationships.end_person_operating_relationship(
            app.state.conn, relationship, "2026-08-02", seed["manager_id"], "reassigned"
        )
        field_headers = {"Authorization": "Bearer " + issued["access_token"]}
        denied = client.post("/api/v1/field-capture/submissions", json=_field_payload(), headers=field_headers)
        assert denied.status_code == 422
        assert "active explicit relationship" in denied.json()["detail"]
        assert app.state.conn.execute("SELECT COUNT(*) FROM field_capture_candidates").fetchone()[0] == 0
    finally:
        client.close()


def test_capture_pass_issuance_fails_closed_without_server_owned_signing_authority(tmp_path):
    app = create_app(str(tmp_path / "unconfigured-field-capture.db"), manager_api_token="manager-secret")
    with TestClient(app) as client:
        seed = seed_pilot(app.state.conn)
        app.state.manager_person_id = seed["manager_id"]
        response = client.post(
            "/api/v1/field-capture/passes",
            json={
                "field_information_request_id": "not-an-open-browser-capability",
                "signal_template_id": "not-a-template",
                "signal_template_version": 1,
                "expires_at": "2026-08-11T09:00:00+05:30",
            },
            headers={"X-FFL-Manager-Token": "manager-secret"},
        )

    assert response.status_code == 503
    assert "signing authority" in response.json()["detail"]


def test_field_surface_never_queues_raw_photos_or_location_or_promises_auto_send():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "ffl" / "static" / "field"
    script = (root / "app.js").read_text()
    page = (root / "index.html").read_text()

    assert "localStorage" not in script
    assert "geolocation" not in script
    assert "/api/v1/exceptions" not in script
    assert "auto-send" not in (page + script).lower()
    assert "/api/v1/field-capture/context" in script
