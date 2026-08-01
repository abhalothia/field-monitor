from pathlib import Path

from fastapi.testclient import TestClient

from ffl.app import create_app
from ffl.communications import persistence
from ffl.communications.fake import FakeLoopMessageProvider
from ffl.communications.loopmessage import LoopMessageProvider
from ffl.persistence import repository
from ffl.seed import seed_pilot
from ffl.services.operations import create_work_item


def _setup(tmp_path: Path):
    provider = FakeLoopMessageProvider()
    app = create_app(str(tmp_path / "communications.db"), communication_provider=provider)
    with TestClient(app) as client:
        seed = seed_pilot(app.state.conn)
        work = create_work_item(
            app.state.conn, seed["allocation_id"], "WhatsApp irrigation check", seed["operator_id"],
            "2026-07-10T09:00:00+00:00", initial_status="planned",
        )
        endpoint = persistence.create_endpoint(
            app.state.conn, seed["operator_id"], "loopmessage", "+15550000001", "hi-IN"
        )
        consent = persistence.set_consent(app.state.conn, endpoint["id"], "work_prompt", True, "signed field pilot")
        template = persistence.create_template(
            app.state.conn, "irrigation_check", 1, "hi-IN", "work_prompt",
            "FFL: सिंचाई जांच / Inspect irrigation. Reply REPORT_DEVIATION if needed.", seed["manager_id"],
        )
        yield client, app.state.conn, provider, seed, work, endpoint, consent, template


def _send_prompt(client, work, endpoint, template, seed):
    response = client.post(
        "/api/v1/work-items/{}/communication-prompts".format(work.id),
        json={"endpoint_id": endpoint["id"], "template_id": template["id"], "initiated_by_person_id": seed["manager_id"]},
    )
    assert response.status_code == 201
    return response.json()


def _inbound(client, provider, event_id, message_id="inbound-1", **additional):
    payload = {
        "event": "message_inbound", "contact": "+15550000001", "text": "REPORT_DEVIATION",
        "message_type": "attachments", "attachments": ["https://evidence.example.invalid/photo.jpg"],
        "message_id": message_id, "webhook_id": event_id, "api_version": "1.0",
    }
    payload.update(additional)
    return client.post(
        "/api/v1/communications/loopmessage/webhook", json=payload,
        headers={"Authorization": provider.webhook_authorization},
    )


def test_consent_backed_prompt_inbound_attachment_replay_and_human_exception_acceptance(tmp_path):
    for client, conn, provider, seed, work, endpoint, _consent, template in _setup(tmp_path):
        prompt = _send_prompt(client, work, endpoint, template, seed)
        assert prompt["status"] == "accepted"
        assert provider.sent[0]["contact"] == "+15550000001"
        assert "सिंचाई" in provider.sent[0]["text"]

        first = _inbound(client, provider, "webhook-inbound-1", quick_reply="REPORT_DEVIATION")
        replay = _inbound(client, provider, "webhook-inbound-1", quick_reply="REPORT_DEVIATION")
        assert first.status_code == 200
        assert replay.json()["status"] == "duplicate"
        candidate_id = first.json()["candidate_id"]

        candidate = client.get("/api/v1/communications/inbox").json()["candidates"][0]
        assert candidate["id"] == candidate_id
        assert candidate["work_item_id"] == work.id
        assert candidate["allocation_id"] == seed["allocation_id"]
        assert conn.execute("SELECT count(*) FROM communication_attachments").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM exception_records").fetchone()[0] == 0

        accepted = client.post(
            "/api/v1/communications/candidates/{}/accept".format(candidate_id),
            json={"reviewer_id": seed["manager_id"], "exception_owner_id": seed["manager_id"],
                  "exception_fallback_owner_id": seed["lead_id"], "severity": "high"},
        )
        assert accepted.status_code == 200
        assert accepted.json()["accepted_record_type"] == "exception_record"
        assert conn.execute("SELECT count(*) FROM exception_records").fetchone()[0] == 1
        assert repository.get_work_item(conn, work.id).status == "planned"


def test_invalid_signature_opt_out_and_delivery_failure_remain_visible(tmp_path):
    for client, conn, provider, seed, work, endpoint, _consent, template in _setup(tmp_path):
        invalid = client.post("/api/v1/communications/loopmessage/webhook", json={}, headers={"Authorization": "wrong"})
        assert invalid.status_code == 401
        assert conn.execute("SELECT count(*) FROM communication_events").fetchone()[0] == 0

        prompt = _send_prompt(client, work, endpoint, template, seed)
        assert client.get("/api/v1/communications/health").json()["awaiting_response_count"] == 1
        failed = client.post(
            "/api/v1/communications/loopmessage/webhook",
            json={"event": "message_failed", "contact": "+15550000001", "text": "",
                  "message_id": prompt["provider_message_id"], "webhook_id": "webhook-failed-1"},
            headers={"Authorization": provider.webhook_authorization},
        )
        assert failed.status_code == 200
        assert client.get("/api/v1/communications/health").json()["failed_delivery_count"] == 1
        assert repository.get_work_item(conn, work.id).status == "planned"

        persistence.set_consent(conn, endpoint["id"], "work_prompt", False, "operator opted out")
        suppressed = client.post(
            "/api/v1/work-items/{}/communication-prompts".format(work.id),
            json={"endpoint_id": endpoint["id"], "template_id": template["id"], "initiated_by_person_id": seed["manager_id"]},
        )
        assert suppressed.status_code == 422
        assert "consent" in suppressed.json()["detail"]
        assert len(provider.sent) == 1


def test_ambiguous_context_requires_review_and_signal_acceptance_uses_canonical_record(tmp_path):
    for client, conn, provider, seed, work, endpoint, _consent, template in _setup(tmp_path):
        _send_prompt(client, work, endpoint, template, seed)
        second_work = create_work_item(
            conn, seed["allocation_id"], "Second open prompt", seed["operator_id"],
            "2026-07-11T09:00:00+00:00", initial_status="planned",
        )
        _send_prompt(client, second_work, endpoint, template, seed)
        ambiguous = _inbound(client, provider, "webhook-ambiguous", message_id="inbound-ambiguous", text="crop looks fine")
        candidate = client.get("/api/v1/communications/inbox").json()["candidates"][0]
        assert ambiguous.status_code == 200
        assert candidate["work_item_id"] is None
        assert client.post(
            "/api/v1/communications/candidates/{}/accept".format(candidate["id"]),
            json={"reviewer_id": seed["manager_id"], "signal_template_id": "missing", "signal_template_version": 1},
        ).status_code == 422

        # Resolve by leaving exactly one open prompt, then accept a normal signal.
        conn.execute("UPDATE communication_prompts SET status = 'responded' WHERE work_item_id = ?", (second_work.id,))
        conn.commit()
        resolved = _inbound(client, provider, "webhook-signal", message_id="inbound-signal", text="crop looks fine")
        signal_candidate = client.get("/api/v1/communications/inbox").json()["candidates"][-1]
        assert resolved.status_code == 200
        signal_template = conn.execute("SELECT id, version FROM signal_templates WHERE name = 'crop_exception'").fetchone()
        accepted = client.post(
            "/api/v1/communications/candidates/{}/accept".format(signal_candidate["id"]),
            json={"reviewer_id": seed["manager_id"], "signal_template_id": signal_template["id"], "signal_template_version": signal_template["version"]},
        )
        assert accepted.status_code == 200
        assert accepted.json()["accepted_record_type"] == "field_signal"
        assert conn.execute("SELECT count(*) FROM field_signals").fetchone()[0] == 1


def test_loopmessage_adapter_uses_documented_authorization_and_whatsapp_channel(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"message_id": "provider-message-1"}

    def fake_post(url, headers, json, timeout):
        captured.update({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return Response()

    monkeypatch.setattr("ffl.communications.loopmessage.httpx.post", fake_post)
    provider = LoopMessageProvider("organization-key", "webhook-token", "sender-1")
    result = provider.send_message("+15550000001", "FFL work prompt", None, "ffl-prompt-1")

    assert provider.verify_webhook("webhook-token")
    assert not provider.verify_webhook("wrong")
    assert result.provider_message_id == "provider-message-1"
    assert captured == {
        "url": "https://a.loopmessage.com/api/v1/message/send/",
        "headers": {"Authorization": "organization-key", "Content-Type": "application/json"},
        "json": {"contact": "+15550000001", "text": "FFL work prompt", "channel": "whatsapp",
                 "passthrough": "ffl-prompt-1", "sender": "sender-1"},
        "timeout": 15.0,
    }
