from typing import Any, Dict, Optional

from ffl.communications.loopmessage import LoopMessageProvider
from ffl.communications.ports import AttachmentContent, MessageStatus, ProviderRejectedError, SendResult


class FakeLoopMessageProvider(LoopMessageProvider):
    """Deterministic test provider; it never uses a network or real credentials."""

    name = "loopmessage"

    def __init__(self, webhook_authorization: str = "test-loopmessage-webhook") -> None:
        super().__init__(organization_api_key=None, webhook_authorization=webhook_authorization)
        self.sent: list[Dict[str, str]] = []
        self.statuses: Dict[str, Optional[MessageStatus]] = {}
        self.attachments: Dict[str, AttachmentContent] = {}
        self.crash_after_accept = False
        self.synchronous_error_code: Optional[int] = None

    def send_message(self, contact: str, text: str, sender: Optional[str], passthrough: str) -> SendResult:
        if self.synchronous_error_code is not None:
            raise ProviderRejectedError(self.synchronous_error_code)
        message_id = "fake-message-{}".format(len(self.sent) + 1)
        self.sent.append({"contact": contact, "text": text, "sender": sender or "", "passthrough": passthrough})
        self.statuses[message_id] = MessageStatus(message_id, "processing")
        if self.crash_after_accept:
            raise KeyboardInterrupt("injected process crash after provider acceptance")
        return SendResult(provider_message_id=message_id, status="accepted")

    def get_message_status(self, provider_message_id: str) -> Optional[MessageStatus]:
        return self.statuses.get(provider_message_id)

    def download_inbound_attachment(self, url: str) -> AttachmentContent:
        if url not in self.attachments:
            raise RuntimeError("injected attachment download failure")
        return self.attachments[url]

    def normalize_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        normalized = super().normalize_webhook(payload)
        return normalized
