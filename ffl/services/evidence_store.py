"""Private, content-addressed evidence storage boundary.

The operating database stores a stable ``supabase://`` reference, never a
public object URL.  A production Vercel function is the only component that
holds the Storage key; browser clients receive neither that key nor a bucket
path.  Local/test callers retain the earlier filesystem implementation.
"""

import hashlib
import os
from pathlib import Path
import re
from typing import Callable, Optional, Protocol, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


_BUCKET = re.compile(r"[a-z0-9][a-z0-9_-]{2,62}")


class EvidenceStoreError(RuntimeError):
    """Storage failed without exposing remote response content to the API."""


class EvidenceStoreUnavailable(EvidenceStoreError):
    """A production runtime is missing its private evidence-store boundary."""


class EvidenceStore(Protocol):
    def put_content_addressed(self, content_hash: str, content: bytes, media_type: str) -> str:
        """Retain bytes once and return a non-public immutable reference."""


class LocalEvidenceStore:
    """Small filesystem store for local development and deterministic tests."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def put_content_addressed(self, content_hash: str, content: bytes, media_type: str) -> str:
        from ffl.services.evidence import _write_content_once

        _write_content_once(self.directory / content_hash, content)
        return str(self.directory / content_hash)


class UnavailableEvidenceStore:
    """Fail closed instead of silently storing evidence in Vercel's /tmp."""

    def __init__(self, detail: str) -> None:
        self.detail = detail

    def put_content_addressed(self, content_hash: str, content: bytes, media_type: str) -> str:
        raise EvidenceStoreUnavailable(self.detail)


Requester = Callable[[str, str, Optional[bytes], dict], Tuple[int, bytes]]


class SupabasePrivateEvidenceStore:
    """Server-only REST adapter for a private Supabase Storage bucket.

    Content-addressed writes use ``x-upsert: false``.  A 409 race is accepted
    only after the adapter downloads and hashes the already-stored object; it
    never overwrites an object merely because a path is occupied.
    """

    def __init__(self, origin: str, service_key: str, bucket: str, requester: Optional[Requester] = None) -> None:
        parsed = urlparse(origin.rstrip("/"))
        if parsed.scheme != "https" or not parsed.netloc or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise ValueError("FFL_EVIDENCE_STORAGE_URL must be an HTTPS Supabase project origin")
        if not isinstance(service_key, str) or not service_key.strip():
            raise ValueError("FFL_EVIDENCE_STORAGE_KEY must be configured")
        if _BUCKET.fullmatch(bucket) is None:
            raise ValueError("FFL_EVIDENCE_STORAGE_BUCKET is invalid")
        self.origin = origin.rstrip("/")
        self.service_key = service_key
        self.bucket = bucket
        self._requester = requester or self._urllib_request

    def _headers(self, media_type: Optional[str] = None) -> dict:
        headers = {
            "Authorization": "Bearer " + self.service_key,
            "apikey": self.service_key,
        }
        if media_type is not None:
            headers["Content-Type"] = media_type
        return headers

    @staticmethod
    def _urllib_request(method: str, url: str, content: Optional[bytes], headers: dict) -> Tuple[int, bytes]:
        request = Request(url, data=content, headers=headers, method=method)
        try:
            with urlopen(request, timeout=20) as response:
                return response.status, response.read()
        except HTTPError as error:
            # Remote response bodies can contain provider detail.  The API
            # surface does not need it, so retain only the numerical status.
            return error.code, b""
        except URLError as error:
            raise EvidenceStoreError("private evidence storage is unavailable") from error

    def _object_path(self, content_hash: str) -> str:
        return "sha256/{0}/{1}".format(content_hash[:2], content_hash)

    def _object_url(self, prefix: str, object_path: str) -> str:
        segments = [self.origin, "storage", "v1", "object"]
        if prefix:
            segments.append(prefix)
        segments.extend([quote(self.bucket, safe=""), quote(object_path, safe="/")])
        return "/".join(segments)

    def put_content_addressed(self, content_hash: str, content: bytes, media_type: str) -> str:
        object_path = self._object_path(content_hash)
        headers = self._headers(media_type)
        headers["x-upsert"] = "false"
        status, _ = self._requester(
            "POST", self._object_url("", object_path), content, headers
        )
        if 200 <= status < 300:
            return "supabase://{0}/{1}".format(self.bucket, object_path)
        if status != 409:
            raise EvidenceStoreError("private evidence storage rejected the upload")
        read_status, established = self._requester(
            "GET", self._object_url("authenticated", object_path), None, self._headers()
        )
        if read_status == 200 and hashlib.sha256(established).hexdigest() == content_hash:
            return "supabase://{0}/{1}".format(self.bucket, object_path)
        raise EvidenceStoreError("existing private evidence object does not match its content hash")


def evidence_store_from_environment() -> EvidenceStore:
    """Resolve exactly one retention backend without ever falling back on Vercel."""

    backend = os.environ.get("FFL_EVIDENCE_STORE", "").strip().lower()
    if backend == "supabase":
        origin = os.environ.get("FFL_EVIDENCE_STORAGE_URL")
        key = os.environ.get("FFL_EVIDENCE_STORAGE_KEY")
        bucket = os.environ.get("FFL_EVIDENCE_STORAGE_BUCKET", "agro-evidence")
        if not origin or not key:
            return UnavailableEvidenceStore("private evidence storage is not configured")
        try:
            return SupabasePrivateEvidenceStore(origin, key, bucket)
        except ValueError:
            return UnavailableEvidenceStore("private evidence storage is not configured")
    if backend not in {"", "local"}:
        return UnavailableEvidenceStore("private evidence storage backend is not supported")
    if os.environ.get("VERCEL"):
        return UnavailableEvidenceStore("private evidence storage is not configured")
    from ffl.services.evidence import evidence_directory

    return LocalEvidenceStore(evidence_directory())
