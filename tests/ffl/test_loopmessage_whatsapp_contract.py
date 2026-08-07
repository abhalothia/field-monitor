import pytest

from ffl.communications.fake import FakeLoopMessageProvider
from ffl.communications.loopmessage import LoopMessageProvider


def test_template_send_preserves_provider_template_and_parameters():
    provider = FakeLoopMessageProvider()
    result = provider.send_template(
        contact="+15550000001", sender="fake-whatsapp-sender",
        template_id="weekly-checkin-hi-v1", locale="hi-IN",
        parameters={"farm": "North Block"}, passthrough="run-1",
    )
    assert result.provider_message_id == "fake-message-1"
    assert provider.sent[0]["template_id"] == "weekly-checkin-hi-v1"
    assert provider.sent[0]["parameters"] == {"farm": "North Block"}


def test_normalized_reply_exposes_reply_to_and_opt_out_without_raw_address():
    event = FakeLoopMessageProvider().normalize_webhook({
        "event": "message_inbound", "webhook_id": "evt-1", "message_id": "msg-2",
        "contact": "+15550000001", "sender": "fake-whatsapp-sender",
        "text": "STOP", "reply_to_message_id": "outbound-1",
    })
    assert event["reply_to_message_id"] == "outbound-1"
    assert event["intent"] == "opt_out"


def test_real_template_send_stays_disabled_without_a_proven_wire_mapping():
    provider = LoopMessageProvider(
        "organization-key", "webhook-token", "sender-1",
        whatsapp_channel_enabled=True,
        whatsapp_capability_proof="sandbox-verified",
        whatsapp_capability_proof_ref="test-sandbox-proof",
    )

    with pytest.raises(RuntimeError, match="template contract is not sandbox-proven"):
        provider.send_template(
            contact="+15550000001", sender="sender-1",
            template_id="weekly-checkin-hi-v1", locale="hi-IN",
            parameters={"farm": "North Block"}, passthrough="run-1",
        )


def test_normalized_attachment_references_are_opaque():
    source_url = "https://provider.example.invalid/private/photo.jpg?secret=1"
    event = FakeLoopMessageProvider().normalize_webhook({
        "event": "message_inbound", "webhook_id": "evt-media-1", "message_id": "msg-media-1",
        "contact": "+15550000001", "sender": "fake-whatsapp-sender",
        "text": "", "attachments": [source_url],
    })

    assert len(event["attachment_references"]) == 1
    assert source_url not in event["attachment_references"][0]
