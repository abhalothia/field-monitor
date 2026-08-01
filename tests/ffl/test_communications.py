from pathlib import Path
import json
import sqlite3

from fastapi.testclient import TestClient

from ffl.app import create_app
from ffl.communications import persistence
from ffl.communications.fake import FakeLoopMessageProvider
from ffl.communications.loopmessage import LoopMessageProvider
from ffl.communications.service import process_pending_communications, retain_inbound_attachment
from ffl.persistence.schema import create_schema
from ffl.persistence import repository
from ffl.seed import seed_pilot
from ffl.services.evidence import retain_evidence
from ffl.services.operations import create_work_item


def _setup(tmp_path: Path):
    provider = FakeLoopMessageProvider()
    app = create_app(str(tmp_path / "communications.db"), communication_provider=provider, manager_api_token="test-manager-token", communication_receipt_key="test-receipt-key")
    with TestClient(app, headers={"X-FFL-Manager-Token": "test-manager-token"}) as client:
        seed = seed_pilot(app.state.conn)
        app.state.manager_person_id = seed["manager_id"]
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
        template = persistence.publish_template(app.state.conn, template["id"], seed["manager_id"])
        yield client, app.state.conn, provider, seed, work, endpoint, consent, template


def _send_prompt(client, work, endpoint, template, seed):
    response = client.post(
        "/api/v1/work-items/{}/communication-prompts".format(work.id),
        json={"endpoint_id": endpoint["id"], "template_id": template["id"], "initiated_by_person_id": seed["manager_id"], "idempotency_key": "prompt:" + work.id},
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
    response = client.post(
        "/api/v1/communications/loopmessage/webhook", json=payload,
        headers={"Authorization": provider.webhook_authorization},
    )
    process_pending_communications(client.app.state.conn, provider, "test-receipt-key")
    return response


def test_consent_backed_prompt_inbound_attachment_replay_and_human_exception_acceptance(tmp_path):
    for client, conn, provider, seed, work, endpoint, _consent, template in _setup(tmp_path):
        prompt = _send_prompt(client, work, endpoint, template, seed)
        replayed_prompt = _send_prompt(client, work, endpoint, template, seed)
        assert prompt["status"] == "accepted"
        assert replayed_prompt["id"] == prompt["id"]
        assert len(provider.sent) == 1
        assert provider.sent[0]["contact"] == "+15550000001"
        assert "सिंचाई" in provider.sent[0]["text"]

        first = _inbound(client, provider, "webhook-inbound-1")
        replay = _inbound(client, provider, "webhook-inbound-1")
        assert first.status_code == 200
        assert replay.json()["status"] == "duplicate"

        candidate = client.get("/api/v1/communications/inbox").json()["candidates"][0]
        candidate_id = candidate["id"]
        assert candidate["id"] == candidate_id
        assert candidate["work_item_id"] == work.id
        assert candidate["allocation_id"] == seed["allocation_id"]
        assert "draft_json" not in candidate
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
        assert process_pending_communications(conn, provider, "test-receipt-key") == 1
        assert client.get("/api/v1/communications/health").json()["failed_delivery_count"] == 1
        assert repository.get_work_item(conn, work.id).status == "planned"

        persistence.set_consent(conn, endpoint["id"], "work_prompt", False, "operator opted out")
        suppressed = client.post(
            "/api/v1/work-items/{}/communication-prompts".format(work.id),
            json={"endpoint_id": endpoint["id"], "template_id": template["id"], "initiated_by_person_id": seed["manager_id"], "idempotency_key": "suppressed:" + work.id},
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
        invalid = client.post(
            "/api/v1/communications/candidates/{}/accept".format(signal_candidate["id"]),
            json={"reviewer_id": seed["manager_id"], "signal_template_id": signal_template["id"], "signal_template_version": signal_template["version"], "signal_values": {"severity": "high"}},
        )
        assert invalid.status_code == 422
        assert conn.execute("SELECT count(*) FROM field_signals").fetchone()[0] == 0
        retained_evidence = retain_evidence(conn, b"reviewed image bytes", "image/jpeg", created_by_person_id=seed["operator_id"])
        unlinked = client.post(
            "/api/v1/communications/candidates/{}/accept".format(signal_candidate["id"]),
            json={"reviewer_id": seed["manager_id"], "signal_template_id": signal_template["id"], "signal_template_version": signal_template["version"], "signal_values": {"severity": "high", "photo_url": "reviewed-in-app"}, "evidence_artifact_id": retained_evidence.id},
        )
        assert unlinked.status_code == 422
        attachment_id = json.loads(conn.execute("SELECT draft_json FROM communication_candidates WHERE id = ?", (signal_candidate["id"],)).fetchone()[0])["attachment_ids"][0]
        retained_id = retain_inbound_attachment(conn, attachment_id, b"reviewed message image", "image/jpeg", str(tmp_path / "evidence"))
        accepted = client.post(
            "/api/v1/communications/candidates/{}/accept".format(signal_candidate["id"]),
            json={"reviewer_id": seed["manager_id"], "signal_template_id": signal_template["id"], "signal_template_version": signal_template["version"], "signal_values": {"severity": "high", "photo_url": "reviewed-in-app"}, "evidence_artifact_id": retained_id},
        )
        assert accepted.status_code == 200
        assert accepted.json()["accepted_record_type"] == "field_signal"
        assert conn.execute("SELECT count(*) FROM field_signals").fetchone()[0] == 1


def test_admin_communications_paths_redact_endpoints_and_publish_templates(tmp_path):
    provider = FakeLoopMessageProvider()
    app = create_app(str(tmp_path / "admin.db"), communication_provider=provider, manager_api_token="test-manager-token", communication_receipt_key="test-receipt-key")
    with TestClient(app, headers={"X-FFL-Manager-Token": "test-manager-token"}) as client:
        seed = seed_pilot(app.state.conn)
        app.state.manager_person_id = seed["manager_id"]
        endpoint = client.post(
            "/api/v1/communication-endpoints",
            json={"person_id": seed["operator_id"], "provider": "loopmessage", "address": "+15550000002", "locale": "hi-IN"},
        )
        assert endpoint.status_code == 201
        assert endpoint.json()["address_last4"] == "0002"
        assert "address" not in endpoint.json()
        consent = client.post(
            "/api/v1/communication-endpoints/{}/consents".format(endpoint.json()["id"]),
            json={"purpose": "work_prompt", "evidence": "signed pilot consent"},
        )
        assert consent.json()["status"] == "active"
        draft = client.post(
            "/api/v1/communication-templates",
            json={"template_key": "daily_check", "version": 1, "locale": "hi-IN", "purpose": "work_prompt", "body": "Daily check"},
        )
        assert draft.json()["status"] == "draft"
        published = client.post(
            "/api/v1/communication-templates/{}/publish".format(draft.json()["id"]),
        )
        assert published.json()["status"] == "published"


def test_loopmessage_adapter_builds_documented_payload_without_a_network_call():
    provider = LoopMessageProvider("organization-key", "webhook-token", "sender-1")
    payload = provider.build_send_payload("+15550000001", "FFL work prompt", None, "ffl-prompt-1")

    assert provider.verify_webhook("webhook-token")
    assert not provider.verify_webhook("wrong")
    assert payload == {"contact": "+15550000001", "text": "FFL work prompt", "passthrough": "ffl-prompt-1", "sender": "sender-1"}
    assert LoopMessageProvider("key", "token", whatsapp_channel_enabled=True).build_send_payload("+15550000001", "prompt", None, "id")["channel"] == "whatsapp"


def test_webhook_receipt_recovers_after_crash_and_replay_creates_one_candidate_and_attachment(tmp_path):
    for client, conn, provider, seed, work, endpoint, _consent, template in _setup(tmp_path):
        _send_prompt(client, work, endpoint, template, seed)
        payload = {
            "event": "message_inbound", "contact": "+15550000001", "text": "REPORT_DEVIATION",
            "message_type": "attachments", "attachments": ["https://private.example.invalid/photo.jpg"],
            "message_id": "crash-inbound", "webhook_id": "crash-receipt-1", "api_version": "1.0",
        }
        accepted = client.post("/api/v1/communications/loopmessage/webhook", json=payload, headers={"Authorization": provider.webhook_authorization})
        assert accepted.status_code == 200
        assert conn.execute("SELECT count(*) FROM communication_candidates").fetchone()[0] == 0
        assert "REPORT_DEVIATION" not in conn.execute("SELECT ciphertext FROM communication_receipts").fetchone()[0]
        assert process_pending_communications(conn, provider, "test-receipt-key", crash_after_receipt=True) == 0
        receipt = conn.execute("SELECT status, attempts FROM communication_receipts").fetchone()
        assert tuple(receipt) == ("retryable", 1)

        replay = client.post("/api/v1/communications/loopmessage/webhook", json=payload, headers={"Authorization": provider.webhook_authorization})
        assert replay.json()["status"] == "duplicate"
        assert conn.execute("SELECT status FROM communication_receipts").fetchone()[0] == "queued"
        assert process_pending_communications(conn, provider, "test-receipt-key") == 1
        assert conn.execute("SELECT count(*) FROM communication_candidates").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM communication_attachments").fetchone()[0] == 1
        processed_replay = client.post("/api/v1/communications/loopmessage/webhook", json=payload, headers={"Authorization": provider.webhook_authorization})
        assert processed_replay.json()["status"] == "duplicate"
        assert process_pending_communications(conn, provider, "test-receipt-key") == 0
        assert conn.execute("SELECT count(*) FROM communication_candidates").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM communication_attachments").fetchone()[0] == 1


def test_legacy_c5_raw_communications_migration_rebuilds_children_without_raw_payloads(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "legacy-c5.db"))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    create_schema(conn)
    conn.executescript("""
        CREATE TABLE communication_events (
            id TEXT PRIMARY KEY, provider TEXT NOT NULL, provider_event_id TEXT NOT NULL,
            provider_message_id TEXT, event_type TEXT NOT NULL, contact_address TEXT NOT NULL,
            endpoint_id TEXT, payload_json TEXT NOT NULL, status TEXT NOT NULL,
            received_at TEXT NOT NULL, UNIQUE(provider, provider_event_id)
        );
        CREATE INDEX idx_communication_events_contact ON communication_events(provider, contact_address);
        CREATE TABLE communication_attachments (
            id TEXT PRIMARY KEY, event_id TEXT NOT NULL REFERENCES communication_events(id),
            source_url TEXT NOT NULL, media_type TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE communication_candidates (
            id TEXT PRIMARY KEY, event_id TEXT NOT NULL UNIQUE REFERENCES communication_events(id),
            prompt_id TEXT, allocation_id TEXT, work_item_id TEXT, endpoint_id TEXT,
            kind TEXT NOT NULL, status TEXT NOT NULL, draft_json TEXT NOT NULL,
            accepted_record_type TEXT, accepted_record_id TEXT, reviewed_by_person_id TEXT,
            reviewed_at TEXT, created_at TEXT NOT NULL
        );
        INSERT INTO communication_events VALUES
            ('legacy-event', 'loopmessage', 'legacy-webhook', 'legacy-message', 'message_inbound',
             '+15550000001', NULL, '{"text":"private field report"}', 'received', '2026-07-10T00:00:00+00:00');
        INSERT INTO communication_attachments VALUES
            ('legacy-attachment', 'legacy-event', 'https://private.example.invalid/photo.jpg', 'image/jpeg', 'pending_fetch', '2026-07-10T00:00:00+00:00');
        INSERT INTO communication_candidates VALUES
            ('legacy-candidate', 'legacy-event', NULL, NULL, NULL, NULL, 'signal', 'review',
             '{"text":"private field report"}', NULL, NULL, NULL, NULL, '2026-07-10T00:00:00+00:00');
    """)
    conn.commit()

    persistence.create_communications_schema(conn)

    event = conn.execute("SELECT * FROM communication_events WHERE id = 'legacy-event'").fetchone()
    assert event["status"] == "quarantined"
    assert "payload_json" not in {row["name"] for row in conn.execute("PRAGMA table_info(communication_events)")}
    assert "private field report" not in event["envelope_json"]
    attachment = conn.execute("SELECT * FROM communication_attachments WHERE id = 'legacy-attachment'").fetchone()
    assert attachment["status"] == "unavailable"
    assert "private.example" not in attachment["source_reference"]
    candidate = conn.execute("SELECT draft_json FROM communication_candidates WHERE id = 'legacy-candidate'").fetchone()
    assert json.loads(candidate[0])["content_redacted"] is True
    assert conn.execute("SELECT count(*) FROM communication_quarantines").fetchone()[0] == 1
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = 'idx_communication_events_contact'").fetchone() is not None
    conn.close()


def test_previous_c5_security_schema_upgrades_additive_tables_and_columns_without_stranding_rows(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "previous-c5.db"))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    create_schema(conn)
    seed = seed_pilot(conn)
    conn.executescript("""
        CREATE TABLE communication_endpoints (
            id TEXT PRIMARY KEY, person_id TEXT NOT NULL REFERENCES people(id), provider TEXT NOT NULL,
            address TEXT NOT NULL, locale TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
            UNIQUE(provider, address)
        );
        CREATE TABLE communication_consents (
            id TEXT PRIMARY KEY, endpoint_id TEXT NOT NULL REFERENCES communication_endpoints(id),
            purpose TEXT NOT NULL, status TEXT NOT NULL, granted_at TEXT NOT NULL, revoked_at TEXT,
            evidence TEXT NOT NULL, UNIQUE(endpoint_id, purpose)
        );
        CREATE TABLE communication_templates (
            id TEXT PRIMARY KEY, template_key TEXT NOT NULL, version INTEGER NOT NULL, locale TEXT NOT NULL,
            purpose TEXT NOT NULL, body TEXT NOT NULL, status TEXT NOT NULL,
            owner_id TEXT NOT NULL REFERENCES people(id), created_at TEXT NOT NULL,
            UNIQUE(template_key, version, locale)
        );
        CREATE TABLE communication_prompts (
            id TEXT PRIMARY KEY, work_item_id TEXT NOT NULL REFERENCES work_items(id),
            allocation_id TEXT NOT NULL REFERENCES crop_allocations(id),
            endpoint_id TEXT NOT NULL REFERENCES communication_endpoints(id),
            template_id TEXT NOT NULL REFERENCES communication_templates(id),
            initiated_by_person_id TEXT NOT NULL REFERENCES people(id), idempotency_key TEXT NOT NULL UNIQUE,
            provider_message_id TEXT UNIQUE, status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE communication_events (
            id TEXT PRIMARY KEY, provider TEXT NOT NULL, provider_event_id TEXT NOT NULL,
            provider_message_id TEXT, event_type TEXT NOT NULL, contact_fingerprint TEXT NOT NULL,
            endpoint_id TEXT REFERENCES communication_endpoints(id), envelope_json TEXT NOT NULL,
            status TEXT NOT NULL, received_at TEXT NOT NULL, UNIQUE(provider, provider_event_id)
        );
        CREATE TABLE communication_attachments (
            id TEXT PRIMARY KEY, event_id TEXT NOT NULL REFERENCES communication_events(id),
            source_reference TEXT NOT NULL, media_type TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE communication_candidates (
            id TEXT PRIMARY KEY, event_id TEXT NOT NULL UNIQUE REFERENCES communication_events(id),
            prompt_id TEXT REFERENCES communication_prompts(id), allocation_id TEXT REFERENCES crop_allocations(id),
            work_item_id TEXT REFERENCES work_items(id), endpoint_id TEXT REFERENCES communication_endpoints(id),
            kind TEXT NOT NULL, status TEXT NOT NULL, draft_json TEXT NOT NULL, accepted_record_type TEXT,
            accepted_record_id TEXT, reviewed_by_person_id TEXT REFERENCES people(id), reviewed_at TEXT,
            created_at TEXT NOT NULL
        );
    """)
    now = "2026-07-10T00:00:00+00:00"
    conn.execute("INSERT INTO communication_endpoints VALUES (?, ?, ?, ?, ?, ?, ?)", ("c5-endpoint", seed["operator_id"], "loopmessage", "+15550000001", "hi-IN", "active", now))
    conn.execute("INSERT INTO communication_templates VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", ("c5-template", "check", 1, "hi-IN", "work_prompt", "check", "published", seed["manager_id"], now))
    work = create_work_item(conn, seed["allocation_id"], "c5 work", seed["operator_id"], now, initial_status="planned")
    conn.execute("INSERT INTO communication_prompts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", ("c5-prompt", work.id, seed["allocation_id"], "c5-endpoint", "c5-template", seed["manager_id"], "c5-idempotency", "c5-message", "accepted", now, now))
    conn.execute("INSERT INTO communication_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", ("c5-event", "loopmessage", "c5-webhook", "c5-message", "message_delivered", "redacted", "c5-endpoint", '{"message_type":"text"}', "processed", now))
    conn.commit()

    persistence.create_communications_schema(conn)

    assert conn.execute("SELECT id FROM communication_prompts WHERE id = 'c5-prompt'").fetchone()[0] == "c5-prompt"
    assert conn.execute("SELECT id FROM communication_events WHERE id = 'c5-event'").fetchone()[0] == "c5-event"
    assert {row["name"] for row in conn.execute("PRAGMA table_info(communication_prompts)")} >= {"idempotency_key", "logical_action_key"}
    assert {row["name"] for row in conn.execute("PRAGMA table_info(communication_templates)")} >= {"provider_template_id", "provider_approval_state"}
    assert conn.execute("SELECT 1 FROM communication_deliveries LIMIT 1").fetchone() is None
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    conn.close()
