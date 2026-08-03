import csv
import io

from fastapi.testclient import TestClient

from ffl.app import create_app
from ffl.communications import persistence as communications_persistence
from ffl.communications.persistence import create_communications_schema
from ffl.persistence import repository
from ffl.services import operating_export, operations, season, templates


def _setup(conn):
    manager = repository.create_person(conn, "Export Manager", "farm_manager")
    operator = repository.create_person(conn, "Export Operator", "field_operator")
    lead = repository.create_person(conn, "Export Lead", "operations_lead")
    unit = repository.create_operating_unit(conn, "Export Farm")
    block = repository.create_operational_block(conn, unit.id, "North Block", 3.5)
    growing_season = repository.create_season(conn, unit.id, "Kharif 2026", "2026-06-01", "2026-11-30")
    allocation = repository.create_crop_allocation(
        conn, unit.id, block.id, growing_season.id, "Rice", "Pusa 1121", 3.5
    )
    signal_template = templates.publish_signal_template(
        conn, "field observation", 1,
        [{"key": "condition", "type": "choice", "options": ["good", "watch"], "required": True}],
        manager.id,
    )
    evidence = repository.create_evidence_artifact(
        conn, "a" * 64, "image/jpeg", "evidence/field/photo.jpg", created_by_person_id=operator.id
    )
    season.record_field_signal(
        conn, allocation.id, signal_template.id, signal_template.version,
        "2026-08-02T08:00:00Z", operator.id, {"condition": "watch"}, evidence_artifact_id=evidence.id,
    )
    operations.create_work_item(
        conn, allocation.id, "Inspect irrigation", operator.id, "2026-08-03T09:00:00Z", initial_status="planned"
    )
    operations.report_exception(
        conn, allocation.id, "Check water inlet", "high", manager.id, lead.id,
        "2026-08-02T07:00:00Z", "export-exception-1",
    )
    season.schedule_crop_stage_checkpoint(
        conn, allocation.id, "Tillering check", "2026-08-04T09:00:00Z", {"photo": True}
    )
    season.record_harvest(
        conn, allocation.id, "2026-10-10T08:00:00Z", 17.5, "quintal", "weighbridge", {"moisture_pct": 12.8}
    )
    return manager, operator, unit


def test_operating_export_is_canonical_deterministic_and_excludes_communications(ffl_db):
    manager, operator, unit = _setup(ffl_db)
    create_communications_schema(ffl_db)
    endpoint = communications_persistence.create_endpoint(ffl_db, operator.id, "loopmessage", "+15550000001", "hi-IN")
    communications_persistence.record_event_with_receipt(
        ffl_db, "loopmessage", "export-webhook-1", "provider-message-1", "message_inbound", "+15550000001",
        endpoint["id"], {"message_type": "text"}, "private-receipt-never-exported",
    )

    output = operating_export.operating_ledger_csv(ffl_db, unit.id)
    rows = list(csv.DictReader(io.StringIO(output)))

    assert [row["record_type"] for row in rows] == [
        "work_item", "exception_record", "field_signal", "crop_stage_checkpoint", "harvest_record",
    ]
    assert {row["field_name"] for row in rows} == {"North Block"}
    assert {row["crop_name"] for row in rows} == {"Rice"}
    assert any(row["structured_values"] == '{"condition":"watch"}' for row in rows)
    assert "15550000001" not in output
    assert "private-receipt-never-exported" not in output
    assert "communication_event" not in output


def test_operating_export_is_manager_only_and_spreadsheet_safe(tmp_path):
    app = create_app(str(tmp_path / "export.db"), manager_api_token="manager-token")
    with TestClient(app) as client:
        manager, operator, unit = _setup(app.state.conn)
        app.state.manager_person_id = manager.id
        operations.create_work_item(
            app.state.conn, app.state.conn.execute("SELECT id FROM crop_allocations").fetchone()["id"],
            "=unsafe spreadsheet value", operator.id, "2026-08-05T09:00:00Z", initial_status="planned",
        )

        denied = client.get("/api/v1/operating-units/{0}/operating-ledger.csv".format(unit.id))
        allowed = client.get(
            "/api/v1/operating-units/{0}/operating-ledger.csv".format(unit.id),
            headers={"X-FFL-Manager-Token": "manager-token"},
        )

        assert denied.status_code == 403
        assert allowed.status_code == 200
        assert allowed.headers["content-type"].startswith("text/csv")
        assert "attachment; filename=\"agro-ceo-operating-ledger.csv\"" == allowed.headers["content-disposition"]
        assert "'=unsafe spreadsheet value" in allowed.text
