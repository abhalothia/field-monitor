from datetime import datetime, timezone
import json
import sqlite3
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from ffl.api.season_routes import router as season_router
from ffl.persistence import repository
from ffl.persistence.schema import create_schema
from ffl.services import season


def _published_template(conn, owner):
    return repository.create_signal_template(
        conn,
        "Rice stage observation",
        1,
        "published",
        json.dumps([
            {"key": "stage", "type": "choice", "options": ["tillering", "flowering"], "required": True},
            {"key": "condition", "type": "text", "required": False},
        ]),
        owner.id,
        "2026-08-01T00:00:00+00:00",
    )


@pytest.fixture
def season_api():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    create_schema(conn)
    unit = repository.create_operating_unit(conn, "API Test Farm")
    block = repository.create_operational_block(conn, unit.id, "API Block", 2.0)
    season_record = repository.create_season(conn, unit.id, "Kharif 2026", "2026-06-01", "2026-11-30")
    allocation = repository.create_crop_allocation(
        conn, unit.id, block.id, season_record.id, "Rice", None, 2.0
    )
    owner = repository.create_person(conn, "Agronomist", "agronomist")
    operator = repository.create_person(conn, "Operator", "field_operator")
    app = FastAPI()
    app.state.conn = conn
    app.include_router(season_router)
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, conn=conn, allocation=allocation, owner=owner, operator=operator)
    conn.close()


def test_signal_rejects_template_version_and_accepts_published_template(
    ffl_db, crop_allocation, users, owner
):
    template = _published_template(ffl_db, owner)

    with pytest.raises(ValueError, match="ID and version do not match"):
        season.record_field_signal(
            ffl_db, crop_allocation.id, template.id, 2, "2026-08-04T09:00:00+00:00",
            users.operator.id, {"stage": "tillering"},
        )

    signal = season.record_field_signal(
        ffl_db, crop_allocation.id, template.id, 1, "2026-08-04T09:00:00+00:00",
        users.operator.id, {"stage": "tillering", "condition": "observed"},
    )

    assert signal.template_id == template.id
    assert signal.values == {"stage": "tillering", "condition": "observed"}


def test_calendar_orders_context_and_marks_stale_overdue_and_window_items(
    ffl_db, crop_allocation, users, owner
):
    template = _published_template(ffl_db, owner)
    stale = repository.create_crop_stage_checkpoint(
        ffl_db, crop_allocation.id, "superseded stage", "2026-08-01", {}, template.id, 1,
        status="superseded",
    )
    overdue = season.schedule_crop_stage_checkpoint(
        ffl_db, crop_allocation.id, "tillering", "2026-08-04", {}, template.id, 1,
    )
    within_window = season.schedule_crop_stage_checkpoint(
        ffl_db, crop_allocation.id, "flowering", "2026-08-12", {}, template.id, 1,
    )
    work = repository.create_work_item(
        ffl_db, crop_allocation.id, "Capture field evidence", users.manager.id,
        "2026-08-12T09:00:00+00:00", initial_status="planned",
    )
    earlier_work = repository.create_work_item(
        ffl_db, crop_allocation.id, "Inspect irrigation", users.manager.id,
        "2026-08-10T09:00:00+00:00", initial_status="planned",
    )

    calendar = season.allocation_calendar(
        ffl_db, crop_allocation.id, as_of=datetime(2026, 8, 5, tzinfo=timezone.utc)
    )

    assert [item["id"] for item in calendar["checkpoints"]] == [stale.id, overdue.id, within_window.id]
    assert [item["timing_state"] for item in calendar["checkpoints"]] == [
        "stale", "overdue", "within_window",
    ]
    assert calendar["next_checkpoint"]["id"] == overdue.id
    assert [item["id"] for item in calendar["work_items"]] == [earlier_work.id, work.id]
    assert [item["timing_state"] for item in calendar["work_items"]] == ["within_window", "within_window"]


def test_harvest_correction_preserves_original_and_accounts_for_actor_and_reason(
    ffl_db, crop_allocation, users
):
    original = season.record_harvest(
        ffl_db, crop_allocation.id, "2026-11-04", 1000, "kg", "weighbridge", {"grade": "A"},
        status="final",
    )
    correction = season.record_harvest(
        ffl_db, crop_allocation.id, "2026-11-04", 980, "kg", "weighbridge",
        {"grade": "A", "ticket": "WB-22"}, correction_of_id=original.id,
        corrected_by_person_id=users.manager.id, correction_reason="calibrated scale ticket received",
    )

    assert correction.id != original.id
    assert correction.correction_of_id == original.id
    assert correction.corrected_by_person_id == users.manager.id
    assert correction.correction_reason == "calibrated scale ticket received"
    assert repository.get_harvest_record(ffl_db, original.id).quantity == 1000


def test_season_review_retains_evidence_linked_learning_content(
    ffl_db, crop_allocation, users, owner
):
    template = _published_template(ffl_db, owner)
    signal = season.record_field_signal(
        ffl_db, crop_allocation.id, template.id, 1, "2026-08-04T09:00:00+00:00",
        users.operator.id, {"stage": "tillering"},
    )
    learning = [{
        "statement": "Weekly observation record was usable at tillering",
        "evidence_links": [{"entity_type": "field_signal", "entity_id": signal.id}],
    }]

    review = season.record_season_review(
        ffl_db, crop_allocation.id, users.manager.id, learning, learning, learning, learning,
        status="reviewed", reviewed_at="2026-12-01T12:00:00+00:00",
    )

    assert review.status == "reviewed"
    assert review.reviewed_at == "2026-12-01T12:00:00+00:00"
    assert review.confirmed_practices == learning
    assert review.proposed_playbook_changes == learning


def test_season_routes_return_serializable_records_and_422_validation_errors(season_api):
    published = _published_template(season_api.conn, season_api.owner)
    draft = repository.create_signal_template(
        season_api.conn, "Draft only", 1, "draft", "[]", season_api.owner.id, "2026-08-01T00:00:00+00:00"
    )

    calendar = season_api.client.get(
        "/api/v1/allocations/{}/calendar".format(season_api.allocation.id)
    )
    rejected_signal = season_api.client.post(
        "/api/v1/allocations/{}/signals".format(season_api.allocation.id),
        json={
            "template_id": draft.id,
            "template_version": 1,
            "observed_at": "2026-08-04T09:00:00+00:00",
            "actor_id": season_api.operator.id,
            "values": {},
        },
    )
    accepted_signal = season_api.client.post(
        "/api/v1/allocations/{}/signals".format(season_api.allocation.id),
        json={
            "template_id": published.id,
            "template_version": 1,
            "observed_at": "2026-08-04T09:00:00+00:00",
            "actor_id": season_api.operator.id,
            "values": {"stage": "tillering"},
        },
    )
    original_harvest = season_api.client.post(
        "/api/v1/allocations/{}/harvest-records".format(season_api.allocation.id),
        json={
            "harvest_starts_on": "2026-11-04",
            "quantity": 1000,
            "canonical_unit": "kg",
            "measurement_method": "weighbridge",
            "quality_metrics": {"grade": "A"},
            "status": "final",
        },
    )
    correction = season_api.client.post(
        "/api/v1/allocations/{}/harvest-records".format(season_api.allocation.id),
        json={
            "harvest_starts_on": "2026-11-04",
            "quantity": 980,
            "canonical_unit": "kg",
            "measurement_method": "weighbridge",
            "quality_metrics": {"grade": "A", "ticket": "WB-22"},
            "correction_of_id": original_harvest.json()["id"],
            "corrected_by_person_id": season_api.owner.id,
            "correction_reason": "calibrated scale ticket received",
        },
    )
    learning = [{
        "statement": "Observed stage record is retained for review",
        "evidence_links": [{"entity_type": "field_signal", "entity_id": accepted_signal.json()["id"]}],
    }]
    review = season_api.client.post(
        "/api/v1/allocations/{}/season-reviews".format(season_api.allocation.id),
        json={
            "owner_id": season_api.owner.id,
            "confirmed_practices": learning,
            "invalidated_assumptions": learning,
            "unresolved_questions": learning,
            "proposed_playbook_changes": learning,
        },
    )
    rejected_correction = season_api.client.post(
        "/api/v1/allocations/{}/harvest-records".format(season_api.allocation.id),
        json={
            "harvest_starts_on": "2026-11-04",
            "quantity": 980,
            "canonical_unit": "kg",
            "measurement_method": "weighbridge",
            "correction_of_id": "missing-record",
        },
    )

    assert calendar.status_code == 200
    assert calendar.json()["allocation"]["id"] == season_api.allocation.id
    assert rejected_signal.status_code == 422
    assert rejected_signal.json()["detail"] == "signal template must be published"
    assert accepted_signal.status_code == 201
    assert accepted_signal.json()["values"] == {"stage": "tillering"}
    assert original_harvest.status_code == 201
    assert correction.status_code == 201
    assert correction.json()["correction_of_id"] == original_harvest.json()["id"]
    assert review.status_code == 201
    assert review.json()["confirmed_practices"] == learning
    assert rejected_correction.status_code == 422
    assert rejected_correction.json()["detail"] == "corrected_by_person_id is required"
