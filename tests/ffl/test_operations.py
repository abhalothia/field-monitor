import pytest

from ffl.services.operations import (
    create_work_item,
    list_audit_events,
    report_exception,
    transition_work_item,
)


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
