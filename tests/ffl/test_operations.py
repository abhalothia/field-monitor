import sqlite3

import pytest

from ffl.services.operations import (
    create_work_item,
    list_audit_events,
    report_exception,
    transition_work_item,
)
from ffl.persistence import repository


def test_work_requires_submission_before_acceptance(ffl_db, crop_allocation, users):
    work = create_work_item(
        ffl_db,
        crop_allocation.id,
        "Inspect irrigation",
        users.manager.id,
        "2026-07-10T09:00:00+00:00",
    )

    with pytest.raises(ValueError, match="invalid work transition"):
        transition_work_item(ffl_db, work.id, "accepted", users.manager.id, "reviewed")

    submitted = transition_work_item(
        ffl_db, work.id, "submitted", users.operator.id, "photo attached"
    )
    accepted = transition_work_item(
        ffl_db, submitted.id, "accepted", users.manager.id, "verified"
    )

    assert accepted.status == "accepted"
    assert [
        event.to_status for event in list_audit_events(ffl_db, "work_item", work.id)
    ] == ["submitted", "accepted"]


def test_replayed_exception_key_returns_same_exception(ffl_db, crop_allocation, users):
    first = report_exception(
        ffl_db,
        crop_allocation.id,
        "Leaf damage",
        "high",
        users.manager.id,
        users.lead.id,
        "2026-07-10T08:00:00+00:00",
        "device-7:42",
    )
    replay = report_exception(
        ffl_db,
        crop_allocation.id,
        "Leaf damage",
        "high",
        users.manager.id,
        users.lead.id,
        "2026-07-10T08:00:00+00:00",
        "device-7:42",
    )

    assert replay.id == first.id


def test_explicitly_planned_work_follows_planned_lifecycle(ffl_db, crop_allocation, users):
    work = create_work_item(
        ffl_db,
        crop_allocation.id,
        "Plan irrigation inspection",
        users.manager.id,
        "2026-07-10T09:00:00+00:00",
        initial_status="planned",
    )

    in_progress = transition_work_item(
        ffl_db, work.id, "in_progress", users.manager.id, "scheduled"
    )
    submitted = transition_work_item(
        ffl_db, in_progress.id, "submitted", users.operator.id, "complete"
    )

    assert submitted.status == "submitted"


def test_work_rejects_unknown_initial_status(ffl_db, crop_allocation, users):
    with pytest.raises(ValueError, match="invalid work status"):
        create_work_item(
            ffl_db,
            crop_allocation.id,
            "Unknown status work",
            users.manager.id,
            "2026-07-10T09:00:00+00:00",
            initial_status="unknown",
        )


def test_failed_audit_rolls_back_work_status_change(ffl_db, crop_allocation, users):
    work = create_work_item(
        ffl_db,
        crop_allocation.id,
        "Inspect irrigation",
        users.manager.id,
        "2026-07-10T09:00:00+00:00",
    )
    ffl_db.execute(
        """
        CREATE TRIGGER reject_work_audit
        BEFORE INSERT ON audit_events
        WHEN NEW.entity_type = 'work_item'
        BEGIN
            SELECT RAISE(ABORT, 'audit unavailable');
        END;
        """
    )

    with pytest.raises(sqlite3.IntegrityError, match="audit unavailable"):
        transition_work_item(ffl_db, work.id, "submitted", users.operator.id, "complete")

    assert repository.get_work_item(ffl_db, work.id).status == "in_progress"


def test_exception_unique_key_race_returns_existing_record(
    ffl_db, crop_allocation, users, monkeypatch
):
    first = report_exception(
        ffl_db,
        crop_allocation.id,
        "Leaf damage",
        "high",
        users.manager.id,
        users.lead.id,
        "2026-07-10T08:00:00+00:00",
        "device-7:43",
    )
    monkeypatch.setattr(repository, "get_exception_by_idempotency_key", lambda conn, key: None)

    replay = report_exception(
        ffl_db,
        crop_allocation.id,
        "Leaf damage",
        "high",
        users.manager.id,
        users.lead.id,
        "2026-07-10T08:00:00+00:00",
        "device-7:43",
    )

    assert replay.id == first.id
