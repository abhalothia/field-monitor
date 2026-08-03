import base64
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ffl.app import create_app
from ffl.persistence import repository
from ffl.services import procurement_capture
from ffl.services.trackolap_metrics import dashboard_metrics_for_source


CAPTURE_SAMPLE = b"""Season Code,Farmer Code,Harvested Quantity Qtl,Fortune Purchase Quantity Qtl,Snapshot Date
Kharif-2026,farmer-001,10,8,2026-11-10
Kharif-2026,farmer-002,15,15,2026-11-10
"""


def test_procurement_capture_retains_only_season_aggregate_and_unblocks_purchase_share(ffl_db, owner, tmp_path):
    result = procurement_capture.register_procurement_capture(
        ffl_db, CAPTURE_SAMPLE, owner.id, "fortune-purchase-export.csv", evidence_directory=str(tmp_path)
    )
    summary = procurement_capture.procurement_capture_summary(ffl_db, result["batch"].id)
    artifact = repository.get_evidence_artifact(ffl_db, result["batch"].evidence_artifact_id)

    assert result["idempotent"] is False
    assert summary["capture"] == {
        "season_code": "Kharif-2026",
        "snapshot_date": "2026-11-10",
        "reported_farmers": 2,
        "reported_harvest_qtl": 25.0,
        "fortune_purchase_qtl": 23.0,
        "purchase_share_percent": 92.0,
    }
    assert artifact is not None
    retained = Path(artifact.storage_reference).read_text()
    persisted_rows = repository.list_import_rows(ffl_db, result["batch"].id)
    assert "farmer-001" not in retained
    assert "farmer-002" not in retained
    assert "farmer-001" not in repr(persisted_rows)
    assert "farmer-002" not in repr({"summary": summary, "rows": [row.mapped for row in persisted_rows]})

    procurement_capture.review_procurement_capture(ffl_db, result["batch"].id, owner.id)
    procurement_capture.publish_procurement_capture(ffl_db, result["batch"].id, owner.id)
    metrics = dashboard_metrics_for_source(ffl_db, as_of="2026-11-11T12:00:00+05:30")

    assert metrics["outcomes"]["purchase_share"] == {
        "availability": "available",
        "season_code": "Kharif-2026",
        "snapshot_date": "2026-11-10",
        "reported_farmers": 2,
        "reported_harvest_qtl": 25.0,
        "fortune_purchase_qtl": 23.0,
        "share_percent": 92.0,
        "basis": "Fortune purchase quantity divided by linked growers' reported harvest quantity",
        "limitation": "reported-harvest coverage, not regional market share",
    }


def test_procurement_capture_rejects_duplicate_code_and_mixed_snapshot_scope(ffl_db, owner, tmp_path):
    duplicate = CAPTURE_SAMPLE + b"Kharif-2026,farmer-001,3,1,2026-11-10\n"
    result = procurement_capture.register_procurement_capture(
        ffl_db, duplicate, owner.id, evidence_directory=str(tmp_path)
    )
    assert result["counters"]["invalid_source_rows"] == 1

    mixed_season = CAPTURE_SAMPLE.replace(b"Kharif-2026,farmer-002", b"Rabi-2026,farmer-002")
    with pytest.raises(ValueError, match="one season"):
        procurement_capture.register_procurement_capture(
            ffl_db, mixed_season, owner.id, evidence_directory=str(tmp_path)
        )


def test_procurement_capture_api_is_manager_only_and_never_returns_farmer_code(tmp_path, monkeypatch):
    monkeypatch.setenv("FFL_EVIDENCE_DIR", str(tmp_path / "evidence"))
    app = create_app(str(tmp_path / "capture.db"), manager_api_token="manager-token")
    manager = repository.create_person(app.state.conn, "Pilot Manager", "farm_manager")
    app.state.manager_person_id = manager.id
    payload = {
        "content_base64": base64.b64encode(CAPTURE_SAMPLE).decode("ascii"),
        "original_filename": "fortune-purchase-export.csv",
    }
    with TestClient(app) as client:
        denied = client.post("/api/v1/procurement-capture/csv", json=payload)
        created = client.post(
            "/api/v1/procurement-capture/csv", json=payload,
            headers={"x-ffl-manager-token": "manager-token"},
        )
        batch_id = created.json()["batch"]["id"]
        detail = client.get(
            "/api/v1/procurement-capture/" + batch_id,
            headers={"x-ffl-manager-token": "manager-token"},
        )

    assert denied.status_code == 403
    assert created.status_code == 201
    assert detail.status_code == 200
    assert "farmer-001" not in detail.text
    assert "farmer-002" not in detail.text
