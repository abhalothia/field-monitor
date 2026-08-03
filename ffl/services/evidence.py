"""Local-pilot evidence retention.

Evidence is deliberately stored outside SQLite.  SQLite only retains an immutable
content address and a local reference; document interpretation belongs to a
separately approved processor.
"""

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Optional

from ffl.domain.models import EvidenceArtifact
from ffl.persistence import repository
from ffl.services.evidence_store import EvidenceStore, LocalEvidenceStore


ALLOWED_MEDIA_TYPES = {
    "text/csv",
    "text/plain",
    "application/zip",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
MAX_DIRECT_EVIDENCE_BYTES = 3 * 1024 * 1024


def evidence_directory(directory: Optional[str] = None) -> Path:
    """Return the configured local evidence root, creating it only when needed."""
    configured = directory or os.environ.get("FFL_EVIDENCE_DIR", "/tmp/ffl-evidence")
    return Path(configured).expanduser().resolve()


def _validate_media_type(media_type: str) -> None:
    if media_type in ALLOWED_MEDIA_TYPES or media_type.startswith("image/"):
        return
    raise ValueError("unsupported evidence media type")


def _write_content_once(path: Path, content: bytes) -> None:
    """Atomically materialize a content-addressed file without replacing one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if hashlib.sha256(path.read_bytes()).hexdigest() != path.name:
            raise ValueError("existing evidence file does not match its content hash")
        return
    descriptor, temporary_name = tempfile.mkstemp(prefix=".upload-", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary_name, path)
        except FileExistsError:
            # Another request won the same content-addressed write.  Its digest
            # is checked below before this request returns.
            pass
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
        if hashlib.sha256(path.read_bytes()).hexdigest() != path.name:
            raise ValueError("stored evidence file does not match its content hash")
        try:
            path.chmod(0o444)
        except OSError:
            # Read-only permissions are a best-effort guard; the content hash is
            # the durable immutability check on filesystems without POSIX modes.
            pass
    except Exception:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
        raise


def retain_evidence(
    conn,
    content: bytes,
    media_type: str,
    original_filename: Optional[str] = None,
    source_uri: Optional[str] = None,
    created_by_person_id: Optional[str] = None,
    directory: Optional[str] = None,
    store: Optional[EvidenceStore] = None,
) -> EvidenceArtifact:
    """Retain supported evidence and return its idempotent content-addressed record.

    This function never parses a PDF, DOCX, or image and never creates an
    operating record from its contents.
    """
    artifact, _ = retain_evidence_result(
        conn, content, media_type, original_filename, source_uri, created_by_person_id, directory, store
    )
    return artifact


def retain_evidence_result(
    conn,
    content: bytes,
    media_type: str,
    original_filename: Optional[str] = None,
    source_uri: Optional[str] = None,
    created_by_person_id: Optional[str] = None,
    directory: Optional[str] = None,
    store: Optional[EvidenceStore] = None,
) -> tuple[EvidenceArtifact, bool]:
    """Retain evidence and report whether this call established the database record."""
    if not isinstance(content, bytes) or not content:
        raise ValueError("evidence content must be non-empty bytes")
    if len(content) > MAX_DIRECT_EVIDENCE_BYTES:
        raise ValueError("direct evidence upload must be at most 3 MiB")
    _validate_media_type(media_type)
    if created_by_person_id is not None and conn.execute(
        "SELECT 1 FROM people WHERE id = ?", (created_by_person_id,)
    ).fetchone() is None:
        raise ValueError("evidence creator does not exist")
    content_hash = hashlib.sha256(content).hexdigest()
    established = repository.get_evidence_artifact_by_hash(conn, content_hash)
    if established is not None:
        return established, False
    resolved_store = store or LocalEvidenceStore(evidence_directory(directory))
    storage_reference = resolved_store.put_content_addressed(content_hash, content, media_type)
    return repository.create_evidence_artifact_if_absent(
        conn,
        content_hash=content_hash,
        media_type=media_type,
        storage_reference=storage_reference,
        original_filename=original_filename,
        size_bytes=len(content),
        source_uri=source_uri,
        created_by_person_id=created_by_person_id,
    )
