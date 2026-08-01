from typing import Any, Dict, Optional

from ffl.communications.loopmessage import LoopMessageProvider
from ffl.communications.ports import SendResult


class FakeLoopMessageProvider(LoopMessageProvider):
    """Deterministic test provider; it never uses a network or real credentials."""

    name = "loopmessage"

    def __init__(self, webhook_authorization: str = "test-loopmessage-webhook") -> None:
        super().__init__(organization_api_key=None, webhook_authorization=webhook_authorization)
        self.sent: list[Dict[str, str]] = []

    def send_message(self, contact: str, text: str, sender: Optional[str], passthrough: str) -> SendResult:
        message_id = "fake-message-{}".format(len(self.sent) + 1)
        self.sent.append({"contact": contact, "text": text, "sender": sender or "", "passthrough": passthrough})
        return SendResult(provider_message_id=message_id, status="accepted")

    def normalize_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        normalized = super().normalize_webhook(payload)
        # LoopMessage does not document interactive WhatsApp payloads. Tests may
        # supply this normalized intent to prove FFL's provider-neutral seam.
        quick_reply = payload.get("quick_reply")
        if isinstance(quick_reply, str):
            normalized["quick_reply"] = quick_reply
        return normalized
