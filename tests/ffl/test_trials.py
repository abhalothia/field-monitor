import hashlib
import sqlite3
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ffl.api.trial_routes import router as trial_router
from ffl.persistence import repository
from ffl.persistence.schema import create_schema
from ffl.services import trials


def _protocol():
    return {
        "summary": "Check a documented irrigation interval before broader use.",
        "work_instructions": ["Measure irrigation duration at each scheduled visit."],
        "evidence_requirements": ["Photo of meter reading and signed field observation."],
    }


def _trial_payload(owner_id):
    return {
        "name": "Irrigation interval pilot",
        "hypothesis": "A measured interval may reduce water use without reducing grade-A output.",
        "owner_id": owner_id,
        "protocol_version": "v1",
        "decision_question": "Whether to retain the interval for the next pilot season.",
        "treatment": {"interval_hours": 48},
        "comparator": {"interval_hours": 36},
        "eligibility_rule": {"crop": "Rice", "same_season": True},
        "measurements": [{"outcome": "grade_a_output", "method": "weighbridge", "cadence": "harvest"}],
        "guardrails": [{"threshold": "wilting observed", "action": "pause and inspect"}],
    }


def _trial_context(ffl_db, users):
    unit = repository.create_operating_unit(ffl_db, "Trials Farm")
    season = repository.create_season(ffl_db, unit.id, "Kharif 2026", "2026-06-01", "2026-11-30")
    treatment_block = repository.create_operational_block(ffl_db, unit.id, "Treatment", 2.0)
    comparator_block = repository.create_operational_block(ffl_db, unit.id, "Comparator", 2.0)
    unrelated_block = repository.create_operational_block(ffl_db, unit.id, "Unrelated", 2.0)
    treatment = repository.create_crop_allocation(
        ffl_db, unit.id, treatment_block.id, season.id, "Rice", None, 2.0
    )
    comparator = repository.create_crop_allocation(
        ffl_db, unit.id, comparator_block.id, season.id, "Rice", None, 2.0
    )
    unrelated = repository.create_crop_allocation(
        ffl_db, unit.id, unrelated_block.id, season.id, "Rice", None, 2.0
    )
    trial = trials.create_trial(ffl_db, **_trial_payload(users.lead.id))
    return SimpleNamespace(trial=trial, treatment=treatment, comparator=comparator, unrelated=unrelated)


def _activate(ffl_db, users, context):
    treatment = trials.add_trial_allocation(
        ffl_db, context.trial.id, context.treatment.id, "treatment", users.lead.id
    )
    comparator = trials.add_trial_allocation(
        ffl_db, context.trial.id, context.comparator.id, "comparator", users.lead.id
    )
    trials.transition_trial_allocation(
        ffl_db, context.trial.id, treatment.id, "enrolled", users.lead.id, "eligible and consented"
    )
    trials.transition_trial_allocation(
        ffl_db, context.trial.id, comparator.id, "enrolled", users.lead.id, "eligible and consented"
    )
    return trials.transition_trial(ffl_db, context.trial.id, "active", users.lead.id, "protocol ready")


def _evidence(ffl_db, owner_id):
    content_hash = hashlib.sha256(b"trial conclusion evidence").hexdigest()
    return repository.create_evidence_artifact(
        ffl_db, content_hash, "text/plain", "private://trial-evidence", created_by_person_id=owner_id
    )


def _causal_result(context):
    return {
        "summary": "The observed output difference is conditional on the documented comparison.",
        "claim_type": "causal",
        "comparison_context": {
            "control_strategy": "Pre-specified matched operational blocks with same measurement protocol.",
            "treatment_allocation_ids": [context.treatment.id],
            "comparator_allocation_ids": [context.comparator.id],
        },
    }


def test_trial_requires_complete_protocol_and_both_enrolled_arms_before_activation(ffl_db, users):
    payload = _trial_payload(users.lead.id)
    payload["measurements"] = [{"outcome": "yield"}]
    with pytest.raises(ValueError, match="measurements.method"):
        trials.create_trial(ffl_db, **payload)

    context = _trial_context(ffl_db, users)
    treatment = trials.add_trial_allocation(
        ffl_db, context.trial.id, context.treatment.id, "treatment", users.lead.id
    )
    trials.transition_trial_allocation(
        ffl_db, context.trial.id, treatment.id, "enrolled", users.lead.id, "eligible"
    )
    with pytest.raises(ValueError, match="treatment and comparator"):
        trials.transition_trial(ffl_db, context.trial.id, "active", users.lead.id, "start")


def test_trial_state_and_allocation_transitions_are_governed_and_auditable(ffl_db, users):
    context = _trial_context(ffl_db, users)
    active = _activate(ffl_db, users, context)
    paused = trials.transition_trial(ffl_db, active.id, "paused", users.manager.id, "water stress threshold")
    stopped = trials.transition_trial(ffl_db, paused.id, "stopped", users.manager.id, "guardrail requires stop")

    assert active.status == "active"
    assert paused.status == "paused"
    assert stopped.status == "stopped"
    assert stopped.ends_on is not None
    detail = trials.trial_detail(ffl_db, stopped.id)
    assert [event["to_status"] for event in detail["audit_events"]] == ["active", "paused", "stopped"]
    assert detail["allocations"][0]["status"] == "enrolled"

    with pytest.raises(ValueError, match="invalid trial transition"):
        trials.transition_trial(ffl_db, stopped.id, "active", users.lead.id, "retry")


def test_confounder_cannot_be_attached_to_nonparticipating_allocation(ffl_db, users):
    context = _trial_context(ffl_db, users)
    _activate(ffl_db, users, context)

    with pytest.raises(ValueError, match="must participate"):
        trials.record_trial_confounder(
            ffl_db, context.trial.id, "weather", "Unexpected rain", "2026-08-12T08:00:00+00:00",
            users.lead.id, allocation_id=context.unrelated.id,
        )

    confounder = trials.record_trial_confounder(
        ffl_db, context.trial.id, "weather", "Unexpected rain", "2026-08-12T08:00:00+00:00",
        users.lead.id, allocation_id=context.treatment.id,
    )
    assert confounder.allocation_id == context.treatment.id


def test_conclusions_require_evidence_limitations_and_comparison_context_for_causal_claims(ffl_db, users):
    context = _trial_context(ffl_db, users)
    _activate(ffl_db, users, context)
    trials.transition_trial(ffl_db, context.trial.id, "completed", users.lead.id, "harvest records complete")
    artifact = _evidence(ffl_db, users.lead.id)

    with pytest.raises(ValueError, match="causal conclusions require comparison_context"):
        trials.create_trial_conclusion(
            ffl_db, context.trial.id, users.lead.id,
            {"summary": "It worked", "claim_type": "causal"}, "medium", ["Single season"], artifact.id,
        )
    with pytest.raises(ValueError, match="limitations must be a non-empty list"):
        trials.create_trial_conclusion(
            ffl_db, context.trial.id, users.lead.id, _causal_result(context), "medium", [], artifact.id,
        )

    conclusion = trials.create_trial_conclusion(
        ffl_db, context.trial.id, users.lead.id, _causal_result(context), "medium",
        [{"statement": "One season and limited blocks; repeat before scale."}], artifact.id,
    )
    reviewed = trials.transition_trial_conclusion(
        ffl_db, context.trial.id, conclusion.id, "review", users.lead.id, "evidence package checked"
    )
    approved = trials.transition_trial_conclusion(
        ffl_db, context.trial.id, reviewed.id, "approved", users.lead.id, "limitations retained"
    )

    assert approved.status == "approved"
    assert approved.approved_at is not None


def test_playbook_can_only_publish_from_an_approved_promoting_conclusion(ffl_db, users):
    context = _trial_context(ffl_db, users)
    _activate(ffl_db, users, context)
    trials.transition_trial(ffl_db, context.trial.id, "completed", users.lead.id, "harvest records complete")
    artifact = _evidence(ffl_db, users.lead.id)
    playbook = trials.create_playbook(ffl_db, "Measured irrigation interval", 1, users.lead.id, _protocol())
    in_review = trials.transition_playbook(
        ffl_db, playbook.id, "review", users.lead.id, "submit protocol for review"
    )

    with pytest.raises(ValueError, match="supporting conclusion"):
        trials.transition_playbook(
            ffl_db, in_review.id, "published", users.lead.id, "publish", effective_from="2027-06-01"
        )

    conclusion = trials.create_trial_conclusion(
        ffl_db, context.trial.id, users.lead.id, _causal_result(context), "medium", ["Repeat next season"], artifact.id,
    )
    trials.transition_trial_conclusion(
        ffl_db, context.trial.id, conclusion.id, "review", users.lead.id, "review evidence"
    )
    promoted = trials.transition_trial_conclusion(
        ffl_db, context.trial.id, conclusion.id, "approved", users.lead.id, "approve bounded finding",
        playbook_decision="promote", playbook_id=in_review.id,
    )
    published = trials.transition_playbook(
        ffl_db, in_review.id, "published", users.lead.id, "publish reviewed protocol",
        effective_from="2027-06-01", supporting_conclusion_id=promoted.id,
    )

    assert published.status == "published"
    assert published.approved_by_person_id == users.lead.id
    assert repository.get_trial_conclusion(ffl_db, promoted.id).playbook_id == published.id
    with pytest.raises(ValueError, match="next version"):
        trials.create_playbook(ffl_db, "Measured irrigation interval", 3, users.lead.id, _protocol())


@pytest.fixture
def trials_api():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    create_schema(conn)
    lead = repository.create_person(conn, "Lead Agronomist", "agronomist")
    app = FastAPI()
    app.state.conn = conn
    app.include_router(trial_router)
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, conn=conn, lead=lead)
    conn.close()


def test_trial_api_returns_clear_422_and_exposes_traceable_detail(trials_api):
    invalid = trials_api.client.post(
        "/api/v1/trials",
        json={**_trial_payload(trials_api.lead.id), "guardrails": []},
    )
    created = trials_api.client.post("/api/v1/trials", json=_trial_payload(trials_api.lead.id))
    trial_id = created.json()["id"]
    missing = trials_api.client.get("/api/v1/trials/not-a-trial")
    detail = trials_api.client.get("/api/v1/trials/{0}".format(trial_id))

    assert invalid.status_code == 422
    assert "guardrails" in invalid.json()["detail"]
    assert created.status_code == 201
    assert missing.status_code == 404
    assert detail.status_code == 200
    assert detail.json()["trial"]["id"] == trial_id
    assert detail.json()["allocations"] == []
