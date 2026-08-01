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


def _trial_payload(owner_id, operating_unit_id="unit-id", season_id="season-id"):
    return {
        "name": "Irrigation interval pilot",
        "hypothesis": "A measured interval may reduce water use without reducing grade-A output.",
        "owner_id": owner_id,
        "protocol_version": "v1",
        "decision_question": "Whether to retain the interval for the next pilot season.",
        "treatment": {"interval_hours": 48},
        "comparator": {"interval_hours": 36},
        "eligibility_rule": {
            "operating_unit_ids": [operating_unit_id],
            "season_ids": [season_id],
            "crop_names": ["Rice"],
            "allocation_statuses": ["active"],
        },
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
        ffl_db, unit.id, unrelated_block.id, season.id, "Wheat", None, 2.0
    )
    trial = trials.create_trial(ffl_db, **_trial_payload(users.lead.id, unit.id, season.id))
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


def _causal_result(context, evidence_artifact_id):
    return {
        "summary": "The observed output difference is conditional on the documented comparison.",
        "claim_type": "causal",
        "comparison_context": {
            "control_strategy": "Pre-specified matched operational blocks with same measurement protocol.",
            "treatment_allocation_ids": [context.treatment.id],
            "comparator_allocation_ids": [context.comparator.id],
        },
        "measurement_coverage": [{
            "outcome": "grade_a_output",
            "method": "weighbridge",
            "observations": [
                {"allocation_id": context.treatment.id, "evidence_artifact_id": evidence_artifact_id},
                {"allocation_id": context.comparator.id, "evidence_artifact_id": evidence_artifact_id},
            ],
        }],
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


def test_trial_owner_and_eligibility_contract_protect_enrolment(ffl_db, users):
    unit = repository.create_operating_unit(ffl_db, "Owner policy farm")
    season = repository.create_season(ffl_db, unit.id, "Kharif 2026", "2026-06-01", "2026-11-30")
    payload = _trial_payload(users.operator.id, unit.id, season.id)
    with pytest.raises(ValueError, match="trial owner"):
        trials.create_trial(ffl_db, **payload)

    context = _trial_context(ffl_db, users)
    unsafe_trial = repository.create_trial(
        ffl_db, "Unsafe owner", "Do not use", users.operator.id, "v1", "Never activate",
        {"rate": 1}, {"rate": 0}, context.trial.eligibility_rule,
        [{"outcome": "grade_a_output", "method": "weighbridge", "cadence": "harvest"}],
        [{"threshold": "any deviation", "action": "stop"}],
    )
    with pytest.raises(ValueError, match="trial owner"):
        trials.add_trial_allocation(
            ffl_db, unsafe_trial.id, context.treatment.id, "treatment", users.lead.id
        )
    with pytest.raises(ValueError, match="eligibility rule"):
        trials.add_trial_allocation(
            ffl_db, context.trial.id, context.unrelated.id, "treatment", users.lead.id
        )
    trial_unit = ffl_db.execute(
        "SELECT operating_unit_id FROM crop_allocations WHERE id = ?", (context.treatment.id,)
    ).fetchone()["operating_unit_id"]
    other_season = repository.create_season(
        ffl_db, trial_unit, "Rabi 2026", "2026-12-01", "2027-04-30"
    )
    other_season_block = repository.create_operational_block(ffl_db, trial_unit, "Other season", 1.0)
    other_season_allocation = repository.create_crop_allocation(
        ffl_db, trial_unit, other_season_block.id, other_season.id, "Rice", None, 1.0
    )
    other_unit = repository.create_operating_unit(ffl_db, "Other farm")
    other_unit_season = repository.create_season(
        ffl_db, other_unit.id, "Kharif 2026", "2026-06-01", "2026-11-30"
    )
    other_unit_block = repository.create_operational_block(ffl_db, other_unit.id, "Other farm block", 1.0)
    other_farm_allocation = repository.create_crop_allocation(
        ffl_db, other_unit.id, other_unit_block.id, other_unit_season.id, "Rice", None, 1.0
    )
    for allocation in (other_season_allocation, other_farm_allocation):
        with pytest.raises(ValueError, match="eligibility rule"):
            trials.add_trial_allocation(
                ffl_db, context.trial.id, allocation.id, "treatment", users.lead.id
            )
    ffl_db.execute("UPDATE crop_allocations SET status = 'inactive' WHERE id = ?", (context.treatment.id,))
    ffl_db.commit()
    with pytest.raises(ValueError, match="only active"):
        trials.add_trial_allocation(
            ffl_db, context.trial.id, context.treatment.id, "treatment", users.lead.id
        )


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


def test_eligible_allocation_has_no_enrolment_time_until_explicit_enrolment(ffl_db, users):
    context = _trial_context(ffl_db, users)
    pending = trials.add_trial_allocation(
        ffl_db, context.trial.id, context.treatment.id, "treatment", users.lead.id
    )
    enrolled = trials.transition_trial_allocation(
        ffl_db, context.trial.id, pending.id, "enrolled", users.lead.id, "eligible and consented"
    )

    assert pending.enrolled_at is None
    assert enrolled.enrolled_at is not None


def test_activation_rechecks_live_eligibility_for_every_enrolled_allocation(ffl_db, users):
    context = _trial_context(ffl_db, users)
    treatment = trials.add_trial_allocation(
        ffl_db, context.trial.id, context.treatment.id, "treatment", users.lead.id
    )
    comparator = trials.add_trial_allocation(
        ffl_db, context.trial.id, context.comparator.id, "comparator", users.lead.id
    )
    trials.transition_trial_allocation(
        ffl_db, context.trial.id, treatment.id, "enrolled", users.lead.id, "eligible"
    )
    trials.transition_trial_allocation(
        ffl_db, context.trial.id, comparator.id, "enrolled", users.lead.id, "eligible"
    )
    ffl_db.execute("UPDATE crop_allocations SET status = 'inactive' WHERE id = ?", (context.treatment.id,))
    ffl_db.commit()

    with pytest.raises(ValueError, match="only active"):
        trials.transition_trial(ffl_db, context.trial.id, "active", users.lead.id, "start")


def test_schema_migrates_legacy_non_null_trial_enrolment_timestamp():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """CREATE TABLE trial_allocations (
            id TEXT PRIMARY KEY, trial_id TEXT NOT NULL, allocation_id TEXT NOT NULL, arm TEXT NOT NULL,
            status TEXT NOT NULL, enrolled_at TEXT NOT NULL, withdrawn_at TEXT, reason TEXT, created_at TEXT NOT NULL,
            UNIQUE (trial_id, allocation_id)
        )"""
    )
    conn.execute(
        """INSERT INTO trial_allocations
           VALUES ('legacy-eligible', 'legacy-trial', 'legacy-allocation', 'treatment', 'eligible',
                   '2026-08-01T00:00:00+00:00', NULL, NULL, '2026-08-01T00:00:00+00:00')"""
    )
    create_schema(conn)

    enrolled_at = next(row for row in conn.execute("PRAGMA table_info(trial_allocations)") if row[1] == "enrolled_at")
    assert enrolled_at[3] == 0
    assert conn.execute(
        "SELECT enrolled_at FROM trial_allocations WHERE id = 'legacy-eligible'"
    ).fetchone()[0] is None
    conn.close()


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
        ffl_db, context.trial.id, users.lead.id, _causal_result(context, artifact.id), "medium", [], artifact.id,
        )

    conclusion = trials.create_trial_conclusion(
        ffl_db, context.trial.id, users.lead.id, _causal_result(context, artifact.id), "medium",
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


def test_causal_conclusion_rejects_withdrawn_cohort_or_missing_measurement_coverage(ffl_db, users):
    context = _trial_context(ffl_db, users)
    _activate(ffl_db, users, context)
    treatment_allocation = repository.list_trial_allocations(ffl_db, context.trial.id)[0]
    trials.transition_trial(ffl_db, context.trial.id, "paused", users.lead.id, "recheck cohort")
    trials.transition_trial_allocation(
        ffl_db, context.trial.id, treatment_allocation.id, "withdrawn", users.lead.id, "missed harvest measurement"
    )
    trials.transition_trial(ffl_db, context.trial.id, "stopped", users.lead.id, "cohort incomplete")
    artifact = _evidence(ffl_db, users.lead.id)

    with pytest.raises(ValueError, match="complete declared comparison cohort"):
        trials.create_trial_conclusion(
            ffl_db, context.trial.id, users.lead.id, _causal_result(context, artifact.id), "low",
            ["One allocation withdrawn"], artifact.id,
        )

    context = _trial_context(ffl_db, users)
    _activate(ffl_db, users, context)
    trials.transition_trial(ffl_db, context.trial.id, "completed", users.lead.id, "harvest records complete")
    artifact = _evidence(ffl_db, users.lead.id)
    missing_measurement = _causal_result(context, artifact.id)
    missing_measurement["measurement_coverage"] = []
    with pytest.raises(ValueError, match="measurement_coverage must be a non-empty list"):
        trials.create_trial_conclusion(
            ffl_db, context.trial.id, users.lead.id, missing_measurement, "low", ["Pilot only"], artifact.id,
        )


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
        ffl_db, context.trial.id, users.lead.id, _causal_result(context, artifact.id), "medium", ["Repeat next season"], artifact.id,
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
