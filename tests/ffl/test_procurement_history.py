import base64
from dataclasses import asdict
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ffl.app import create_app
from ffl.persistence import repository
from ffl.services import procurement_history


PURCHASE_SAMPLE = b"""Entry Date,Purchase: Paddy Purchase Number,Farmer Name,Village,Rate Per Qtl,Bag,Paddy Quantity Qtl,PO Name,Variety Type,Supply Bill No. (1st Attempt)
2025-12-27,PP-001,Asha Devi,Nangla Chamru,100,4,2,Buyer One,Pusa 1121,BILL-001
2025-12-28,PP-002,Bharat Singh,Nangla Chamru,200,6,3,Buyer Two,Pusa 1121,BILL-002
2026-01-02,PP-003,Chitra Kumar,Chhapraula,150,2,1,Buyer One,1509,BILL-003
"""


def test_procurement_history_retains_only_aggregates_not_farmer_or_transaction_data(ffl_db, owner, tmp_path):
    result = procurement_history.register_procurement_history(
        ffl_db, PURCHASE_SAMPLE, owner.id, "all_purchases_Dec27.csv", evidence_directory=str(tmp_path)
    )
    summary = procurement_history.procurement_history_summary(ffl_db, result["batch"].id)
    artifact = repository.get_evidence_artifact(ffl_db, result["batch"].evidence_artifact_id)

    assert result["idempotent"] is False
    assert summary["counters"]["cohorts"] == 2
    assert summary["coverage"] == {
        "months": ["2025-12", "2026-01"],
        "villages": 2,
        "varieties": 2,
        "quantity_qtl": 6.0,
        "weighted_rate_per_qtl": 158.333,
    }
    assert artifact is not None
    retained = Path(artifact.storage_reference).read_text()
    assert "Asha" not in retained
    assert "PP-001" not in retained
    assert "Buyer One" not in retained
    assert "BILL-001" not in retained
    assert "Nangla Chamru" in retained
    assert "160.0" in retained
    manager_surface = dict(summary, batch=asdict(summary["batch"]))
    assert "Asha" not in json.dumps(manager_surface)
    assert "PP-001" not in json.dumps(manager_surface)


def test_procurement_history_is_reviewed_and_published_without_creating_farms(ffl_db, owner, tmp_path):
    result = procurement_history.register_procurement_history(
        ffl_db, PURCHASE_SAMPLE, owner.id, evidence_directory=str(tmp_path)
    )
    procurement_history.review_procurement_history(ffl_db, result["batch"].id, owner.id)
    published = procurement_history.publish_procurement_history(ffl_db, result["batch"].id, owner.id)

    assert published["batch"].status == "published"
    assert published["counters"]["published"] == 2
    assert ffl_db.execute("SELECT COUNT(*) FROM operating_units").fetchone()[0] == 0
    assert ffl_db.execute("SELECT COUNT(*) FROM land_parcels").fetchone()[0] == 0


def test_procurement_history_skips_bad_rows_and_rejects_unknown_columns(ffl_db, owner, tmp_path):
    one_bad = PURCHASE_SAMPLE + b"not-a-date,PP-004,Dinesh,Nangla Chamru,100,1,1,Buyer,Pusa 1121,BILL-004\n"
    unknown_column = PURCHASE_SAMPLE.replace(b"Entry Date,", b"Entry Date,Home Address,", 1)

    result = procurement_history.register_procurement_history(ffl_db, one_bad, owner.id, evidence_directory=str(tmp_path))
    assert result["counters"]["invalid_source_rows"] == 1
    with pytest.raises(ValueError, match="unsupported columns"):
        procurement_history.register_procurement_history(ffl_db, unknown_column, owner.id, evidence_directory=str(tmp_path))


def test_procurement_history_api_is_manager_only_and_returns_only_cohort_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("FFL_EVIDENCE_DIR", str(tmp_path / "evidence"))
    app = create_app(str(tmp_path / "purchases.db"), manager_api_token="manager-token")
    manager = repository.create_person(app.state.conn, "Pilot Manager", "farm_manager")
    app.state.manager_person_id = manager.id
    payload = {
        "content_base64": base64.b64encode(PURCHASE_SAMPLE).decode("ascii"),
        "original_filename": "all_purchases_Dec27.csv",
    }
    with TestClient(app) as client:
        denied = client.post("/api/v1/procurement-history/csv", json=payload)
        created = client.post(
            "/api/v1/procurement-history/csv", json=payload,
            headers={"x-ffl-manager-token": "manager-token"},
        )
        batch_id = created.json()["batch"]["id"]
        detail = client.get(
            "/api/v1/procurement-history/" + batch_id,
            headers={"x-ffl-manager-token": "manager-token"},
        )
        generic = client.get("/api/v1/imports/" + batch_id)

    assert denied.status_code == 403
    assert created.status_code == 201
    assert detail.status_code == 200
    assert "Asha" not in detail.text
    assert "PP-001" not in detail.text
    assert generic.status_code == 404
