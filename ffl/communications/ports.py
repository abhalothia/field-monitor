from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional, Protocol, TypedDict


ConstrainedIntent = Literal[
    "confirm", "decline", "report_deviation", "submit_evidence",
    "request_callback", "help", "opt_out",
]


class TemplateSend(TypedDict):
    """Provider-neutral input for one approved WhatsApp template send."""

    contact: str
    sender: str
    template_id: str
    locale: str
    parameters: Dict[str, str]
    passthrough: str


class NormalizedInboundEvent(TypedDict):
    """Minimum normalized event used while processing a sealed receipt."""

    event_id: str
    message_id: str
    event_type: str
    contact: str
    text: str
    message_type: str
    attachments: list[str]
    attachment_references: list[str]
    channel: Optional[str]
    sender_fingerprint: Optional[str]
    passthrough: Optional[str]
    reply_to_message_id: Optional[str]
    intent: Optional[ConstrainedIntent]
    raw: Dict[str, Any]


@dataclass(frozen=True)
class SendResult:
    provider_message_id: str
    status: str


@dataclass(frozen=True)
class MessageStatus:
    provider_message_id: str
    status: str
    error_code: Optional[int] = None


@dataclass(frozen=True)
class AttachmentContent:
    content: bytes
    media_type: str


class ProviderRejectedError(RuntimeError):
    """A provider returned a definite structured rejection, not a timeout."""

    def __init__(self, error_code: Optional[int] = None) -> None:
        self.error_code = error_code
        super().__init__("provider rejected message" if error_code is None else "provider rejected message ({0})".format(error_code))


class ProviderAmbiguousError(RuntimeError):
    """The provider might have accepted a request, but FFL cannot prove it."""


class CommunicationsProvider(Protocol):
    name: str

    def verify_webhook(self, authorization: Optional[str]) -> bool:
        ...

    def send_message(self, contact: str, text: str, sender: Optional[str], passthrough: str) -> SendResult:
        ...

    def send_template(
        self, contact: str, sender: str, template_id: str, locale: str,
        parameters: Dict[str, str], passthrough: str,
    ) -> SendResult:
        ...

    def get_message_status(self, provider_message_id: str) -> Optional[MessageStatus]:
        ...

    def download_inbound_attachment(self, url: str) -> AttachmentContent:
        ...

    def normalize_webhook(self, payload: Dict[str, Any]) -> NormalizedInboundEvent:
        ...
