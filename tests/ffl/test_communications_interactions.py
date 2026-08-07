import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ffl.communications.interactions import (
    create_interaction_run,
    find_interaction_for_inbound,
    interaction_run,
    record_interaction_dispatch,
    route_inbound_interaction,
)
from ffl.communications.persistence import (
    create_communication_profile,
    create_communications_schema,
    verify_endpoint,
)
from ffl.persistence import repository
from ffl.persistence.database import translate_sqlite_sql


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "db" / "postgres" / "0021_agro_communications_control_plane.sql"


@pytest.fixture
def interaction_context(ffl_db, crop_allocation):
    create_communications_schema(ffl_db)
    farmer = repository.create_person(ffl_db, "Interaction Farmer", "grower")
    admin = repository.create_person(ffl_db, "Interaction Admin", "manager")
    now = datetime.now(timezone.utc).isoformat()
    ffl_db.execute(
        "INSERT INTO customer_portals VALUES (?, ?, ?, ?, 'active', ?)",
        ("interaction-portal", "interaction-portal", "Interaction Portal", "interactions.example.test", now),
    )
    for identity_id, person_id, phone, subject in (
        ("interaction-farmer-identity", farmer.id, "+919800001001", "interaction-farmer"),
        ("interaction-admin-identity", admin.id, "+919800001002", "interaction-admin"),
    ):
        ffl_db.execute(
            """INSERT INTO portal_identities
               (id, person_id, phone_e164, auth_subject, identity_status, invited_at,
                verified_at, last_authenticated_at, created_at)
               VALUES (?, ?, ?, ?, 'active', ?, ?, NULL, ?)""",
            (identity_id, person_id, phone, subject, now, now, now),
        )
    for membership_id, person_id, identity_id, role in (
        ("interaction-farmer-membership", farmer.id, "interaction-farmer-identity", "farmer"),
        ("interaction-admin-membership", admin.id, "interaction-admin-identity", "admin"),
    ):
        ffl_db.execute(
            """INSERT INTO portal_memberships
               (id, portal_id, person_id, identity_id, portal_role, membership_status,
                invited_at, activated_at, created_at)
               VALUES (?, 'interaction-portal', ?, ?, ?, 'active', ?, ?, ?)""",
            (membership_id, person_id, identity_id, role, now, now, now),
        )
    ffl_db.commit()
    profile = create_communication_profile(
        ffl_db, "interaction-portal", farmer.id, "hi-IN", "Asia/Kolkata",
    )
    endpoint = verify_endpoint(
        ffl_db, profile["id"], "loopmessage", "+919876540001",
        "portal_invitation", admin.id,
    )
    return type(
        "InteractionContext",
        (),
        {"conn": ffl_db, "profile": profile, "endpoint": endpoint, "allocation": crop_allocation},
    )()


def _ready_run(context, *, allocation_id=None, expires_at=None, expected_intents=("confirm",)):
    return create_interaction_run(
        context.conn,
        context.profile["id"],
        context.endpoint["id"],
        allocation_id=allocation_id or context.allocation.id,
        workflow_version_id="weekly-checkin-v1",
        expected_intents=expected_intents,
        expires_at=expires_at or (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    )


def test_reply_to_message_resolves_exact_run_when_recipient_has_two_open_requests(interaction_context):
    first = _ready_run(interaction_context)
    second = _ready_run(interaction_context)
    record_interaction_dispatch(interaction_context.conn, first.id, "provider-first")
    record_interaction_dispatch(interaction_context.conn, second.id, "provider-second")

    resolved = find_interaction_for_inbound(
        interaction_context.conn,
        "loopmessage",
        interaction_context.endpoint["id"],
        "provider-second",
        None,
    )

    assert resolved is not None
    assert resolved.id == second.id


def test_unmatched_reply_never_selects_the_latest_open_run(interaction_context):
    run = _ready_run(interaction_context)
    record_interaction_dispatch(interaction_context.conn, run.id, "provider-first")

    assert find_interaction_for_inbound(
        interaction_context.conn,
        "loopmessage",
        interaction_context.endpoint["id"],
        None,
        "unknown-token",
    ) is None
    assert interaction_run(interaction_context.conn, run.id).status == "dispatched"


def test_valid_context_token_resolves_only_its_dispatched_run(interaction_context):
    run = _ready_run(interaction_context)
    record_interaction_dispatch(interaction_context.conn, run.id, "provider-first")

    resolved = find_interaction_for_inbound(
        interaction_context.conn,
        "loopmessage",
        interaction_context.endpoint["id"],
        "unmatched-provider-message",
        run.context_token,
    )

    assert resolved is not None
    assert resolved.id == run.id


def test_reply_to_message_id_wins_over_a_conflicting_valid_context_token(interaction_context):
    first = _ready_run(interaction_context)
    second = _ready_run(interaction_context)
    record_interaction_dispatch(interaction_context.conn, first.id, "provider-first")
    record_interaction_dispatch(interaction_context.conn, second.id, "provider-second")

    resolved = find_interaction_for_inbound(
        interaction_context.conn,
        "loopmessage",
        interaction_context.endpoint["id"],
        "provider-first",
        second.context_token,
    )

    assert resolved is not None
    assert resolved.id == first.id


def test_context_token_is_returned_once_but_only_its_hash_is_persisted(interaction_context):
    run = _ready_run(interaction_context, expected_intents=("confirm", "report_deviation"))
    row = interaction_context.conn.execute(
        "SELECT * FROM communication_interaction_runs WHERE id = ?", (run.id,),
    ).fetchone()
    columns = {
        column["name"]
        for column in interaction_context.conn.execute("PRAGMA table_info(communication_interaction_runs)")
    }

    assert run.context_token
    assert "context_token" not in columns
    assert row["context_token_hash"] == hashlib.sha256(run.context_token.encode("utf-8")).hexdigest()
    assert run.context_token not in tuple(str(value) for value in row)

    with pytest.raises(Exception, match="immutable"):
        interaction_context.conn.execute(
            "UPDATE communication_interaction_runs SET context_token_hash = ? WHERE id = ?",
            ("0" * 64, run.id),
        )


def test_context_token_is_bound_to_provider_endpoint_status_and_expiry(interaction_context):
    run = _ready_run(interaction_context)
    record_interaction_dispatch(interaction_context.conn, run.id, "provider-first")

    assert find_interaction_for_inbound(
        interaction_context.conn, "other-provider", interaction_context.endpoint["id"],
        None, run.context_token,
    ) is None
    assert find_interaction_for_inbound(
        interaction_context.conn, "loopmessage", "other-endpoint", None, run.context_token,
    ) is None
    assert find_interaction_for_inbound(
        interaction_context.conn, "loopmessage", interaction_context.endpoint["id"],
        None, run.context_token,
        now=(datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
    ) is None


def test_route_rejects_an_intent_outside_the_immutable_expected_set(interaction_context):
    run = _ready_run(interaction_context, expected_intents=("confirm", "decline"))
    record_interaction_dispatch(interaction_context.conn, run.id, "provider-first")

    assert route_inbound_interaction(
        interaction_context.conn,
        "loopmessage",
        interaction_context.endpoint["id"],
        "provider-first",
        None,
        "report_deviation",
    ) is None
    assert route_inbound_interaction(
        interaction_context.conn,
        "loopmessage",
        interaction_context.endpoint["id"],
        "provider-first",
        None,
        "confirm",
    ).id == run.id


def test_postgres_interaction_tables_are_private_and_index_exact_correlation_paths():
    sql = MIGRATION.read_text(encoding="utf-8")

    for table in (
        "agro_communication_interaction_runs",
        "agro_communication_interaction_dispatches",
    ):
        assert "CREATE TABLE IF NOT EXISTS " + table in sql
        assert "REVOKE ALL ON TABLE " + table + " FROM PUBLIC" in sql
    assert "context_token_hash TEXT NOT NULL UNIQUE" in sql
    assert "context_token TEXT" not in sql
    assert "(provider, provider_message_id)" in sql
    assert "agro_idx_communication_interaction_runs_endpoint_status" in sql
    assert translate_sqlite_sql(
        "SELECT * FROM communication_interaction_runs WHERE endpoint_id = ?"
    ) == "SELECT * FROM agro_communication_interaction_runs WHERE endpoint_id = %s"
