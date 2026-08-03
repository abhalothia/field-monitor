from datetime import datetime, timezone
import hashlib

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ffl.api.portfolio_routes import router as portfolio_router
from ffl.persistence import repository
from ffl.services import field_information_requests, imports, operations, portfolio, season, sources, templates, trials


NOW = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)


def _published_template(ffl_db, owner):
    return templates.publish_signal_template(
        ffl_db,
        "portfolio-stage-check",
        1,
        [{"key": "stage", "type": "text", "required": True}],
        owner.id,
    )


def _source(ffl_db, owner):
    return sources.register_source(
        ffl_db,
        source_key="portfolio-weather",
        display_name="Portfolio weather context",
        source_type="not-installed",
        purpose="regional weather context",
        authority_level="official",
        owner_id=owner.id,
        permitted_data_classes=["forecast"],
        schema_version="v1",
        mapping_version="v1",
        default_coverage={"district": "pilot-district"},
        freshness_target_hours=6,
        enabled=True,
    )


def _evidence(ffl_db, owner, content=b"portfolio evidence"):
    return repository.create_evidence_artifact(
        ffl_db,
        hashlib.sha256(content).hexdigest(),
        "text/plain",
        "private://evidence/portfolio",
        created_by_person_id=owner.id,
    )


def _trial_protocol(operating_unit_id, season_id):
    return {
        "name": "Portfolio trial",
        "hypothesis": "A documented approach should be assessed before scaling.",
        "protocol_version": "v1",
        "decision_question": "Whether to continue the documented approach.",
        "treatment": {"interval_hours": 48},
        "comparator": {"interval_hours": 36},
        "eligibility_rule": {
            "operating_unit_ids": [operating_unit_id],
            "season_ids": [season_id],
            "crop_names": ["Rice"],
            "allocation_statuses": ["active"],
        },
        "measurements": [{"outcome": "grade_a_output", "method": "weighbridge", "cadence": "harvest"}],
        "guardrails": [{"threshold": "wilting", "action": "pause"}],
    }


def test_portfolio_aggregates_canonical_operations_without_evidence_content(ffl_db, crop_allocation, users):
    template = _published_template(ffl_db, users.lead)
    overdue = operations.create_work_item(
        ffl_db, crop_allocation.id, "Inspect irrigation", users.manager.id,
        "2026-07-30T09:00:00+00:00", initial_status="planned",
    )
    rejected = operations.create_work_item(
        ffl_db, crop_allocation.id, "Re-check moisture", users.operator.id,
        "2026-08-02T09:00:00+00:00", initial_status="rejected",
    )
    reported = operations.report_exception(
        ffl_db, crop_allocation.id, "Water pooling", "critical", users.manager.id, users.lead.id,
        "2026-08-01T06:00:00+00:00", "portfolio-exception",
    )
    upcoming = season.schedule_crop_stage_checkpoint(
        ffl_db, crop_allocation.id, "Tillering", "2026-08-04", {"photo": "required"}, template.id, 1
    )
    signal = season.record_field_signal(
        ffl_db, crop_allocation.id, template.id, 1, "2026-08-01T08:00:00+00:00", users.operator.id,
        {"stage": "tillering"}, status="submitted",
    )
    source = _source(ffl_db, users.lead)
    sources.refresh_source(ffl_db, source.source_key, now=NOW)

    batch = imports.register_csv_import(
        ffl_db,
        "allocation_id,observed_at,observation\n{0},2026-08-01T08:00:00+00:00,standing-water\n".format(
            crop_allocation.id
        ).encode("utf-8"),
        "field_visit",
        users.manager.id,
    )["batch"]
    allocation_row = ffl_db.execute(
        "SELECT operating_unit_id, season_id FROM crop_allocations WHERE id = ?", (crop_allocation.id,)
    ).fetchone()
    protocol = _trial_protocol(allocation_row["operating_unit_id"], allocation_row["season_id"])
    trial = repository.create_trial(
        ffl_db,
        protocol["name"],
        protocol["hypothesis"],
        users.lead.id,
        protocol["protocol_version"],
        protocol["decision_question"],
        protocol["treatment"],
        protocol["comparator"],
        protocol["eligibility_rule"],
        protocol["measurements"],
        protocol["guardrails"],
        status="paused",
        status_reason="guardrail needs review",
    )
    playbook = trials.create_playbook(
        ffl_db,
        "Portfolio playbook",
        1,
        users.lead.id,
        {
            "summary": "Inspect before broad use.",
            "work_instructions": ["Inspect"],
            "evidence_requirements": ["Field observation"],
        },
    )
    trials.transition_playbook(ffl_db, playbook.id, "review", users.lead.id, "ready for review")

    result = portfolio.portfolio_snapshot(ffl_db, as_of=NOW)

    assert result["scope"]["active_farms"]["count"] == 1
    assert result["scope"]["active_allocations"]["items"][0]["id"] == crop_allocation.id
    assert result["work"]["overdue"]["total_count"] == 1
    assert result["work"]["overdue"]["items"][0]["id"] == overdue.id
    assert result["work"]["rejected_rework"]["items"][0]["id"] == rejected.id
    assert result["exceptions"]["by_severity"] == {"critical": 1}
    assert result["exceptions"]["open"]["items"][0]["id"] == reported.id
    assert result["crop_stage_checkpoints"]["upcoming"]["items"][0]["id"] == upcoming.id
    assert result["imports"]["review_required"]["items"][0]["id"] == batch.id
    assert result["sources"]["attention"]["items"][0]["source_key"] == source.source_key
    assert result["sources"]["attention"]["items"][0]["health"] == "unavailable"
    assert result["field_signals"]["open"]["items"][0]["id"] == signal.id
    assert result["field_signals"]["open"]["items"][0]["evidence_attached"] is False
    assert result["learning"]["trials"]["by_status"] == {"paused": 1}
    assert result["learning"]["playbooks"]["by_status"] == {"review": 1}
    assert result["risk_action_ledger"]["total_count"] >= 8
    rendered = repr(result)
    assert "private://evidence/portfolio" not in rendered
    assert "standing-water" not in rendered
    assert "portfolio-stage-check" not in rendered


def test_portfolio_uses_explicit_not_configured_context_for_empty_or_missing_optional_records(ffl_db, owner):
    result = portfolio.portfolio_snapshot(ffl_db, as_of=NOW)

    assert result["scope"]["active_farms"] == {"count": 0, "items": []}
    assert result["sources"]["availability"] == "not_configured"
    assert result["imports"]["batches_by_status"] == {}
    assert result["field_signals"]["open"]["total_count"] == 0

    _source(ffl_db, owner)
    ffl_db.execute("DROP TABLE regional_signals")
    ffl_db.commit()
    resilient = portfolio.portfolio_snapshot(ffl_db, as_of=NOW)
    assert resilient["sources"]["attention"]["items"][0]["health"] == "unavailable"


def test_portfolio_surfaces_request_state_without_message_copy_or_false_completion(ffl_db, crop_allocation, users):
    work = operations.create_work_item(
        ffl_db, crop_allocation.id, "Revisit coverage gap", users.manager.id,
        "2026-08-02T09:00:00+00:00", initial_status="in_progress",
    )
    field_request = field_information_requests.create_information_request(
        ffl_db,
        crop_allocation.id,
        users.operator.id,
        "evidence_photo",
        True,
        "2026-08-01T09:00:00+00:00",
        "Please photograph the north boundary.",
        "कृपया उत्तर सीमा की तस्वीर भेजें।",
        "portfolio-field-ask:001",
        work_item_id=work.id,
        initiated_by_person_id=users.manager.id,
    )
    ready = field_information_requests.ready_information_request(
        ffl_db, field_request.id, actor_person_id=users.manager.id
    )
    field_information_requests.mark_information_request_dispatched(
        ffl_db, ready.id, actor_system_key="system:future-delivery"
    )

    result = portfolio.portfolio_snapshot(ffl_db, as_of=NOW)

    assert result["field_information_requests"]["availability"] == "available"
    assert result["field_information_requests"]["open"]["items"] == [{
        "id": field_request.id,
        "allocation_id": crop_allocation.id,
        "target_person_id": users.operator.id,
        "request_kind": "evidence_photo",
        "evidence_required": True,
        "due_at": "2026-08-01T09:00:00+00:00",
        "status": "dispatched",
    }]
    ledger = next(item for item in result["risk_action_ledger"]["items"] if item["entity"]["id"] == field_request.id)
    assert ledger["action"] == "review_field_response_or_recover"
    assert ledger["proof_required"] is True
    assert ledger["owner_id"] == users.operator.id
    assert repository.get_work_item(ffl_db, work.id).status == "in_progress"
    rendered = repr(result)
    assert "photograph the north boundary" not in rendered
    assert "उत्तर सीमा" not in rendered


def test_unmounted_portfolio_route_validates_as_of_and_keeps_service_read_only(ffl_db, crop_allocation, users):
    work = operations.create_work_item(
        ffl_db, crop_allocation.id, "Future work", users.manager.id,
        "2026-08-02T09:00:00+00:00", initial_status="planned",
    )
    app = FastAPI()
    app.state.conn = ffl_db
    app.include_router(portfolio_router)
    client = TestClient(app)

    before = ffl_db.execute("SELECT status FROM work_items WHERE id = ?", (work.id,)).fetchone()["status"]
    response = client.get("/api/v1/portfolio?as_of=2026-08-01T12:00:00Z")
    invalid = client.get("/api/v1/portfolio?as_of=not-a-date")
    naive_timestamp = client.get("/api/v1/portfolio?as_of=2026-08-01T12:00:00")
    date_only = client.get("/api/v1/portfolio?as_of=2026-08-01")
    after = ffl_db.execute("SELECT status FROM work_items WHERE id = ?", (work.id,)).fetchone()["status"]

    assert response.status_code == 200
    assert response.json()["as_of"] == "2026-08-01T12:00:00+00:00"
    assert invalid.status_code == 422
    assert naive_timestamp.status_code == 422
    assert naive_timestamp.json()["detail"] == "as_of timestamps must include a timezone"
    assert date_only.status_code == 200
    assert date_only.json()["as_of"] == "2026-08-01T00:00:00+00:00"
    assert before == after == "planned"
