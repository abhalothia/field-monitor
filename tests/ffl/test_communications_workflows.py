"""Versioned, allocation-specific farmer workflow safety checks."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from ffl.communications.persistence import (
    create_communication_profile,
    create_communications_schema,
    create_template,
    publish_template,
    set_scoped_consent,
    verify_endpoint,
)
from ffl.communications.workflows import (
    create_workflow_draft,
    create_workflow_runs,
    eligible_workflow_targets,
    publish_weekly_farmer_workflow,
    publish_workflow_version,
)
from ffl.persistence import repository
from ffl.persistence.database import translate_sqlite_sql


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "db" / "postgres" / "0021_agro_communications_control_plane.sql"


@pytest.fixture
def workflow_context(ffl_db, crop_allocation):
    create_communications_schema(ffl_db)
    now = "2026-08-07T12:00:00+00:00"
    admin = repository.create_person(ffl_db, "Workflow Admin", "manager")
    farmer = repository.create_person(ffl_db, "Workflow Farmer", "grower")
    ffl_db.execute(
        "INSERT INTO customer_portals VALUES (?, ?, ?, ?, 'active', ?)",
        ("workflow-portal", "workflow-portal", "Workflow Portal", "workflow.example.test", now),
    )
    for person, identity_id, role in (
        (admin, "workflow-admin-identity", "admin"),
        (farmer, "workflow-farmer-identity", "farmer"),
    ):
        ffl_db.execute(
            """INSERT INTO portal_identities
               (id, person_id, phone_e164, auth_subject, identity_status, invited_at,
                verified_at, last_authenticated_at, created_at)
               VALUES (?, ?, ?, ?, 'active', ?, ?, NULL, ?)""",
            (identity_id, person.id, "+91960000000" + str(1 if role == "admin" else 2),
             "workflow-" + role, now, now, now),
        )
        ffl_db.execute(
            """INSERT INTO portal_memberships
               (id, portal_id, person_id, identity_id, portal_role, membership_status,
                invited_at, activated_at, created_at)
               VALUES (?, 'workflow-portal', ?, ?, ?, 'active', ?, ?, ?)""",
            ("workflow-" + role + "-membership", person.id, identity_id, role, now, now, now),
        )
    second_block = repository.create_operational_block(
        ffl_db, crop_allocation.operating_unit_id, "Workflow Second Block", 2.0,
    )
    second = repository.create_crop_allocation(
        ffl_db, crop_allocation.operating_unit_id, second_block.id, crop_allocation.season_id,
        "Rice", None, 2.0,
    )
    for allocation in (crop_allocation, second):
        repository.create_person_operating_relationship(
            ffl_db, farmer.id, "crop_allocation", allocation.id, "grower", "2026-06-01",
            provenance="reviewed workflow farmer coverage",
        )
    ffl_db.commit()
    profile = create_communication_profile(
        ffl_db, "workflow-portal", farmer.id, "hi-IN", "Asia/Kolkata",
    )
    endpoint = verify_endpoint(
        ffl_db, profile["id"], "loopmessage", "+919876540101", "reviewed roster", admin.id,
    )
    for allocation in (crop_allocation, second):
        set_scoped_consent(
            ffl_db, profile["id"], endpoint["id"], "weekly_farmer_checkin",
            "crop_allocation", allocation.id, True, "signed workflow consent", admin.id,
        )
    template = create_template(
        ffl_db, "weekly-farmer", 1, "hi-IN", "weekly_farmer_checkin", "Weekly check-in",
        admin.id,
    )
    publish_template(ffl_db, template["id"], admin.id)
    return type("WorkflowContext", (), {
        "conn": ffl_db, "admin": admin, "farmer": farmer, "profile": profile,
        "endpoint": endpoint, "first": crop_allocation, "second": second, "template": template,
    })()


def _draft(context, **overrides):
    data = {
        "workflow_key": "weekly-farmer-checkin",
        "owner_id": context.admin.id,
        "purpose": "weekly_farmer_checkin",
        "trigger": {"kind": "weekly_farmer_checkin"},
        "audience": {
            "portal_id": "workflow-portal", "portal_role": "farmer", "active_allocation": True,
        },
        "template_id": context.template["id"],
        "expected_intents": ("confirm", "report_deviation", "request_callback", "help"),
        "response_deadline_hours": 72,
        "quiet_hours": ("22:00", "06:00"),
        "frequency_cap": 7,
        "escalation_owner_id": context.admin.id,
    }
    data.update(overrides)
    return create_workflow_draft(context.conn, **data)


def test_weekly_farmer_workflow_creates_one_run_per_eligible_allocation(workflow_context):
    version = publish_weekly_farmer_workflow(
        workflow_context.conn, owner_id=workflow_context.admin.id,
    )

    runs = create_workflow_runs(
        workflow_context.conn, version.id, due_at="2026-08-10T04:00:00+00:00",
        now="2026-08-10T04:00:00+00:00",
    )

    assert [(run.profile_id, run.allocation_id) for run in runs] == sorted([
        (workflow_context.profile["id"], workflow_context.first.id),
        (workflow_context.profile["id"], workflow_context.second.id),
    ])
    assert all(run.context_token for run in runs)
    assert create_workflow_runs(
        workflow_context.conn, version.id, due_at="2026-08-10T04:00:00+00:00",
        now="2026-08-10T04:00:00+00:00",
    ) == ()


def test_workflow_skips_revoked_or_out_of_quiet_hours_targets(workflow_context):
    version = publish_workflow_version(workflow_context.conn, _draft(workflow_context).id)
    workflow_context.conn.execute(
        "UPDATE communication_scoped_consents SET status = 'revoked', revoked_at = ? WHERE profile_id = ? AND scope_id = ?",
        ("2026-08-09T12:00:00+00:00", workflow_context.profile["id"], workflow_context.first.id),
    )

    quiet_targets = eligible_workflow_targets(
        workflow_context.conn, version.id, due_at="2026-08-10T18:00:00+00:00",
    )
    allowed_targets = eligible_workflow_targets(
        workflow_context.conn, version.id, due_at="2026-08-10T04:00:00+00:00",
    )

    assert quiet_targets == ()
    assert [(target.profile_id, target.allocation_id) for target in allowed_targets] == [
        (workflow_context.profile["id"], workflow_context.second.id),
    ]


def test_workflow_rejects_generic_audience_keys_and_keeps_published_capture_immutable(workflow_context):
    with pytest.raises(ValueError, match="unknown workflow audience keys"):
        _draft(workflow_context, audience={"portal_id": "workflow-portal", "sql": "SELECT *"})

    version = publish_workflow_version(workflow_context.conn, _draft(workflow_context).id)
    with pytest.raises(Exception, match="immutable"):
        workflow_context.conn.execute(
            "UPDATE communication_workflow_versions SET template_id = ? WHERE id = ?",
            ("replacement-template", version.id),
        )
    workflow_context.conn.rollback()
    with pytest.raises(Exception, match="lifecycle"):
        workflow_context.conn.execute(
            "UPDATE communication_workflow_versions SET published_at = ? WHERE id = ?",
            ("2026-08-11T00:00:00+00:00", version.id),
        )
    workflow_context.conn.rollback()


def test_workflow_frequency_cap_is_rechecked_as_weekly_runs_are_created(workflow_context):
    version = publish_workflow_version(
        workflow_context.conn, _draft(workflow_context, frequency_cap=1).id,
    )

    runs = create_workflow_runs(
        workflow_context.conn, version.id, due_at="2026-08-10T04:00:00+00:00",
    )

    assert len(runs) == 1


def test_workflow_run_conflict_rolls_back_its_interaction_and_retry_creates_one(workflow_context):
    version = publish_workflow_version(
        workflow_context.conn, _draft(workflow_context, frequency_cap=1).id,
    )
    before = workflow_context.conn.execute(
        "SELECT COUNT(*) AS count FROM communication_interaction_runs",
    ).fetchone()["count"]
    workflow_context.conn.execute(
        """CREATE TRIGGER workflow_run_conflict_for_test
           BEFORE INSERT ON communication_workflow_runs
           BEGIN
               SELECT RAISE(ABORT, 'UNIQUE constraint failed: communication_workflow_runs.profile_id');
           END""",
    )
    workflow_context.conn.commit()

    assert create_workflow_runs(
        workflow_context.conn, version.id, due_at="2026-08-10T04:00:00+00:00",
        now="2026-08-10T04:00:00+00:00",
    ) == ()
    assert workflow_context.conn.execute(
        "SELECT COUNT(*) AS count FROM communication_interaction_runs",
    ).fetchone()["count"] == before
    assert workflow_context.conn.execute(
        "SELECT COUNT(*) AS count FROM communication_workflow_runs",
    ).fetchone()["count"] == 0

    workflow_context.conn.execute("DROP TRIGGER workflow_run_conflict_for_test")
    workflow_context.conn.commit()
    runs = create_workflow_runs(
        workflow_context.conn, version.id, due_at="2026-08-10T04:00:00+00:00",
        now="2026-08-10T04:00:00+00:00",
    )

    assert len(runs) == 1
    assert workflow_context.conn.execute(
        "SELECT COUNT(*) AS count FROM communication_workflow_runs",
    ).fetchone()["count"] == 1


def test_workflow_run_uses_supplied_now_for_interaction_and_workflow_timestamps(workflow_context):
    version = publish_workflow_version(
        workflow_context.conn, _draft(workflow_context, frequency_cap=1).id,
    )
    now = "2026-08-11T05:30:00+00:00"
    runs = create_workflow_runs(
        workflow_context.conn, version.id, due_at="2026-08-10T04:00:00+00:00", now=now,
    )
    workflow_run = workflow_context.conn.execute(
        "SELECT * FROM communication_workflow_runs WHERE id = ?", (runs[0].id,),
    ).fetchone()
    interaction = workflow_context.conn.execute(
        "SELECT * FROM communication_interaction_runs WHERE id = ?", (runs[0].interaction_run_id,),
    ).fetchone()

    assert workflow_run["created_at"] == now
    assert interaction["created_at"] == now
    assert interaction["expires_at"] == "2026-08-14T05:30:00+00:00"


def test_postgres_workflow_relations_are_private_and_translate(workflow_context):
    sql = MIGRATION.read_text(encoding="utf-8")
    for table in ("agro_communication_workflows", "agro_communication_workflow_versions", "agro_communication_workflow_runs"):
        assert "CREATE TABLE IF NOT EXISTS " + table in sql
        assert "REVOKE ALL ON TABLE " + table + " FROM PUBLIC" in sql
    assert "(profile_id, allocation_id, workflow_version_id, weekly_window)" in sql
    assert translate_sqlite_sql(
        "SELECT * FROM communication_workflow_versions WHERE id = ?"
    ) == "SELECT * FROM agro_communication_workflow_versions WHERE id = %s"
