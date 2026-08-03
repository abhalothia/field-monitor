"""Non-secret, fail-closed readiness reporting for the FFL WhatsApp lane.

This module deliberately reports configuration *facts*, not configuration
values. It can be exposed to an authenticated manager once the application
adds a narrow route, because it never returns credentials, sender/contact
addresses, receipt material, provider IDs, or message content.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


_SANDBOX_PROOF = "sandbox-verified"


@dataclass(frozen=True)
class WhatsAppReadinessConfig:
    """Safe-to-inspect facts supplied by the runtime composition root.

    ``private_worker_attested`` is intentionally a deployment-owned fact, not
    a claim inferred from an HTTP request. It should be true only when the
    private FFL worker service has been installed and scheduled according to
    the reviewed runbook.
    """

    provider: str
    api_configured: bool
    webhook_authorization_configured: bool
    receipt_key_configured: bool
    dedicated_sender_configured: bool
    whatsapp_channel_enabled: bool
    whatsapp_capability_proof_verified: bool
    whatsapp_capability_proof_reference_configured: bool
    private_worker_attested: bool

    @classmethod
    def from_loopmessage_provider(
        cls,
        provider: Any,
        *,
        receipt_key_configured: bool,
        private_worker_attested: bool,
    ) -> "WhatsAppReadinessConfig":
        """Derive only booleans from a configured LoopMessage adapter.

        The adapter may contain secrets and a sender identifier. This method
        checks their presence but never copies those values into this config or
        its report.
        """

        return cls(
            provider=str(getattr(provider, "name", "loopmessage")),
            api_configured=_is_configured(getattr(provider, "organization_api_key", None)),
            webhook_authorization_configured=_is_configured(getattr(provider, "webhook_authorization", None)),
            receipt_key_configured=bool(receipt_key_configured),
            dedicated_sender_configured=_is_configured(getattr(provider, "sender_id", None)),
            whatsapp_channel_enabled=bool(getattr(provider, "whatsapp_channel_enabled", False)),
            whatsapp_capability_proof_verified=(
                getattr(provider, "whatsapp_capability_proof", None) == _SANDBOX_PROOF
            ),
            whatsapp_capability_proof_reference_configured=_is_configured(
                getattr(provider, "whatsapp_capability_proof_ref", None)
            ),
            private_worker_attested=bool(private_worker_attested),
        )


def whatsapp_readiness(config: WhatsAppReadinessConfig) -> Dict[str, Any]:
    """Return the manager-safe status for real inbound and outbound traffic.

    FFL intentionally requires the entire private operating lane before either
    direction is eligible. In particular, a sender or API key alone can never
    activate a provider-selected non-WhatsApp channel, and no webhook receipt
    may become stranded without the private recovery worker.
    """

    checks = {
        "api_configured": config.api_configured,
        "webhook_authorization_configured": config.webhook_authorization_configured,
        "receipt_key_configured": config.receipt_key_configured,
        "dedicated_sender_configured": config.dedicated_sender_configured,
        "whatsapp_channel_enabled": config.whatsapp_channel_enabled,
        "whatsapp_capability_proof_verified": config.whatsapp_capability_proof_verified,
        "whatsapp_capability_proof_reference_configured": config.whatsapp_capability_proof_reference_configured,
        "private_worker_attested": config.private_worker_attested,
    }
    gaps = _gaps(checks)
    eligible = not gaps
    return {
        "provider": config.provider,
        "transport": "whatsapp_only",
        "status": "ready" if eligible else "blocked",
        "live_inbound_eligible": eligible,
        "live_outbound_eligible": eligible,
        "checks": checks,
        "private_worker_required": True,
        "gaps": gaps,
    }


def _gaps(checks: Dict[str, bool]) -> List[str]:
    """Stable, non-secret gap codes for UI copy and operational automation."""

    labels = {
        "api_configured": "organization_api_not_configured",
        "webhook_authorization_configured": "webhook_authorization_not_configured",
        "receipt_key_configured": "receipt_key_not_configured",
        "dedicated_sender_configured": "dedicated_sender_not_configured",
        "whatsapp_channel_enabled": "whatsapp_channel_not_enabled",
        "whatsapp_capability_proof_verified": "whatsapp_sandbox_proof_not_verified",
        "whatsapp_capability_proof_reference_configured": "whatsapp_sandbox_proof_reference_not_recorded",
        "private_worker_attested": "private_worker_not_attested",
    }
    return [labels[key] for key, value in checks.items() if not value]


def _is_configured(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())
