from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol


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

    def get_message_status(self, provider_message_id: str) -> Optional[MessageStatus]:
        ...

    def download_inbound_attachment(self, url: str) -> AttachmentContent:
        ...

    def normalize_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        ...
