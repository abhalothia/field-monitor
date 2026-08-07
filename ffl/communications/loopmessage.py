"""The narrow adapter for the documented LoopMessage API surface."""

import hashlib
import hmac
import ipaddress
import os
import socket
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import httpx

from ffl.communications.ports import (
    AttachmentContent, MessageStatus, NormalizedInboundEvent, ProviderAmbiguousError,
    ProviderRejectedError, SendResult,
)


MAX_INBOUND_ATTACHMENT_BYTES = 10 * 1024 * 1024


class LoopMessageProvider:
    name = "loopmessage"

    def __init__(
        self, organization_api_key: Optional[str] = None, webhook_authorization: Optional[str] = None,
        sender_id: Optional[str] = None, api_base_url: Optional[str] = None, whatsapp_channel_enabled: bool = False,
        whatsapp_capability_proof: Optional[str] = None, whatsapp_capability_proof_ref: Optional[str] = None,
    ) -> None:
        self.organization_api_key = organization_api_key
        self.webhook_authorization = webhook_authorization
        self.sender_id = sender_id
        self.api_base_url = (api_base_url or "https://a.loopmessage.com").rstrip("/")
        self.whatsapp_channel_enabled = whatsapp_channel_enabled
        self.whatsapp_capability_proof = whatsapp_capability_proof
        self.whatsapp_capability_proof_ref = whatsapp_capability_proof_ref

    @classmethod
    def from_environment(cls) -> "LoopMessageProvider":
        return cls(
            organization_api_key=os.environ.get("FFL_LOOPMESSAGE_ORGANIZATION_API_KEY"),
            webhook_authorization=os.environ.get("FFL_LOOPMESSAGE_WEBHOOK_AUTHORIZATION"),
            sender_id=os.environ.get("FFL_LOOPMESSAGE_SENDER_ID"),
            api_base_url=os.environ.get("FFL_LOOPMESSAGE_API_BASE_URL"),
            whatsapp_channel_enabled=os.environ.get("FFL_LOOPMESSAGE_WHATSAPP_CHANNEL_ENABLED") == "true",
            whatsapp_capability_proof=os.environ.get("FFL_LOOPMESSAGE_WHATSAPP_CAPABILITY_PROOF"),
            whatsapp_capability_proof_ref=os.environ.get("FFL_LOOPMESSAGE_WHATSAPP_CAPABILITY_PROOF_REF"),
        )

    @property
    def whatsapp_capability_enabled(self) -> bool:
        return bool(
            self.organization_api_key
            and self.webhook_authorization
            and self.whatsapp_channel_enabled
            and self.sender_id
            and self.whatsapp_capability_proof == "sandbox-verified"
            and self.whatsapp_capability_proof_ref
        )

    def verify_webhook(self, authorization: Optional[str]) -> bool:
        if not self.webhook_authorization or authorization is None:
            return False
        return hmac.compare_digest(self.webhook_authorization, authorization)

    def send_message(self, contact: str, text: str, sender: Optional[str], passthrough: str) -> SendResult:
        if not self.organization_api_key:
            raise RuntimeError("LoopMessage credentials are not configured")
        if not self.whatsapp_capability_enabled:
            raise RuntimeError("validated WhatsApp capability is not configured")
        payload = self.build_send_payload(contact, text, sender, passthrough)
        response = httpx.post(
            self.api_base_url + "/api/v1/message/send/",
            headers={"Authorization": self.organization_api_key, "Content-Type": "application/json"},
            json=payload, timeout=15.0,
        )
        body = _json_body(response)
        # A 5xx can occur after the provider accepted the request.  It must be
        # reconciled, not converted into a decisive rejection and re-sent.
        if 500 <= response.status_code <= 599:
            raise ProviderAmbiguousError("LoopMessage send response was ambiguous")
        # Only a client-side HTTP rejection, or a structured rejection in an
        # otherwise successful response, is decisive.  Redirects and other
        # unusual non-2xx outcomes do not prove that LoopMessage did not
        # accept the send, so they enter the no-resend reconciliation path.
        if 400 <= response.status_code <= 499 or body.get("success") is False:
            raise ProviderRejectedError(_error_code(body))
        if not response.is_success:
            raise ProviderAmbiguousError("LoopMessage send response was ambiguous")
        if not body.get("message_id"):
            raise RuntimeError("LoopMessage did not accept the send request")
        return SendResult(provider_message_id=str(body["message_id"]), status="accepted")

    def send_template(
        self, contact: str, sender: str, template_id: str, locale: str,
        parameters: Dict[str, str], passthrough: str,
    ) -> SendResult:
        """Refuse live template traffic until the exact sandbox wire contract is proven."""
        raise RuntimeError("LoopMessage WhatsApp template contract is not sandbox-proven")

    def get_message_status(self, provider_message_id: str) -> Optional[MessageStatus]:
        """Use LoopMessage's documented status endpoint for an accepted message."""
        if not self.organization_api_key:
            raise RuntimeError("LoopMessage credentials are not configured")
        response = httpx.get(
            self.api_base_url + "/v1/message/status/{0}/".format(provider_message_id),
            headers={"Authorization": self.organization_api_key, "Content-Type": "application/json"}, timeout=15.0,
        )
        body = _json_body(response)
        if response.status_code == 404:
            return None
        if not response.is_success or body.get("success") is False:
            raise ProviderRejectedError(_error_code(body))
        value = body.get("status")
        if not isinstance(value, str) or value.lower() not in {"processing", "failed", "delivered", "unknown"}:
            raise RuntimeError("LoopMessage returned an invalid message status")
        return MessageStatus(str(body.get("message_id") or provider_message_id), value.lower(), _error_code(body))

    def download_inbound_attachment(self, url: str) -> AttachmentContent:
        """Retrieve a documented inbound attachment URL without retaining the URL.

        URLs originate in an authenticated provider webhook, but are still treated
        as untrusted input: HTTPS only, no credentials/redirects, no private IP
        targets, and a bounded response body.
        """
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("inbound attachment URL is not an allowed HTTPS URL")
        _require_public_host(parsed.hostname)
        with httpx.stream("GET", url, timeout=15.0, follow_redirects=False) as response:
            response.raise_for_status()
            media_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if not media_type:
                raise ValueError("inbound attachment has no media type")
            content = bytearray()
            for chunk in response.iter_bytes():
                content.extend(chunk)
                if len(content) > MAX_INBOUND_ATTACHMENT_BYTES:
                    raise ValueError("inbound attachment exceeds the size limit")
        if not content:
            raise ValueError("inbound attachment is empty")
        return AttachmentContent(bytes(content), media_type)

    def build_send_payload(self, contact: str, text: str, sender: Optional[str], passthrough: str) -> Dict[str, Any]:
        if not self.whatsapp_capability_enabled:
            raise RuntimeError("validated WhatsApp capability is not configured")
        payload: Dict[str, Any] = {
            "contact": contact,
            "text": text,
            "passthrough": passthrough,
            "channel": "whatsapp",
        }
        selected_sender = sender or self.sender_id
        if selected_sender:
            payload["sender"] = selected_sender
        return payload

    def normalize_webhook(self, payload: Dict[str, Any]) -> NormalizedInboundEvent:
        webhook_id = payload.get("webhook_id")
        event = payload.get("event")
        contact = payload.get("contact")
        if not isinstance(webhook_id, str) or not isinstance(event, str) or not isinstance(contact, str):
            raise ValueError("LoopMessage webhook requires webhook_id, event, and contact")
        attachments = payload.get("attachments") or []
        if not isinstance(attachments, list) or not all(isinstance(item, str) for item in attachments):
            raise ValueError("LoopMessage attachments must be URL strings")
        channel = payload.get("channel")
        if channel is not None and channel != "whatsapp":
            raise ValueError("LoopMessage inbound channel is not WhatsApp")
        sender = payload.get("sender")
        if self.whatsapp_capability_enabled:
            if not isinstance(sender, str) or not sender:
                raise ValueError("LoopMessage WhatsApp webhook requires sender")
            if not hmac.compare_digest(sender, self.sender_id):
                raise ValueError("LoopMessage WhatsApp webhook sender does not match the configured sender")
        return {
            "event_id": webhook_id,
            "message_id": str(payload.get("message_id", "")),
            "event_type": event,
            "contact": contact,
            "text": str(payload.get("text", "")),
            "message_type": str(payload.get("message_type", "text")),
            "attachments": attachments,
            "attachment_references": [_attachment_reference(webhook_id, item) for item in attachments],
            "channel": channel,
            # The private receipt retains the provider payload for recovery,
            # but ordinary event storage gets only this non-reversible marker.
            "sender_fingerprint": _sender_fingerprint(sender) if isinstance(sender, str) else None,
            "passthrough": payload.get("passthrough") if isinstance(payload.get("passthrough"), str) else None,
            # The provider correlation field is intentionally unmapped until
            # a non-production sandbox proves its exact wire location.
            "reply_to_message_id": None,
            "intent": None,
            "raw": payload,
        }


def _json_body(response: httpx.Response) -> Dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _error_code(body: Dict[str, Any]) -> Optional[int]:
    value = body.get("error_code")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _sender_fingerprint(sender: str) -> str:
    return hashlib.sha256(("loopmessage:sender:" + sender).encode("utf-8")).hexdigest()


def _attachment_reference(event_id: str, source: str) -> str:
    digest = hashlib.sha256(("loopmessage:attachment:" + event_id + ":" + source).encode("utf-8")).hexdigest()
    return "loopmessage-attachment:" + digest


def _require_public_host(hostname: str) -> None:
    try:
        addresses = {record[4][0] for record in socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)}
    except OSError as error:
        raise RuntimeError("could not resolve inbound attachment host") from error
    if not addresses:
        raise ValueError("inbound attachment host has no address")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise ValueError("inbound attachment host resolves to a non-public address")
