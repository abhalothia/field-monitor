"""Aggregate, decision-safe read model for normalized TrackOlap records."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any, Iterable, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

from ffl.integrations.trackolap.contracts import TrackolapRecord
from ffl.persistence import repository
from ffl.services.trackolap_ingest import SOURCE_KEY


DEFAULT_REPORTING_TIMEZONE = "Asia/Kolkata"
_INVALID_VISIT_STATUSES = {"cancelled", "invalid", "rejected"}
_SEVERITY_ORDER = {"low": 0, "moderate": 1, "high": 2, "critical": 3}


def dashboard_metrics(
    records: Sequence[Any],
    as_of: str | datetime,
    recent_days: int = 14,
    issue_window_days: int = 7,
    reporting_timezone: str = DEFAULT_REPORTING_TIMEZONE,
) -> dict:
    """Derive dashboard-equivalent aggregates without interpreting them as advice.

    The metrics have intentionally narrow semantics: detected issues are dated
    observations, a low observation count lowers confidence, and off-kit use
    is a human review cue rather than an agronomic recommendation.
    """
    if recent_days <= 0 or issue_window_days <= 0:
        raise ValueError("reporting windows must be positive")
    timezone = ZoneInfo(reporting_timezone)
    now = _as_datetime(as_of).astimezone(timezone)
    current = _current_revisions(records)
    tasks = [_values(record) for record in current if _feed(record) == "farmer_tasks"]
    visits = [_values(record) for record in current if _feed(record) == "visits"]
    issues = [_values(record) for record in current if _feed(record) == "issue_observations"]
    pesticides = [_values(record) for record in current if _feed(record) == "pesticide_events"]
    officers = [_values(record) for record in current if _feed(record) == "officers"]

    active_tasks = [
        task
        for task in tasks
        if task.get("task_id") and task.get("task_status", "active").lower() not in {"cancelled", "inactive"}
    ]
    taken_task_ids = {
        task["task_id"]
        for task in active_tasks
        if task.get("kit_status", "").lower() in {"taken", "received"}
    }
    valid_visits = [visit for visit in visits if _valid_visit(visit, now)]
    coverage = _coverage(taken_task_ids, valid_visits, now, recent_days)
    issue_summary = _issue_summary(issues, now, issue_window_days)
    warning_codes = []
    if issue_summary["observation_count"] < 2:
        warning_codes.append("low_observation_confidence")

    return {
        "coverage": coverage,
        "visits": _visit_summary(valid_visits, officers, now),
        "issues": issue_summary,
        "pesticides": _pesticide_summary(pesticides),
        "freshness": _freshness(current, now),
        "warnings": warning_codes,
    }


def dashboard_metrics_for_source(
    conn,
    source_key: str = SOURCE_KEY,
    as_of: Optional[str | datetime] = None,
    reporting_timezone: str = DEFAULT_REPORTING_TIMEZONE,
) -> dict:
    """Read published source context only; draft import rows never affect COO metrics."""
    source = repository.get_source_registry_by_key(conn, source_key)
    now = as_of or datetime.now(ZoneInfo(reporting_timezone))
    if source is None:
        return dashboard_metrics((), now, reporting_timezone=reporting_timezone)
    records = repository.list_trackolap_records(conn, source.id, statuses=("published",))
    return dashboard_metrics(records, now, reporting_timezone=reporting_timezone)


def _coverage(
    task_ids: set[str], visits: Iterable[Mapping[str, str]], now: datetime, recent_days: int
) -> dict[str, int]:
    most_recent_by_task: dict[str, datetime] = {}
    for visit in visits:
        task_id = visit.get("task_id")
        if task_id not in task_ids:
            continue
        performed_at = _optional_timestamp(visit.get("performed_at"))
        if performed_at is None:
            continue
        prior = most_recent_by_task.get(task_id)
        if prior is None or performed_at > prior:
            most_recent_by_task[task_id] = performed_at
    visited_ids = set(most_recent_by_task)
    cutoff = now - timedelta(days=recent_days)
    recent_ids = {task_id for task_id, seen_at in most_recent_by_task.items() if cutoff <= seen_at <= now}
    return {
        "taken_kit": len(task_ids),
        "visited": len(visited_ids),
        "recent": len(recent_ids),
        "overdue": len(task_ids - recent_ids),
        "never_visited": len(task_ids - visited_ids),
    }


def _visit_summary(visits: Iterable[Mapping[str, str]], officers: Iterable[Mapping[str, str]], now: datetime) -> dict:
    on_day = []
    for visit in visits:
        performed_at = _optional_timestamp(visit.get("performed_at"))
        if performed_at is not None and performed_at.astimezone(now.tzinfo).date() == now.date():
            on_day.append(visit)
    filing_officers = {visit.get("filing_officer_id") for visit in on_day if visit.get("filing_officer_id")}
    active_officers = {
        officer.get("officer_id")
        for officer in officers
        if officer.get("officer_id") and officer.get("active_status", "active").lower() == "active"
    }
    return {
        "filed_on_reporting_day": len(on_day),
        "filing_officers": len(filing_officers),
        "active_officers": len(active_officers),
        "active_officers_without_filed_visit": len(active_officers - filing_officers),
    }


def _issue_summary(issues: Iterable[Mapping[str, str]], now: datetime, window_days: int) -> dict:
    cutoff = now - timedelta(days=window_days)
    counts: Counter[str] = Counter()
    severities: dict[str, str] = {}
    total = 0
    for issue in issues:
        observed_at = _optional_timestamp(issue.get("observed_at"))
        issue_code = issue.get("issue_code")
        if observed_at is None or not issue_code or not cutoff <= observed_at <= now:
            continue
        total += 1
        counts[issue_code] += 1
        severity = issue.get("severity", "unknown").lower()
        previous = severities.get(issue_code, "unknown")
        if _SEVERITY_ORDER.get(severity, -1) >= _SEVERITY_ORDER.get(previous, -1):
            severities[issue_code] = severity
    return {
        "window_days": window_days,
        "observation_count": total,
        "by_issue": [
            {"issue_code": code, "count": count, "highest_severity": severities[code]}
            for code, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        ],
    }


def _pesticide_summary(events: Iterable[Mapping[str, str]]) -> dict:
    all_events = list(events)
    off_kit = sum(
        event.get("event_kind", "").lower() in {"off_kit", "off-kit", "non_kit", "non-kit"}
        for event in all_events
    )
    timing_context = sum("transplanted_at" in event for event in all_events)
    return {
        "event_count": len(all_events),
        "off_kit_review_cues": off_kit,
        "events_with_timing_context": timing_context,
        "policy": "review cue only; not an application recommendation or compliance verdict",
    }


def _freshness(records: Sequence[Any], now: datetime) -> dict:
    timestamps = [_optional_timestamp(getattr(record, "source_updated_at", None)) for record in records]
    valid_timestamps = [timestamp for timestamp in timestamps if timestamp is not None]
    if not valid_timestamps:
        return {"status": "unavailable", "latest_source_updated_at": None, "age_hours": None}
    latest = max(valid_timestamps)
    age_hours = max(0.0, (now - latest.astimezone(now.tzinfo)).total_seconds() / 3600)
    return {
        "status": "available",
        "latest_source_updated_at": latest.isoformat(),
        "age_hours": round(age_hours, 2),
    }


def _current_revisions(records: Sequence[Any]) -> list[Any]:
    latest: dict[tuple[str, str], Any] = {}
    for record in records:
        key = (_feed(record), _source_identifier(record))
        current = latest.get(key)
        if current is None or _as_datetime(record.source_updated_at) >= _as_datetime(current.source_updated_at):
            latest[key] = record
    return list(latest.values())


def _valid_visit(visit: Mapping[str, str], now: datetime) -> bool:
    performed_at = _optional_timestamp(visit.get("performed_at"))
    return (
        performed_at is not None
        and performed_at <= now
        and visit.get("visit_status", "").lower() not in _INVALID_VISIT_STATUSES
    )


def _feed(record: Any) -> str:
    return str(getattr(record, "feed"))


def _source_identifier(record: Any) -> str:
    return str(getattr(record, "source_identifier", getattr(record, "source_id")))


def _values(record: Any) -> Mapping[str, str]:
    values = getattr(record, "values")
    return values if isinstance(values, Mapping) else {}


def _as_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("as_of and source timestamps must be ISO-8601") from exc
    else:
        raise ValueError("as_of and source timestamps must be ISO-8601")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("as_of and source timestamps must include a timezone offset")
    return parsed


def _optional_timestamp(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return _as_datetime(value)
    except ValueError:
        return None
