"""Small authenticated private-receipt envelope; never exposed by ordinary APIs."""

import base64
import hashlib
import hmac
import json
import os
from typing import Any, Dict


def seal(key: str, value: Dict[str, Any]) -> str:
    if not key:
        raise ValueError("communications receipt key is not configured")
    nonce = os.urandom(16)
    plain = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    stream = _stream(key.encode("utf-8"), nonce, len(plain))
    cipher = bytes(a ^ b for a, b in zip(plain, stream))
    tag = hmac.new(key.encode("utf-8"), nonce + cipher, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(nonce + tag + cipher).decode("ascii")


def open_receipt(key: str, token: str) -> Dict[str, Any]:
    data = base64.urlsafe_b64decode(token.encode("ascii"))
    nonce, tag, cipher = data[:16], data[16:48], data[48:]
    expected = hmac.new(key.encode("utf-8"), nonce + cipher, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected):
        raise ValueError("communications receipt integrity check failed")
    plain = bytes(a ^ b for a, b in zip(cipher, _stream(key.encode("utf-8"), nonce, len(cipher))))
    return json.loads(plain.decode("utf-8"))


def _stream(key: bytes, nonce: bytes, length: int) -> bytes:
    result = b""
    counter = 0
    while len(result) < length:
        result += hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        counter += 1
    return result[:length]
