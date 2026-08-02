import hashlib

import pytest

from ffl.services import evidence
from ffl.services.evidence_store import (
    EvidenceStoreUnavailable,
    SupabasePrivateEvidenceStore,
    evidence_store_from_environment,
)


class FakeEvidenceStore:
    def __init__(self):
        self.calls = []

    def put_content_addressed(self, content_hash, content, media_type):
        self.calls.append((content_hash, content, media_type))
        return "fake-private://evidence/" + content_hash


def test_evidence_store_is_content_addressed_and_database_replay_skips_second_upload(ffl_db, owner):
    store = FakeEvidenceStore()
    content = b"signed soil report"

    first, created = evidence.retain_evidence_result(
        ffl_db, content, "application/pdf", created_by_person_id=owner.id, store=store
    )
    replay, replay_created = evidence.retain_evidence_result(
        ffl_db, content, "application/pdf", created_by_person_id=owner.id, store=store
    )

    assert created is True
    assert replay_created is False
    assert replay.id == first.id
    assert first.storage_reference == "fake-private://evidence/" + hashlib.sha256(content).hexdigest()
    assert store.calls == [(hashlib.sha256(content).hexdigest(), content, "application/pdf")]


def test_supabase_store_refuses_overwrite_and_verifies_a_concurrent_object():
    content = b"field-photo-bytes"
    digest = hashlib.sha256(content).hexdigest()
    calls = []

    def requester(method, url, body, headers):
        calls.append((method, url, body, headers))
        return (409, b"") if method == "POST" else (200, content)

    store = SupabasePrivateEvidenceStore(
        "https://example.supabase.co", "server-only-key", "agro-evidence", requester=requester
    )

    reference = store.put_content_addressed(digest, content, "image/jpeg")

    assert reference == "supabase://agro-evidence/sha256/{0}/{1}".format(digest[:2], digest)
    assert calls[0][0] == "POST"
    assert calls[0][3]["x-upsert"] == "false"
    assert "/storage/v1/object/agro-evidence/sha256/" in calls[0][1]
    assert calls[1][0] == "GET"
    assert "/storage/v1/object/authenticated/agro-evidence/sha256/" in calls[1][1]


def test_vercel_evidence_configuration_fails_closed(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("FFL_EVIDENCE_STORE", raising=False)

    store = evidence_store_from_environment()

    with pytest.raises(EvidenceStoreUnavailable, match="not configured"):
        store.put_content_addressed("a" * 64, b"x", "text/plain")


def test_direct_evidence_size_is_bounded_before_storage(ffl_db, owner):
    store = FakeEvidenceStore()

    with pytest.raises(ValueError, match="at most 3 MiB"):
        evidence.retain_evidence_result(
            ffl_db, b"x" * ((3 * 1024 * 1024) + 1), "text/plain", created_by_person_id=owner.id, store=store
        )

    assert store.calls == []
