import json

from ffl.communications.loopmessage import LoopMessageProvider
from ffl.communications.readiness import WhatsAppReadinessConfig, whatsapp_readiness


def _provider(**overrides):
    values = {
        "organization_api_key": "organization-api-secret",
        "webhook_authorization": "dashboard-webhook-secret",
        "sender_id": "+15550000001",
        "whatsapp_channel_enabled": True,
        "whatsapp_capability_proof": "sandbox-verified",
        "whatsapp_capability_proof_ref": "reviewed-ticket-123",
    }
    values.update(overrides)
    return LoopMessageProvider(**values)


def test_readiness_is_ready_only_when_the_complete_private_whatsapp_lane_is_attested():
    config = WhatsAppReadinessConfig.from_loopmessage_provider(
        _provider(), receipt_key_configured=True, private_worker_attested=True
    )

    report = whatsapp_readiness(config)

    assert report == {
        "provider": "loopmessage",
        "transport": "whatsapp_only",
        "status": "ready",
        "live_inbound_eligible": True,
        "live_outbound_eligible": True,
        "checks": {
            "api_configured": True,
            "webhook_authorization_configured": True,
            "receipt_key_configured": True,
            "dedicated_sender_configured": True,
            "whatsapp_channel_enabled": True,
            "whatsapp_capability_proof_verified": True,
            "whatsapp_capability_proof_reference_configured": True,
            "private_worker_attested": True,
        },
        "private_worker_required": True,
        "gaps": [],
    }


def test_readiness_fails_closed_and_reveals_no_secret_or_sender_value():
    config = WhatsAppReadinessConfig.from_loopmessage_provider(
        _provider(
            webhook_authorization="",
            sender_id="+15550000001",
            whatsapp_channel_enabled=False,
            whatsapp_capability_proof="unreviewed",
            whatsapp_capability_proof_ref="",
        ),
        receipt_key_configured=False,
        private_worker_attested=False,
    )

    report = whatsapp_readiness(config)
    rendered = json.dumps(report)

    assert report["status"] == "blocked"
    assert report["live_inbound_eligible"] is False
    assert report["live_outbound_eligible"] is False
    assert report["gaps"] == [
        "webhook_authorization_not_configured",
        "receipt_key_not_configured",
        "whatsapp_channel_not_enabled",
        "whatsapp_sandbox_proof_not_verified",
        "whatsapp_sandbox_proof_reference_not_recorded",
        "private_worker_not_attested",
    ]
    for protected_value in ("dashboard-webhook-secret", "+15550000001", "unreviewed"):
        assert protected_value not in rendered


def test_nonempty_proof_is_not_treated_as_a_validated_whatsapp_capability():
    config = WhatsAppReadinessConfig.from_loopmessage_provider(
        _provider(whatsapp_capability_proof="claim-only"),
        receipt_key_configured=True,
        private_worker_attested=True,
    )

    report = whatsapp_readiness(config)

    assert report["checks"]["whatsapp_capability_proof_verified"] is False
    assert report["gaps"] == ["whatsapp_sandbox_proof_not_verified"]
    assert report["live_inbound_eligible"] is False
    assert report["live_outbound_eligible"] is False
