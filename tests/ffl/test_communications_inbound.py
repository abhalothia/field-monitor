from ffl.communications import persistence
from ffl.communications.inbound import process_inbound_event
from ffl.communications.service import receive_webhook
from ffl.communications.interactions import create_interaction_run
from ffl.services.operations import create_work_item

from tests.ffl.test_communications import _setup, _send_prompt


def _event(conn, provider, payload):
    stored, _created = receive_webhook(conn, provider, payload, "test-receipt-key")
    return provider.normalize_webhook(payload), stored


def test_known_farmer_photo_reply_creates_review_candidate_for_exact_allocation(tmp_path):
    for client, conn, provider, seed, work, endpoint, _consent, template in _setup(tmp_path):
        prompt = _send_prompt(client, work, endpoint, template, seed)
        event, stored = _event(conn, provider, {
            "event": "message_inbound", "contact": "+15550000001", "text": "SUBMIT_EVIDENCE",
            "message_type": "attachments", "attachments": ["https://evidence.example.invalid/photo.jpg"],
            "message_id": "inbound-photo", "webhook_id": "inbound-photo-event",
            "reply_to_message_id": prompt["provider_message_id"], "sender": "fake-whatsapp-sender",
        })

        outcome = process_inbound_event(conn, provider, event, stored)
        candidate = persistence.get_candidate_for_event(conn, outcome.event_id)

        assert outcome.kind == "review_candidate"
        assert candidate is not None
        assert candidate["allocation_id"] == seed["allocation_id"]


def test_stop_revokes_interaction_scope_and_suppresses_future_dispatch(tmp_path):
    for client, conn, provider, seed, work, endpoint, _consent, template in _setup(tmp_path):
        prompt = _send_prompt(client, work, endpoint, template, seed)
        profile = conn.execute(
            "SELECT id FROM communication_profiles WHERE person_id = ?", (seed["operator_id"],),
        ).fetchone()
        future_work = create_work_item(
            conn, seed["allocation_id"], "future communication", seed["operator_id"],
            "2026-08-15T00:00:00+00:00", initial_status="planned",
        )
        future_prompt, _created = persistence.create_prompt(
            conn, future_work.id, seed["allocation_id"], endpoint["id"], template["id"],
            seed["manager_id"], "future-inbound-suppression",
        )
        future = create_interaction_run(
            conn, profile["id"], endpoint["id"], allocation_id=seed["allocation_id"],
            work_item_id=future_work.id, legacy_prompt_id=future_prompt["id"],
            expected_intents=("confirm", "opt_out"),
            expires_at="2026-09-01T00:00:00+00:00",
        )
        event, stored = _event(conn, provider, {
            "event": "message_inbound", "contact": "+15550000001", "text": "STOP",
            "message_type": "text", "message_id": "inbound-stop", "webhook_id": "inbound-stop-event",
            "reply_to_message_id": prompt["provider_message_id"], "sender": "fake-whatsapp-sender",
        })

        outcome = process_inbound_event(conn, provider, event, stored)

        assert outcome.kind == "opt_out"
        assert not persistence.has_scoped_consent(
            conn, profile["id"], endpoint["id"], "work_prompt", "crop_allocation", seed["allocation_id"],
        )
        assert persistence.outbox_entry(conn, future.id)["status"] == "suppressed"


def test_unknown_or_unmatched_reply_creates_redacted_review_case_not_candidate(tmp_path):
    for client, conn, provider, _seed, _work, _endpoint, _consent, _template in _setup(tmp_path):
        event, stored = _event(conn, provider, {
            "event": "message_inbound", "contact": "+919999999999", "text": "my crop is sick",
            "message_type": "text", "message_id": "unmatched-message", "webhook_id": "unmatched-event",
            "sender": "fake-whatsapp-sender",
        })

        outcome = process_inbound_event(conn, provider, event, stored)

        assert outcome.kind == "identity_review"
        assert persistence.get_candidate_for_event(conn, outcome.event_id) is None
        review = persistence.get_inbound_review_for_event(conn, outcome.event_id)
        assert review is not None
        assert review["state"] == "identity_review"
        assert "my crop is sick" not in str(review)


def test_exact_confirm_stays_out_of_signal_and_exception_acceptance_lanes(tmp_path):
    for client, conn, provider, seed, work, endpoint, _consent, template in _setup(tmp_path):
        prompt = _send_prompt(client, work, endpoint, template, seed)
        event, stored = _event(conn, provider, {
            "event": "message_inbound", "contact": "+15550000001", "text": "CONFIRM",
            "message_type": "text", "message_id": "confirm-message", "webhook_id": "confirm-event",
            "reply_to_message_id": prompt["provider_message_id"], "sender": "fake-whatsapp-sender",
        })

        outcome = process_inbound_event(conn, provider, event, stored)

        assert outcome.kind == "context_review"
        assert persistence.get_candidate_for_event(conn, outcome.event_id) is None
        assert conn.execute("SELECT count(*) FROM field_signals").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM exception_records").fetchone()[0] == 0
