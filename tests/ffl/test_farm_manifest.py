import base64
from dataclasses import asdict
import json

import pytest
from fastapi.testclient import TestClient

from ffl.app import create_app
from ffl.persistence import repository
from ffl.services import imports


VALID_MANIFEST = b"""source_farm_id,record_status,state_name,district_name,village_name,pincode,source_recorded_at,source_record_ref,crop_name,season_name,latitude,longitude,location_precision,boundary_evidence_ref
FRL-001,active,Uttar Pradesh,Gautam Buddha Nagar,Nangla Chamru,201314,2026-08-02T08:00:00+05:30,trace:FRL-001,Pusa Basmati 1121,Kharif 2026,28.5534523,77.5555503,field_verified,boundary:sha256:example-001
FRL-002,active,Uttar Pradesh,Gautam Buddha Nagar,Chhapraula,201301,2026-08-02T08:00:00+05:30,trace:FRL-002,Pusa Basmati 1121,Kharif 2026,,,,
"""

PLOT_MANIFEST = b'''source_farm_id,source_plot_id,plot_label,area_hectares,record_status,state_name,district_name,subdistrict_name,village_name,village_lgd_code,pincode,source_recorded_at,source_record_ref,crop_name,cultivar,season_name,latitude,longitude,boundary_geojson,location_precision,boundary_evidence_ref
FRL-001,PLOT-A,North block,2.5,active,Uttar Pradesh,Gautam Buddha Nagar,Dadri,Nangla Chamru,123456,201314,2026-08-02T08:00:00+05:30,trace:PLOT-A,Pusa Basmati 1121,1121,Kharif 2026,,,"{""type"":""Polygon"",""coordinates"":[[[77.5500,28.5500],[77.5600,28.5500],[77.5600,28.5600],[77.5500,28.5500]]]}",field_boundary,boundary:sha256:plot-a
FRL-001,PLOT-B,East block,1.8,active,Uttar Pradesh,Gautam Buddha Nagar,Dadri,Nangla Chamru,123456,201314,2026-08-02T08:00:00+05:30,trace:PLOT-B,Pusa Basmati 1121,1121,Kharif 2026,28.5601,77.5701,,field_point,boundary:sha256:plot-b
'''


def test_farm_manifest_retains_only_minimal_non_person_records(ffl_db, owner, tmp_path):
    result = imports.register_farm_manifest(
        ffl_db, VALID_MANIFEST, owner.id, "approved-farm-manifest.csv", evidence_directory=str(tmp_path)
    )
    summary = imports.farm_manifest_summary(ffl_db, result["batch"].id)

    assert result["batch"].purpose == "farm_manifest"
    assert result["counters"] == {"total": 2, "valid": 2, "invalid": 0, "quarantined": 0, "published": 0}
    assert summary["counters"]["field_verified"] == 1
    assert summary["counters"]["village_context_only"] == 1
    assert summary["district_context_keys"] == ["in:uttar-pradesh:gautam-buddha-nagar"]
    manager_surface = dict(summary, batch=asdict(summary["batch"]))
    assert "FRL-001" not in json.dumps(manager_surface)
    assert "77.5555503" not in json.dumps(manager_surface)


def test_farm_manifest_does_not_create_canonical_farms_or_land(ffl_db, owner, tmp_path):
    result = imports.register_farm_manifest(ffl_db, VALID_MANIFEST, owner.id, evidence_directory=str(tmp_path))

    imports.review_farm_manifest(ffl_db, result["batch"].id, owner.id)
    published = imports.publish_farm_manifest(ffl_db, result["batch"].id, owner.id)

    assert published["batch"].status == "published"
    assert published["counters"]["published"] == 2
    assert ffl_db.execute("SELECT COUNT(*) FROM operating_units").fetchone()[0] == 0
    assert ffl_db.execute("SELECT COUNT(*) FROM land_parcels").fetchone()[0] == 0
    assert ffl_db.execute("SELECT COUNT(*) FROM operational_blocks").fetchone()[0] == 0


def test_published_farm_manifest_can_supply_private_verified_plot_features(ffl_db, owner, tmp_path):
    result = imports.register_farm_manifest(ffl_db, PLOT_MANIFEST, owner.id, evidence_directory=str(tmp_path))

    with pytest.raises(ValueError, match="published"):
        imports.farm_manifest_map_features(ffl_db, result["batch"].id)
    imports.review_farm_manifest(ffl_db, result["batch"].id, owner.id)
    imports.publish_farm_manifest(ffl_db, result["batch"].id, owner.id)
    feature_collection = imports.farm_manifest_map_features(ffl_db, result["batch"].id)

    assert feature_collection["type"] == "FeatureCollection"
    assert [feature["geometry"]["type"] for feature in feature_collection["features"]] == ["Polygon", "Point"]
    assert feature_collection["features"][0]["properties"]["feature_id"] == "PLOT-A"
    assert feature_collection["features"][0]["properties"]["area_hectares"] == 2.5
    assert feature_collection["features"][0]["properties"]["village_lgd_code"] == "123456"


def test_farm_manifest_rejects_pii_before_evidence_is_retained(ffl_db, owner, tmp_path):
    personal = VALID_MANIFEST.replace(b"source_farm_id,", b"Farmer Name,source_farm_id,")

    with pytest.raises(ValueError, match="personal or payment"):
        imports.register_farm_manifest(ffl_db, personal, owner.id, evidence_directory=str(tmp_path))

    assert ffl_db.execute("SELECT COUNT(*) FROM evidence_artifacts").fetchone()[0] == 0
    assert ffl_db.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0] == 0


def test_farm_manifest_requires_exact_schema_and_timezone_aware_source_time(ffl_db, owner, tmp_path):
    friendly_header = VALID_MANIFEST.replace(b"source_farm_id", b"Source Farm Id", 1)
    no_timezone = VALID_MANIFEST.replace(b"2026-08-02T08:00:00+05:30", b"2026-08-02", 1)

    with pytest.raises(ValueError, match="snake_case"):
        imports.register_farm_manifest(ffl_db, friendly_header, owner.id, evidence_directory=str(tmp_path))
    result = imports.register_farm_manifest(ffl_db, no_timezone, owner.id, evidence_directory=str(tmp_path))

    assert result["counters"]["invalid"] == 1


def test_farm_manifest_rejects_unexpected_purchase_columns_before_retention(ffl_db, owner, tmp_path):
    purchase_column = VALID_MANIFEST.replace(b"source_farm_id,", b"source_farm_id,rate_per_qtl,", 1)

    with pytest.raises(ValueError, match="unsupported columns"):
        imports.register_farm_manifest(ffl_db, purchase_column, owner.id, evidence_directory=str(tmp_path))

    assert ffl_db.execute("SELECT COUNT(*) FROM evidence_artifacts").fetchone()[0] == 0


def test_farm_manifest_quarantines_unverified_coordinates_and_blocks_publish(ffl_db, owner, tmp_path):
    unsafe = VALID_MANIFEST.replace(b"field_verified,boundary:sha256:example-001", b"village,")
    result = imports.register_farm_manifest(ffl_db, unsafe, owner.id, evidence_directory=str(tmp_path))

    assert result["counters"]["invalid"] == 1
    imports.review_farm_manifest(ffl_db, result["batch"].id, owner.id)
    with pytest.raises(ValueError, match="invalid or quarantined"):
        imports.publish_farm_manifest(ffl_db, result["batch"].id, owner.id)


def test_farm_manifest_requires_the_same_named_manager_to_review_and_publish(ffl_db, users, tmp_path):
    result = imports.register_farm_manifest(ffl_db, VALID_MANIFEST, users.manager.id, evidence_directory=str(tmp_path))

    imports.review_farm_manifest(ffl_db, result["batch"].id, users.manager.id)
    with pytest.raises(ValueError, match="named manager reviewer"):
        imports.publish_farm_manifest(ffl_db, result["batch"].id, users.lead.id)


def test_farm_manifest_api_is_manager_only_and_never_returns_rows(tmp_path, monkeypatch):
    monkeypatch.setenv("FFL_EVIDENCE_DIR", str(tmp_path / "evidence"))
    app = create_app(str(tmp_path / "manifest.db"), manager_api_token="manager-token")
    manager = repository.create_person(app.state.conn, "Pilot Manager", "farm_manager")
    app.state.manager_person_id = manager.id
    payload = {
        "content_base64": base64.b64encode(VALID_MANIFEST).decode("ascii"),
        "original_filename": "approved-farm-manifest.csv",
    }
    with TestClient(app) as client:
        denied = client.post("/api/v1/farm-manifests/csv", json=payload)
        created = client.post(
            "/api/v1/farm-manifests/csv", json=payload,
            headers={"x-ffl-manager-token": "manager-token"},
        )
        batch_id = created.json()["batch"]["id"]
        detail = client.get(
            "/api/v1/farm-manifests/" + batch_id,
            headers={"x-ffl-manager-token": "manager-token"},
        )
        map_denied = client.get("/api/v1/farm-manifests/" + batch_id + "/map-features")
        map_before_publish = client.get(
            "/api/v1/farm-manifests/" + batch_id + "/map-features",
            headers={"x-ffl-manager-token": "manager-token"},
        )
        review = client.post(
            "/api/v1/farm-manifests/" + batch_id + "/review",
            headers={"x-ffl-manager-token": "manager-token"},
        )
        publish = client.post(
            "/api/v1/farm-manifests/" + batch_id + "/publish",
            headers={"x-ffl-manager-token": "manager-token"},
        )
        map_after_publish = client.get(
            "/api/v1/farm-manifests/" + batch_id + "/map-features",
            headers={"x-ffl-manager-token": "manager-token"},
        )
        generic_detail = client.get("/api/v1/imports/" + batch_id)
        generic_create = client.post(
            "/api/v1/imports/csv",
            json={
                "content_base64": base64.b64encode(VALID_MANIFEST).decode("ascii"),
                "purpose": "farm_manifest",
                "owner_id": manager.id,
            },
        )

    assert denied.status_code == 403
    assert created.status_code == 201
    assert "rows" not in created.json()
    assert detail.status_code == 200
    assert "FRL-001" not in detail.text
    assert "77.5555503" not in detail.text
    assert map_denied.status_code == 403
    assert map_before_publish.status_code == 422
    assert review.status_code == 200
    assert publish.status_code == 200
    assert map_after_publish.json()["features"][0]["geometry"]["type"] == "Point"
    assert generic_detail.status_code == 404
    assert generic_create.status_code == 422
