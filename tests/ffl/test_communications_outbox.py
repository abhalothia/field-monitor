"""Focused dispatch tests for the policy-controlled communications outbox."""

from datetime import datetime, timezone
import hashlib
import json
import sqlite3
import threading

import pytest

from ffl.communications import outbox as outbox_module
from ffl.communications import persistence
from ffl.communications.fake import FakeLoopMessageProvider
from ffl.communications.interactions import context_token_for_run, find_interaction_for_dispatch_callback
from ffl.communications.outbox import (
    _valid_parameters,
    dispatch_due_workflows,
    dispatch_ready_interaction,
    reconcile_outbox_messages,
)
from ffl.communications.ports import MessageStatus, SendResult
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


def test_opt_out_between_claim_and_send_suppresses_without_provider_call(dispatch_context, monkeypatch):
    provider = FakeLoopMessageProvider()
    real_details = outbox_module._dispatch_details
    calls = 0

    def details_with_interleaved_opt_out(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            dispatch_context.conn.execute(
                "UPDATE communication_scoped_consents SET status = 'revoked', revoked_at = ? WHERE endpoint_id = ?",
                ("2026-08-10T04:00:00+00:00", dispatch_context.endpoint["id"]),
            )
            dispatch_context.conn.commit()
            persistence.update_outbox_entry(
                dispatch_context.conn, dispatch_context.run.interaction_run_id,
                "suppressed", policy_code="scoped_opt_out",
            )
        return real_details(*args, **kwargs)

    monkeypatch.setattr(outbox_module, "_dispatch_details", details_with_interleaved_opt_out)
    result = dispatch_ready_interaction(
        dispatch_context.conn, provider, dispatch_context.run.interaction_run_id,
        datetime(2026, 8, 10, 4, 0, tzinfo=timezone.utc), context_token=dispatch_context.run.context_token,
    )

    assert result.status == "suppressed"
    assert provider.sent == []
    assert persistence.outbox_entry(dispatch_context.conn, dispatch_context.run.interaction_run_id)["status"] == "suppressed"


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


def test_scheduler_regenerates_the_interaction_context_token_after_restart(dispatch_context):
    provider = FakeLoopMessageProvider()
    provider.ambiguous_after_accept = True

    result = dispatch_due_workflows(
        dispatch_context.conn, provider, datetime(2026, 8, 10, 4, 0, tzinfo=timezone.utc),
    )

    assert result[0].status == "unknown"
    stored = dispatch_context.conn.execute(
        "SELECT context_token_hash FROM communication_interaction_runs WHERE id = ?",
        (dispatch_context.run.interaction_run_id,),
    ).fetchone()
    assert hashlib.sha256(provider.sent[0]["passthrough"].encode("utf-8")).hexdigest() == stored["context_token_hash"]
    assert provider.sent[0]["passthrough"] not in json.dumps(
        dict(dispatch_context.conn.execute("SELECT * FROM communication_outbox").fetchone()), sort_keys=True,
    )
    recovered = find_interaction_for_dispatch_callback(
        dispatch_context.conn, provider.name, dispatch_context.endpoint["id"], None,
        provider.sent[0]["passthrough"],
    )
    assert recovered is not None and recovered.id == dispatch_context.run.interaction_run_id


def test_template_parameters_are_strictly_empty():
    assert _valid_parameters({})
    assert not _valid_parameters({"farm": "North Block"})


def test_context_token_key_is_required(monkeypatch):
    monkeypatch.delenv("FFL_COMMUNICATION_CONTEXT_TOKEN_KEY")
    with pytest.raises(ValueError, match="CONTEXT_TOKEN_KEY"):
        context_token_for_run("interaction-run-1")


@pytest.mark.parametrize("provider_status, expected", (("unknown", "unknown"), ("failed", "failed")))
def test_provider_returned_terminal_status_is_not_marked_dispatched(dispatch_context, provider_status, expected):
    class TerminalStatusProvider(FakeLoopMessageProvider):
        def send_template(self, *args, **kwargs):
            accepted = super().send_template(*args, **kwargs)
            return SendResult(accepted.provider_message_id, provider_status)

    result = dispatch_ready_interaction(
        dispatch_context.conn, TerminalStatusProvider(), dispatch_context.run.interaction_run_id,
        datetime(2026, 8, 10, 4, 0, tzinfo=timezone.utc), context_token=dispatch_context.run.context_token,
    )

    outbox = dispatch_context.conn.execute("SELECT status, provider_message_id FROM communication_outbox").fetchone()
    assert result.status == outbox["status"] == expected
    assert outbox["provider_message_id"] == "fake-message-1"


def test_provider_returned_unknown_with_message_id_is_reconcilable(dispatch_context):
    class UnknownProvider(FakeLoopMessageProvider):
        def send_template(self, *args, **kwargs):
            accepted = super().send_template(*args, **kwargs)
            return SendResult(accepted.provider_message_id, "unknown")

    provider = UnknownProvider()
    result = dispatch_ready_interaction(
        dispatch_context.conn, provider, dispatch_context.run.interaction_run_id,
        datetime(2026, 8, 10, 4, 0, tzinfo=timezone.utc), context_token=dispatch_context.run.context_token,
    )
    provider.statuses[result.provider_message_id] = MessageStatus(result.provider_message_id, "delivered")

    assert result.status == "unknown"
    assert reconcile_outbox_messages(dispatch_context.conn, provider) == 1
    assert dispatch_context.conn.execute("SELECT status FROM communication_outbox").fetchone()["status"] == "dispatched"
    assert len(provider.sent) == 1


def test_atomic_claim_allows_only_one_connection_to_dispatch(dispatch_context, tmp_path):
    path = tmp_path / "outbox-race.db"
    first = sqlite3.connect(path, check_same_thread=False)
    dispatch_context.conn.backup(first)
    first.row_factory = sqlite3.Row
    second = sqlite3.connect(path, check_same_thread=False)
    second.row_factory = sqlite3.Row
    started = threading.Event()
    release = threading.Event()

    class BlockingProvider(FakeLoopMessageProvider):
        def send_template(self, *args, **kwargs):
            result = super().send_template(*args, **kwargs)
            started.set()
            assert release.wait(timeout=5)
            return result

    provider = BlockingProvider()
    now = datetime(2026, 8, 10, 4, 0, tzinfo=timezone.utc)
    outcomes = {}

    def dispatch_first():
        outcomes["first"] = dispatch_ready_interaction(
            first, provider, dispatch_context.run.interaction_run_id, now,
            context_token=dispatch_context.run.context_token,
        )

    try:
        first_thread = threading.Thread(target=dispatch_first)
        first_thread.start()
        assert started.wait(timeout=5)
        second_result = dispatch_ready_interaction(
            second, provider, dispatch_context.run.interaction_run_id, now,
            context_token=dispatch_context.run.context_token,
        )
        release.set()
        first_thread.join(timeout=5)
    finally:
        release.set()
        first.close()
        second.close()

    assert not first_thread.is_alive()
    assert outcomes["first"].status == "dispatched"
    assert second_result.status == "dispatching"
    assert len(provider.sent) == 1
