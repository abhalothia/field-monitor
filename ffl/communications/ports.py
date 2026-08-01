from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol


@dataclass(frozen=True)
class SendResult:
    provider_message_id: str
    status: str


class CommunicationsProvider(Protocol):
    name: str

    def verify_webhook(self, authorization: Optional[str]) -> bool:
        ...

    def send_message(self, contact: str, text: str, sender: Optional[str], passthrough: str) -> SendResult:
        ...

    def normalize_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        ...
