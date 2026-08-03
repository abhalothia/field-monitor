"""Focused contract tests for provider-neutral field information requests."""

import sqlite3
from pathlib import Path

import pytest

from ffl.persistence import repository
from ffl.persistence.database import translate_sqlite_sql
from ffl.persistence.schema import create_schema
from ffl.services import field_information_requests
from ffl.services.operations import create_work_item


def _draft_request(conn, allocation, users, **overrides):
    payload = {
        "allocation_id": allocation.id,
        "target_person_id": users.operator.id,
        "request_kind": "field_check",
        "evidence_required": True,
        "due_at": "2026-07-10T09:00:00+05:30",
        "request_copy_en": "Please check North Block and send one photo before 9:00 AM.",
        "request_copy_hi": "कृपया नॉर्थ ब्लॉक देखें और सुबह 9 बजे से पहले एक फोटो भेजें।",
        "idempotency_key": "field-check:north-block:001",
        "initiated_by_person_id": users.manager.id,
    }
    payload.update(overrides)
    return field_information_requests.create_information_request(conn, **payload)


def test_request_is_a_replay_safe_immutable_bilingual_intent(ffl_db, crop_allocation, users):
    work = create_work_item(
        ffl_db, crop_allocation.id, "Revisit a coverage gap", users.manager.id,
        "2026-07-10T09:00:00+05:30",
    )
    request = _draft_request(ffl_db, crop_allocation, users, work_item_id=work.id)
    replay = _draft_request(ffl_db, crop_allocation, users, work_item_id=work.id)

    assert replay.id == request.id
    assert request.status == "draft"
    assert request.allocation_id == crop_allocation.id
    assert request.target_person_id == users.operator.id
    assert request.work_item_id == work.id
    assert request.evidence_required is True
    assert request.request_copy_en.startswith("Please check")
    assert "फोटो" in request.request_copy_hi
    assert [(event.from_status, event.to_status, event.actor_person_id) for event in repository.list_field_information_request_events(
        ffl_db, request.id
    )] == [("created", "draft", users.manager.id)]

    system_created = _draft_request(
        ffl_db, crop_allocation, users, idempotency_key="coverage-recovery:system:001",
        initiated_by_person_id=None, initiated_by_system_key="system:coverage-recovery",
    )
    assert system_created.initiated_by_person_id is None
    assert system_created.initiated_by_system_key == "system:coverage-recovery"

    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        ffl_db.execute(
            "UPDATE field_information_requests SET request_copy_en = ? WHERE id = ?",
            ("different words", request.id),
        )
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        ffl_db.execute("DELETE FROM field_information_requests WHERE id = ?", (request.id,))


def test_request_rejects_unbounded_or_mismatched_context(ffl_db, crop_allocation, users):
    work = create_work_item(
        ffl_db, crop_allocation.id, "Inspect irrigation", users.manager.id,
        "2026-07-10T09:00:00+05:30",
    )
    other_unit = repository.create_operating_unit(ffl_db, "Other Farm")
    other_block = repository.create_operational_block(ffl_db, other_unit.id, "Other Block", 1.0)
    other_season = repository.create_season(
        ffl_db, other_unit.id, "Kharif 2026", "2026-06-01", "2026-11-30"
    )
    other_allocation = repository.create_crop_allocation(
        ffl_db, other_unit.id, other_block.id, other_season.id, "Rice", None, 1.0
    )

    with pytest.raises(ValueError, match="request_kind must be"):
        _draft_request(ffl_db, crop_allocation, users, request_kind="recommendation")
    with pytest.raises(ValueError, match="evidence_required must be"):
        _draft_request(ffl_db, crop_allocation, users, evidence_required=1)
    with pytest.raises(ValueError, match="due_at must include a timezone"):
        _draft_request(ffl_db, crop_allocation, users, due_at="2026-07-10T09:00:00")
    with pytest.raises(ValueError, match="target person does not exist"):
        _draft_request(ffl_db, crop_allocation, users, target_person_id="missing")
    with pytest.raises(ValueError, match="same crop allocation"):
        _draft_request(ffl_db, other_allocation, users, work_item_id=work.id)
    with pytest.raises(sqlite3.IntegrityError, match="same crop allocation"):
        ffl_db.execute(
            """INSERT INTO field_information_requests (
                id, allocation_id, target_person_id, work_item_id, request_kind, evidence_required,
                due_at, request_copy_en, request_copy_hi, initiated_by_person_id,
                initiated_by_system_key, idempotency_key, status, created_at
            ) VALUES (?, ?, ?, ?, 'field_check', 1, ?, ?, ?, ?, NULL, ?, 'draft', ?)""",
            (
                "wrong-work-allocation", other_allocation.id, users.operator.id, work.id,
                "2026-07-10T09:00:00+05:30", "Check", "जांचें", users.manager.id,
                "direct-work-link:001", "2026-07-09T00:00:00+00:00",
            ),
        )
    with pytest.raises(ValueError, match="either initiated"):
        _draft_request(
            ffl_db, crop_allocation, users, initiated_by_person_id=users.manager.id,
            initiated_by_system_key="system:recovery-job",
        )
    with pytest.raises(ValueError, match="system:<name>"):
        _draft_request(
            ffl_db, crop_allocation, users, initiated_by_person_id=None,
            initiated_by_system_key="loopmessage",
        )


def test_only_valid_lifecycle_transitions_are_recorded_and_response_is_not_field_truth(
    ffl_db, crop_allocation, users
):
    request = _draft_request(ffl_db, crop_allocation, users)

    with pytest.raises(ValueError, match="invalid field information request transition"):
        field_information_requests.mark_information_request_dispatched(
            ffl_db, request.id, actor_system_key="system:future-provider"
        )

    ready = field_information_requests.ready_information_request(
        ffl_db, request.id, actor_person_id=users.manager.id
    )
    dispatched = field_information_requests.mark_information_request_dispatched(
        ffl_db, ready.id, actor_system_key="system:future-provider"
    )
    responded = field_information_requests.mark_information_request_responded(
        ffl_db, dispatched.id, actor_system_key="system:future-intake"
    )

    assert responded.status == "responded"
    assert repository.list_work_items(ffl_db, crop_allocation.id) == []
    assert ffl_db.execute("SELECT COUNT(*) FROM field_signals").fetchone()[0] == 0
    assert [event.to_status for event in repository.list_field_information_request_events(
        ffl_db, request.id
    )] == ["draft", "ready", "dispatched", "responded"]
    with pytest.raises(sqlite3.IntegrityError, match="invalid field information request transition"):
        ffl_db.execute(
            "UPDATE field_information_requests SET status = 'ready' WHERE id = ?", (request.id,)
        )


def test_due_expiry_keeps_linked_recovery_work_open(ffl_db, crop_allocation, users):
    recovery_work = create_work_item(
        ffl_db, crop_allocation.id, "Recover unvisited field coverage", users.manager.id,
        "2026-07-10T09:00:00+05:30",
    )
    overdue = _draft_request(
        ffl_db, crop_allocation, users, work_item_id=recovery_work.id,
        idempotency_key="coverage-recovery:001", due_at="2026-07-09T09:00:00+05:30",
    )
    not_due = _draft_request(
        ffl_db, crop_allocation, users, idempotency_key="coverage-recovery:002",
        due_at="2026-07-11T09:00:00+05:30",
    )

    expired = field_information_requests.expire_due_information_requests(
        ffl_db, "2026-07-10T12:00:00+05:30"
    )

    assert [item.id for item in expired] == [overdue.id]
    assert repository.get_field_information_request(ffl_db, overdue.id).status == "expired"
    assert repository.get_field_information_request(ffl_db, not_due.id).status == "draft"
    assert repository.get_work_item(ffl_db, recovery_work.id).status == "in_progress"
    assert repository.list_field_information_request_events(ffl_db, overdue.id)[-1].actor_system_key == (
        field_information_requests.EXPIRY_SYSTEM_ACTOR
    )
    assert field_information_requests.expire_due_information_requests(
        ffl_db, "2026-07-10T12:00:00+05:30"
    ) == []


def test_schema_is_preview_safe_and_private_postgres_migration_is_manual(ffl_db):
    # Re-running the SQLite bootstrap adds the isolated request ledger without
    # rebuilding existing operating records.
    unit = repository.create_operating_unit(ffl_db, "Existing Preview Farm")
    create_schema(ffl_db)

    assert {row["name"] for row in ffl_db.execute("PRAGMA table_info(field_information_requests)")} >= {
        "allocation_id", "target_person_id", "request_kind", "request_copy_en", "request_copy_hi",
        "idempotency_key", "status",
    }
    assert repository.get_operating_unit(ffl_db, unit.id) == unit
    assert translate_sqlite_sql("SELECT * FROM field_information_requests WHERE id = ?") == (
        "SELECT * FROM agro_field_information_requests WHERE id = %s"
    )

    migration = (
        Path(__file__).resolve().parents[2] / "db/postgres/0005_agro_field_information_requests.sql"
    ).read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS agro_field_information_requests" in migration
    assert "CREATE TABLE IF NOT EXISTS agro_field_information_request_events" in migration
    assert "REVOKE ALL ON TABLE agro_field_information_requests" in migration
    assert "Supabase's Data API" in migration
    assert "LoopMessage" not in migration
