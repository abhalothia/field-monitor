"""Focused dispatch tests for the policy-controlled communications outbox."""

from datetime import datetime, timezone
import json

import pytest

from ffl.communications.fake import FakeLoopMessageProvider
from ffl.communications.outbox import dispatch_ready_interaction
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
    publish_workflow_version,
)
from ffl.persistence import repository


@pytest.fixture
def dispatch_context(ffl_db, crop_allocation):
    create_communications_schema(ffl_db)
    now = "2026-08-07T12:00:00+00:00"
    admin = repository.create_person(ffl_db, "Dispatch Admin", "manager")
    farmer = repository.create_person(ffl_db, "Dispatch Farmer", "grower")
    ffl_db.execute(
        "INSERT INTO customer_portals VALUES (?, ?, ?, ?, 'active', ?)",
        ("dispatch-portal", "dispatch-portal", "Dispatch Portal", "dispatch.example.test", now),
    )
    for person, suffix, role in ((admin, "admin", "admin"), (farmer, "farmer", "farmer")):
        ffl_db.execute(
            """INSERT INTO portal_identities
               (id, person_id, phone_e164, auth_subject, identity_status, invited_at, verified_at, last_authenticated_at, created_at)
               VALUES (?, ?, ?, ?, 'active', ?, ?, NULL, ?)""",
            ("dispatch-" + suffix + "-identity", person.id, "+91970000000" + ("1" if suffix == "admin" else "2"),
             "dispatch-" + suffix, now, now, now),
        )
        ffl_db.execute(
            """INSERT INTO portal_memberships
               (id, portal_id, person_id, identity_id, portal_role, membership_status, invited_at, activated_at, created_at)
               VALUES (?, 'dispatch-portal', ?, ?, ?, 'active', ?, ?, ?)""",
            ("dispatch-" + suffix + "-membership", person.id, "dispatch-" + suffix + "-identity", role, now, now, now),
        )
    repository.create_person_operating_relationship(
        ffl_db, farmer.id, "crop_allocation", crop_allocation.id, "grower", "2026-06-01",
        provenance="reviewed dispatch farmer coverage",
    )
    ffl_db.commit()
    profile = create_communication_profile(ffl_db, "dispatch-portal", farmer.id, "hi-IN", "Asia/Kolkata")
    endpoint = verify_endpoint(ffl_db, profile["id"], "loopmessage", "+919876540102", "reviewed roster", admin.id)
    set_scoped_consent(
        ffl_db, profile["id"], endpoint["id"], "weekly_farmer_checkin", "crop_allocation", crop_allocation.id,
        True, "signed dispatch consent", admin.id,
    )
    template = create_template(
        ffl_db, "weekly-hi", 1, "hi-IN", "weekly_farmer_checkin", "Weekly check-in", admin.id,
        provider_template_id="weekly-hi-v1", provider_approval_state="approved",
    )
    publish_template(ffl_db, template["id"], admin.id)
    draft = create_workflow_draft(
        ffl_db, workflow_key="dispatch-weekly", owner_id=admin.id, purpose="weekly_farmer_checkin",
        trigger={"kind": "weekly_farmer_checkin"},
        audience={"portal_id": "dispatch-portal", "portal_role": "farmer", "active_allocation": True},
        template_id=template["id"], expected_intents=("confirm",), response_deadline_hours=72,
    )
    version = publish_workflow_version(ffl_db, draft.id)
    runs = create_workflow_runs(
        ffl_db, version.id, due_at="2026-08-10T04:00:00+00:00", now="2026-08-10T04:00:00+00:00",
    )
    assert len(runs) == 1
    return type("DispatchContext", (), {
        "conn": ffl_db, "run": runs[0], "endpoint": endpoint, "profile": profile,
        "allocation": crop_allocation,
    })()


def test_dispatch_uses_approved_template_and_records_provider_message_id(dispatch_context):
    provider = FakeLoopMessageProvider()

    result = dispatch_ready_interaction(
        dispatch_context.conn, provider, dispatch_context.run.interaction_run_id,
        datetime(2026, 8, 10, 4, 0, tzinfo=timezone.utc), context_token=dispatch_context.run.context_token,
    )

    assert result.status == "dispatched"
    assert provider.sent[0]["template_id"] == "weekly-hi-v1"
    dispatch = dispatch_context.conn.execute(
        "SELECT provider_message_id FROM communication_interaction_dispatches WHERE interaction_run_id = ?",
        (dispatch_context.run.interaction_run_id,),
    ).fetchone()
    assert dispatch["provider_message_id"] == "fake-message-1"
    outbox = dispatch_context.conn.execute("SELECT * FROM communication_outbox").fetchone()
    assert dispatch_context.run.context_token not in json.dumps(dict(outbox), sort_keys=True)


def test_dispatch_refuses_revoked_consent_without_calling_provider(dispatch_context):
    provider = FakeLoopMessageProvider()
    dispatch_context.conn.execute(
        "UPDATE communication_scoped_consents SET status = 'revoked', revoked_at = ? WHERE endpoint_id = ?",
        ("2026-08-10T03:00:00+00:00", dispatch_context.endpoint["id"]),
    )
    dispatch_context.conn.commit()

    result = dispatch_ready_interaction(
        dispatch_context.conn, provider, dispatch_context.run.interaction_run_id,
        datetime(2026, 8, 10, 4, 0, tzinfo=timezone.utc), context_token=dispatch_context.run.context_token,
    )

    assert result.status == "suppressed"
    assert provider.sent == []


def test_ambiguous_dispatch_is_unknown_and_never_retries(dispatch_context):
    provider = FakeLoopMessageProvider()
    provider.ambiguous_after_accept = True
    now = datetime(2026, 8, 10, 4, 0, tzinfo=timezone.utc)

    first = dispatch_ready_interaction(
        dispatch_context.conn, provider, dispatch_context.run.interaction_run_id,
        now, context_token=dispatch_context.run.context_token,
    )
    second = dispatch_ready_interaction(
        dispatch_context.conn, provider, dispatch_context.run.interaction_run_id,
        now, context_token=dispatch_context.run.context_token,
    )

    assert first.status == second.status == "unknown"
    assert len(provider.sent) == 1
