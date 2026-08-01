import base64
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ffl.api.import_routes import router
from ffl.persistence import repository
from ffl.persistence.schema import create_schema
from ffl.services import evidence, imports


def test_evidence_content_hash_is_idempotent_and_written_once(ffl_db, owner, tmp_path: Path):
    content = b"field note: standing water at north edge"
    first = evidence.retain_evidence(
        ffl_db, content, "text/plain", "visit.txt", created_by_person_id=owner.id, directory=str(tmp_path)
    )
    replay = evidence.retain_evidence(
        ffl_db, content, "text/plain", "renamed.txt", created_by_person_id=owner.id, directory=str(tmp_path)
    )

    assert replay.id == first.id
    assert Path(first.storage_reference).read_bytes() == content
    assert len(repository.list_evidence_artifacts(ffl_db)) == 1


def test_pdf_is_retained_as_evidence_without_extraction(ffl_db, owner, tmp_path: Path):
    content = b"%PDF-1.4\nnot parsed by the import workbench\n"

    artifact = evidence.retain_evidence(
        ffl_db, content, "application/pdf", "soil-report.pdf", created_by_person_id=owner.id,
        directory=str(tmp_path),
    )

    assert artifact.media_type == "application/pdf"
    assert Path(artifact.storage_reference).read_bytes() == content
    assert ffl_db.execute("SELECT COUNT(*) AS count FROM field_signals").fetchone()["count"] == 0


def test_ambiguous_and_malformed_csv_rows_are_quarantined(ffl_db, owner, tmp_path: Path):
    ambiguous = imports.register_csv_import(
        ffl_db, b"plot,area\nNorth plot,5\n", "land_register", owner.id, evidence_directory=str(tmp_path),
    )
    malformed = imports.register_csv_import(
        ffl_db, b"land_parcel_id,area\nknown,5,extra\n", "land_register", owner.id, evidence_directory=str(tmp_path),
    )

    assert ambiguous["batch"].status == "profiled"
    assert ambiguous["counters"]["quarantined"] == 1
    assert malformed["counters"]["quarantined"] == 1
    first_errors = repository.list_import_rows(ffl_db, ambiguous["batch"].id)[0].validation_errors
    assert first_errors[0]["code"] == "ambiguous_identity"


def test_publish_is_blocked_for_reviewed_import_with_bad_rows(ffl_db, owner, tmp_path: Path):
    result = imports.register_csv_import(
        ffl_db, b"land_parcel_id\n\n", "land_register", owner.id, evidence_directory=str(tmp_path),
    )
    reviewed = imports.review_import(ffl_db, result["batch"].id, owner.id)

    with pytest.raises(ValueError, match="invalid or quarantined"):
        imports.publish_import(ffl_db, result["batch"].id)

    assert reviewed.reviewed_by_id == owner.id
    assert repository.get_import_batch(ffl_db, result["batch"].id).status == "review"


def test_publish_marks_only_import_rows_and_never_overwrites_land(ffl_db, owner, tmp_path: Path):
    unit = repository.create_operating_unit(ffl_db, "Pilot")
    parcel = repository.create_land_parcel(ffl_db, unit.id, "Approved parcel", 2.5)
    result = imports.register_csv_import(
        ffl_db, f"land_parcel_id\n{parcel.id}\n".encode("utf-8"), "land_register", owner_id=owner.id,
        evidence_directory=str(tmp_path),
    )
    imports.review_import(ffl_db, result["batch"].id, owner.id)

    published = imports.publish_import(ffl_db, result["batch"].id)

    assert published["batch"].status == "published"
    assert published["counters"]["published"] == 1
    approved = ffl_db.execute(
        "SELECT name, area_hectares FROM land_parcels WHERE id = ?", (parcel.id,)
    ).fetchone()
    assert (approved["name"], approved["area_hectares"]) == ("Approved parcel", 2.5)


def test_csv_replay_with_same_purpose_returns_same_batch(ffl_db, owner, tmp_path: Path):
    content = b"plot,area\nNorth plot,5\n"
    first = imports.register_csv_import(
        ffl_db, content, "land_register", owner.id, evidence_directory=str(tmp_path)
    )
    replay = imports.register_csv_import(
        ffl_db, content, "land_register", owner.id, evidence_directory=str(tmp_path)
    )

    assert replay["idempotent"] is True
    assert replay["batch"].id == first["batch"].id


def test_same_content_with_a_different_purpose_is_rejected(ffl_db, owner, tmp_path: Path):
    content = b"plot,area\nNorth plot,5\n"
    imports.register_csv_import(ffl_db, content, "land_register", owner.id, evidence_directory=str(tmp_path))

    with pytest.raises(ValueError, match="different import purpose"):
        imports.register_csv_import(ffl_db, content, "field_visit", owner.id, evidence_directory=str(tmp_path))


def test_import_registration_rolls_back_rows_after_forced_integrity_error(ffl_db, owner, tmp_path: Path, monkeypatch):
    original = repository.create_import_row

    def fail_row(*args, **kwargs):
        raise sqlite3.IntegrityError("simulated row race")

    monkeypatch.setattr(repository, "create_import_row", fail_row)
    with pytest.raises(sqlite3.IntegrityError, match="simulated row race"):
        imports.register_csv_import(
            ffl_db, b"plot,area\nNorth plot,5\n", "land_register", owner.id, evidence_directory=str(tmp_path)
        )

    assert ffl_db.execute("SELECT COUNT(*) AS count FROM import_batches").fetchone()["count"] == 0
    assert ffl_db.execute("SELECT COUNT(*) AS count FROM import_rows").fetchone()["count"] == 0
    monkeypatch.setattr(repository, "create_import_row", original)
    retry = imports.register_csv_import(
        ffl_db, b"plot,area\nNorth plot,5\n", "land_register", owner.id, evidence_directory=str(tmp_path)
    )
    assert retry["counters"]["total"] == 1


def test_concurrent_unique_conflict_returns_established_batch(ffl_db, owner, tmp_path: Path, monkeypatch):
    content = b"plot,area\nNorth plot,5\n"
    artifact = evidence.retain_evidence(ffl_db, content, "text/csv", created_by_person_id=owner.id, directory=str(tmp_path))
    established = repository.create_import_batch(
        ffl_db, "land_register", artifact.content_hash, artifact.id, "csv-v1", owner.id, {"headers": ["plot"]},
        status="profiled",
    )
    original_get = repository.get_import_batch_by_content_hash
    calls = {"count": 0}

    def stale_then_actual(conn, content_hash):
        calls["count"] += 1
        return None if calls["count"] <= 2 else original_get(conn, content_hash)

    monkeypatch.setattr(repository, "get_import_batch_by_content_hash", stale_then_actual)
    replay = imports.register_csv_import(
        ffl_db, content, "land_register", owner.id, evidence_directory=str(tmp_path)
    )

    assert replay["idempotent"] is True
    assert replay["batch"].id == established.id
    assert ffl_db.execute("SELECT COUNT(*) AS count FROM import_rows").fetchone()["count"] == 0


@pytest.fixture
def import_client(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FFL_EVIDENCE_DIR", str(tmp_path / "evidence"))
    app = FastAPI()
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    create_schema(conn)
    owner = repository.create_person(conn, "Import Owner", "agronomist")
    app.state.conn = conn
    app.include_router(router)
    return SimpleNamespace(client=TestClient(app), owner=owner)


def test_import_api_converts_validation_and_missing_batches(import_client):
    encoded = base64.b64encode(b"plot,area\nNorth,5\n").decode("ascii")
    invalid = import_client.client.post(
        "/api/v1/imports/csv",
        json={"content_base64": encoded, "purpose": "roster", "owner_id": import_client.owner.id},
    )
    missing = import_client.client.get("/api/v1/imports/not-a-batch")
    publish_missing = import_client.client.post("/api/v1/imports/not-a-batch/publish")

    assert invalid.status_code == 422
    assert missing.status_code == 404
    assert publish_missing.status_code == 404


def test_import_api_requires_a_real_review_before_publish(import_client):
    encoded = base64.b64encode(b"plot,area\nNorth,5\n").decode("ascii")
    created = import_client.client.post(
        "/api/v1/imports/csv",
        json={
            "content_base64": encoded,
            "purpose": "land_register",
            "owner_id": import_client.owner.id,
            "reviewed_by": import_client.owner.id,
        },
    )
    batch_id = created.json()["batch"]["id"]
    before_review = import_client.client.post("/api/v1/imports/{}/publish".format(batch_id))
    review = import_client.client.post(
        "/api/v1/imports/{}/review".format(batch_id), json={"reviewer_id": import_client.owner.id}
    )

    assert created.status_code == 201
    assert created.json()["batch"]["status"] == "profiled"
    assert created.json()["batch"]["reviewed_by_id"] is None
    assert before_review.status_code == 422
    assert review.status_code == 200
    assert review.json()["batch"]["reviewed_by_id"] == import_client.owner.id


def test_evidence_api_returns_422_for_invalid_base64(import_client):
    response = import_client.client.post(
        "/api/v1/evidence", json={"content_base64": "not base64", "media_type": "text/plain"}
    )

    assert response.status_code == 422


def test_evidence_api_uses_final_upsert_result_for_idempotency(import_client):
    payload = {
        "content_base64": base64.b64encode(b"a field note").decode("ascii"),
        "media_type": "text/plain",
    }

    first = import_client.client.post("/api/v1/evidence", json=payload)
    replay = import_client.client.post("/api/v1/evidence", json=payload)

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.json()["id"] == first.json()["id"]


def test_schema_migrates_existing_import_batch_table_with_reviewer_column():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """CREATE TABLE import_batches (
            id TEXT PRIMARY KEY, purpose TEXT NOT NULL, status TEXT NOT NULL, content_hash TEXT NOT NULL UNIQUE,
            evidence_artifact_id TEXT NOT NULL, mapping_version TEXT NOT NULL, source_id TEXT, owner_id TEXT NOT NULL,
            received_at TEXT NOT NULL, reviewed_at TEXT, published_at TEXT, profile_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )"""
    )

    create_schema(conn)

    columns = {row[1] for row in conn.execute("PRAGMA table_info(import_batches)").fetchall()}
    assert "reviewed_by_id" in columns
    conn.close()
