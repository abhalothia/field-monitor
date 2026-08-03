from __future__ import annotations

from ffl.integrations.trackolap.contracts import TrackolapRecord
from ffl.services.trackolap_metrics import dashboard_metrics


def _record(feed: str, source_id: str, values: dict[str, str]) -> TrackolapRecord:
    return TrackolapRecord(
        feed=feed,
        source_id=source_id,
        source_updated_at="2026-08-03T12:00:00+05:30",
        tenant_id="fortune-paddy",
        values=values,
    )


RECORDS = [
    _record("farmer_tasks", "task-1", {"task_id": "task-1", "kit_status": "taken", "task_status": "active"}),
    _record("farmer_tasks", "task-2", {"task_id": "task-2", "kit_status": "taken", "task_status": "active"}),
    _record("farmer_tasks", "task-3", {"task_id": "task-3", "kit_status": "taken", "task_status": "active"}),
    _record(
        "visits",
        "visit-1",
        {
            "visit_id": "visit-1",
            "task_id": "task-1",
            "filing_officer_id": "officer-1",
            "performed_at": "2026-08-03T09:00:00+05:30",
            "submitted_at": "2026-08-03T09:05:00+05:30",
            "visit_status": "complete",
        },
    ),
    _record(
        "visits",
        "visit-2",
        {
            "visit_id": "visit-2",
            "task_id": "task-2",
            "filing_officer_id": "officer-2",
            "performed_at": "2026-07-10T09:00:00+05:30",
            "submitted_at": "2026-07-10T09:05:00+05:30",
            "visit_status": "complete",
        },
    ),
]


def test_coverage_marks_never_visited_and_stale_visits_overdue():
    snapshot = dashboard_metrics(RECORDS, as_of="2026-08-03T18:00:00+05:30")

    assert snapshot["coverage"] == {
        "taken_kit": 3,
        "visited": 2,
        "recent": 1,
        "overdue": 2,
        "never_visited": 1,
    }
    assert snapshot["warnings"] == ["low_observation_confidence"]


def test_issue_counts_are_windowed_observations_not_claimed_open_outbreaks():
    records = RECORDS + [
        _record(
            "issue_observations",
            "issue-1",
            {
                "observation_id": "issue-1",
                "visit_id": "visit-1",
                "task_id": "task-1",
                "issue_code": "stem-borer",
                "severity": "high",
                "observed_at": "2026-08-03T09:00:00+05:30",
            },
        ),
        _record(
            "issue_observations",
            "issue-2",
            {
                "observation_id": "issue-2",
                "visit_id": "visit-1",
                "task_id": "task-1",
                "issue_code": "stem-borer",
                "severity": "high",
                "observed_at": "2026-07-20T09:00:00+05:30",
            },
        ),
    ]

    snapshot = dashboard_metrics(records, as_of="2026-08-03T18:00:00+05:30")

    assert snapshot["issues"] == {
        "window_days": 7,
        "observation_count": 1,
        "by_issue": [{"issue_code": "stem-borer", "count": 1, "highest_severity": "high"}],
    }
