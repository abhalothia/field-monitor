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
from ffl.services import operations, season


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


def test_calendar_normalizes_checkpoint_offsets_before_ordering_and_evaluation(
    ffl_db, crop_allocation, owner
):
    template = _published_template(ffl_db, owner)
    later_instant = season.schedule_crop_stage_checkpoint(
        ffl_db, crop_allocation.id, "UTC later", "2026-08-04T04:00:00+00:00", {}, template.id, 1,
    )
    earlier_instant = season.schedule_crop_stage_checkpoint(
        ffl_db, crop_allocation.id, "Offset earlier", "2026-08-04T08:00:00+05:30", {}, template.id, 1,
    )

    calendar = season.allocation_calendar(
        ffl_db, crop_allocation.id, as_of=datetime(2026, 8, 4, 3, tzinfo=timezone.utc)
    )

    assert [item["id"] for item in calendar["checkpoints"]] == [earlier_instant.id, later_instant.id]
    assert [item["timing_state"] for item in calendar["checkpoints"]] == ["overdue", "within_window"]


def test_calendar_treats_cancelled_work_as_distinct_terminal_state(ffl_db, crop_allocation, users):
    cancelled = repository.create_work_item(
        ffl_db, crop_allocation.id, "Cancelled field walk", users.manager.id,
        "2026-08-01T09:00:00+00:00", initial_status="cancelled",
    )

    calendar = season.allocation_calendar(
        ffl_db, crop_allocation.id, as_of=datetime(2026, 8, 5, tzinfo=timezone.utc)
    )

    assert calendar["work_items"][0]["id"] == cancelled.id
    assert calendar["work_items"][0]["timing_state"] == "cancelled"


def test_calendar_surfaces_rejected_work_for_rework(ffl_db, crop_allocation, users):
    rejected = repository.create_work_item(
        ffl_db, crop_allocation.id, "Rework field evidence", users.manager.id,
        "2026-08-01T09:00:00+00:00", initial_status="submitted",
    )
    operations.transition_work_item(
        ffl_db, rejected.id, "rejected", users.manager.id, "Photo does not identify the block"
    )

    calendar = season.allocation_calendar(
        ffl_db, crop_allocation.id, as_of=datetime(2026, 8, 5, tzinfo=timezone.utc)
    )

    assert calendar["work_items"][0]["status"] == "rejected"
    assert calendar["work_items"][0]["timing_state"] == "overdue"


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


def test_harvest_correction_rejects_a_nonfinal_predecessor(ffl_db, crop_allocation, users):
    preliminary = season.record_harvest(
        ffl_db, crop_allocation.id, "2026-11-04", 1000, "kg", "weighbridge", {}, status="preliminary",
    )

    with pytest.raises(ValueError, match="require a final predecessor"):
        season.record_harvest(
            ffl_db, crop_allocation.id, "2026-11-04", 980, "kg", "weighbridge", {},
            correction_of_id=preliminary.id, corrected_by_person_id=users.manager.id,
            correction_reason="calibrated scale ticket received",
        )


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


@pytest.mark.parametrize(
    "empty_category",
    ["confirmed_practices", "invalidated_assumptions", "unresolved_questions", "proposed_playbook_changes"],
)
def test_season_review_requires_content_in_every_learning_category(
    ffl_db, crop_allocation, users, owner, empty_category
):
    template = _published_template(ffl_db, owner)
    signal = season.record_field_signal(
        ffl_db, crop_allocation.id, template.id, 1, "2026-08-04T09:00:00+00:00",
        users.operator.id, {"stage": "tillering"},
    )
    learning = [{
        "statement": "Observed field evidence is retained for the season review",
        "evidence_links": [{"entity_type": "field_signal", "entity_id": signal.id}],
    }]

    categories = {
        "confirmed_practices": learning,
        "invalidated_assumptions": learning,
        "unresolved_questions": learning,
        "proposed_playbook_changes": learning,
    }
    categories[empty_category] = []

    with pytest.raises(ValueError, match="{0} must contain".format(empty_category)):
        season.record_season_review(
            ffl_db, crop_allocation.id, users.manager.id,
            categories["confirmed_practices"], categories["invalidated_assumptions"],
            categories["unresolved_questions"], categories["proposed_playbook_changes"],
        )


def test_season_review_rejects_evidence_only_learning_entries(ffl_db, crop_allocation, users, owner):
    template = _published_template(ffl_db, owner)
    signal = season.record_field_signal(
        ffl_db, crop_allocation.id, template.id, 1, "2026-08-04T09:00:00+00:00",
        users.operator.id, {"stage": "tillering"},
    )
    evidence_only = [{"evidence_links": [{"entity_type": "field_signal", "entity_id": signal.id}]}]

    with pytest.raises(ValueError, match="confirmed_practices entries require a non-empty statement"):
        season.record_season_review(
            ffl_db, crop_allocation.id, users.manager.id,
            evidence_only, evidence_only, evidence_only, evidence_only,
        )


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


def test_season_routes_reject_nonfinal_and_contradictory_harvest_corrections(season_api):
    preliminary = season_api.client.post(
        "/api/v1/allocations/{}/harvest-records".format(season_api.allocation.id),
        json={
            "harvest_starts_on": "2026-11-04",
            "quantity": 1000,
            "canonical_unit": "kg",
            "measurement_method": "weighbridge",
        },
    )
    nonfinal_correction = season_api.client.post(
        "/api/v1/allocations/{}/harvest-records".format(season_api.allocation.id),
        json={
            "harvest_starts_on": "2026-11-04",
            "quantity": 980,
            "canonical_unit": "kg",
            "measurement_method": "weighbridge",
            "correction_of_id": preliminary.json()["id"],
            "corrected_by_person_id": season_api.owner.id,
            "correction_reason": "calibrated scale ticket received",
            "status": "corrected",
        },
    )
    final = season_api.client.post(
        "/api/v1/allocations/{}/harvest-records".format(season_api.allocation.id),
        json={
            "harvest_starts_on": "2026-11-04",
            "quantity": 1000,
            "canonical_unit": "kg",
            "measurement_method": "weighbridge",
            "status": "final",
        },
    )
    contradictory_status = season_api.client.post(
        "/api/v1/allocations/{}/harvest-records".format(season_api.allocation.id),
        json={
            "harvest_starts_on": "2026-11-04",
            "quantity": 980,
            "canonical_unit": "kg",
            "measurement_method": "weighbridge",
            "correction_of_id": final.json()["id"],
            "corrected_by_person_id": season_api.owner.id,
            "correction_reason": "calibrated scale ticket received",
            "status": "preliminary",
        },
    )

    assert preliminary.status_code == 201
    assert nonfinal_correction.status_code == 422
    assert nonfinal_correction.json()["detail"] == "harvest corrections require a final predecessor record"
    assert final.status_code == 201
    assert contradictory_status.status_code == 422
    assert contradictory_status.json()["detail"] == "harvest correction status must be corrected"


def test_season_review_route_rejects_evidence_only_content(season_api):
    template = _published_template(season_api.conn, season_api.owner)
    signal = season_api.client.post(
        "/api/v1/allocations/{}/signals".format(season_api.allocation.id),
        json={
            "template_id": template.id,
            "template_version": 1,
            "observed_at": "2026-08-04T09:00:00+00:00",
            "actor_id": season_api.operator.id,
            "values": {"stage": "tillering"},
        },
    )
    evidence_only = [{
        "evidence_links": [{"entity_type": "field_signal", "entity_id": signal.json()["id"]}],
    }]
    response = season_api.client.post(
        "/api/v1/allocations/{}/season-reviews".format(season_api.allocation.id),
        json={
            "owner_id": season_api.owner.id,
            "confirmed_practices": evidence_only,
            "invalidated_assumptions": evidence_only,
            "unresolved_questions": evidence_only,
            "proposed_playbook_changes": evidence_only,
        },
    )

    assert signal.status_code == 201
    assert response.status_code == 422
    assert response.json()["detail"] == "confirmed_practices entries require a non-empty statement"
