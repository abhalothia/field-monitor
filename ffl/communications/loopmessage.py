"""The narrow adapter for the documented LoopMessage API surface."""

import hmac
import os
from typing import Any, Dict, Optional

import httpx

from ffl.communications.ports import SendResult


class LoopMessageProvider:
    name = "loopmessage"

    def __init__(
        self, organization_api_key: Optional[str] = None, webhook_authorization: Optional[str] = None,
        sender_id: Optional[str] = None, api_base_url: Optional[str] = None, whatsapp_channel_enabled: bool = False,
    ) -> None:
        self.organization_api_key = organization_api_key
        self.webhook_authorization = webhook_authorization
        self.sender_id = sender_id
        self.api_base_url = (api_base_url or "https://a.loopmessage.com").rstrip("/")
        self.whatsapp_channel_enabled = whatsapp_channel_enabled

    @classmethod
    def from_environment(cls) -> "LoopMessageProvider":
        return cls(
            organization_api_key=os.environ.get("FFL_LOOPMESSAGE_ORGANIZATION_API_KEY"),
            webhook_authorization=os.environ.get("FFL_LOOPMESSAGE_WEBHOOK_AUTHORIZATION"),
            sender_id=os.environ.get("FFL_LOOPMESSAGE_SENDER_ID"),
            api_base_url=os.environ.get("FFL_LOOPMESSAGE_API_BASE_URL"),
            whatsapp_channel_enabled=os.environ.get("FFL_LOOPMESSAGE_WHATSAPP_CHANNEL_ENABLED") == "true",
        )

    def verify_webhook(self, authorization: Optional[str]) -> bool:
        if not self.webhook_authorization or authorization is None:
            return False
        return hmac.compare_digest(self.webhook_authorization, authorization)

    def send_message(self, contact: str, text: str, sender: Optional[str], passthrough: str) -> SendResult:
        if not self.organization_api_key:
            raise RuntimeError("LoopMessage credentials are not configured")
        payload = self.build_send_payload(contact, text, sender, passthrough)
        response = httpx.post(
            self.api_base_url + "/api/v1/message/send/",
            headers={"Authorization": self.organization_api_key, "Content-Type": "application/json"},
            json=payload, timeout=15.0,
        )
        response.raise_for_status()
        body = response.json()
        if body.get("success") is False or not body.get("message_id"):
            raise RuntimeError("LoopMessage did not accept the send request")
        return SendResult(provider_message_id=str(body["message_id"]), status="accepted")

    def build_send_payload(self, contact: str, text: str, sender: Optional[str], passthrough: str) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "contact": contact,
            "text": text,
            "passthrough": passthrough,
        }
        if self.whatsapp_channel_enabled:
            payload["channel"] = "whatsapp"
        selected_sender = sender or self.sender_id
        if selected_sender:
            payload["sender"] = selected_sender
        return payload

    def normalize_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        webhook_id = payload.get("webhook_id")
        event = payload.get("event")
        contact = payload.get("contact")
        if not isinstance(webhook_id, str) or not isinstance(event, str) or not isinstance(contact, str):
            raise ValueError("LoopMessage webhook requires webhook_id, event, and contact")
        attachments = payload.get("attachments") or []
        if not isinstance(attachments, list) or not all(isinstance(item, str) for item in attachments):
            raise ValueError("LoopMessage attachments must be URL strings")
        return {
            "event_id": webhook_id,
            "message_id": str(payload.get("message_id", "")),
            "event_type": event,
            "contact": contact,
            "text": str(payload.get("text", "")),
            "message_type": str(payload.get("message_type", "text")),
            "attachments": attachments,
            "raw": payload,
        }
