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
        ffl_db, b"plot,area\nNorth plot,5\n", "land_register", owner.id,
        reviewed_by=owner.id, evidence_directory=str(tmp_path),
    )
    malformed = imports.register_csv_import(
        ffl_db, b"land_parcel_id,area\nknown,5,extra\n", "land_register", owner.id,
        reviewed_by=owner.id, evidence_directory=str(tmp_path),
    )

    assert ambiguous["batch"].status == "review"
    assert ambiguous["counters"]["quarantined"] == 1
    assert malformed["counters"]["quarantined"] == 1
    first_errors = repository.list_import_rows(ffl_db, ambiguous["batch"].id)[0].validation_errors
    assert first_errors[0]["code"] == "ambiguous_identity"


def test_publish_is_blocked_for_reviewed_import_with_bad_rows(ffl_db, owner, tmp_path: Path):
    result = imports.register_csv_import(
        ffl_db, b"land_parcel_id\n\n", "land_register", owner.id,
        reviewed_by=owner.id, evidence_directory=str(tmp_path),
    )

    with pytest.raises(ValueError, match="invalid or quarantined"):
        imports.publish_import(ffl_db, result["batch"].id)

    assert repository.get_import_batch(ffl_db, result["batch"].id).status == "review"


def test_publish_marks_only_import_rows_and_never_overwrites_land(ffl_db, owner, tmp_path: Path):
    unit = repository.create_operating_unit(ffl_db, "Pilot")
    parcel = repository.create_land_parcel(ffl_db, unit.id, "Approved parcel", 2.5)
    result = imports.register_csv_import(
        ffl_db, f"land_parcel_id\n{parcel.id}\n".encode("utf-8"), "land_register", owner_id=owner.id,
        reviewed_by=owner.id, evidence_directory=str(tmp_path),
    )

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


def test_evidence_api_returns_422_for_invalid_base64(import_client):
    response = import_client.client.post(
        "/api/v1/evidence", json={"content_base64": "not base64", "media_type": "text/plain"}
    )

    assert response.status_code == 422
