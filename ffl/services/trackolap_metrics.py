"""Aggregate, decision-safe read model for normalized TrackOlap records."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any, Iterable, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

from ffl.integrations.trackolap.contracts import TrackolapRecord
from ffl.persistence import repository
from ffl.services import procurement_capture
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
    procurement_snapshot: Optional[Mapping[str, Any]] = None,
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
    task_farmers = {
        task["task_id"]: task["farmer_code"]
        for task in active_tasks
        if task.get("task_id") and task.get("farmer_code")
        and task.get("kit_status", "").lower() in {"taken", "received"}
    }
    taken_farmer_codes = set(task_farmers.values())
    valid_visits = [visit for visit in visits if _valid_visit(visit, now)]
    coverage = _coverage(taken_farmer_codes, task_farmers, valid_visits, now, recent_days)
    issue_summary = _issue_summary(issues, now, issue_window_days)
    pesticide_summary = _pesticide_summary(pesticides)
    warning_codes = []
    if issue_summary["observation_count"] < 2:
        warning_codes.append("low_observation_confidence")

    return {
        "coverage": coverage,
        "visits": _visit_summary(valid_visits, officers, now),
        "issues": issue_summary,
        "pesticides": pesticide_summary,
        "outcomes": _operating_outcomes(
            coverage, pesticide_summary, issue_summary, procurement_snapshot
        ),
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
        return dashboard_metrics(
            (),
            now,
            reporting_timezone=reporting_timezone,
            procurement_snapshot=procurement_capture.latest_published_procurement_capture(conn),
        )
    records = repository.list_trackolap_records(conn, source.id, statuses=("published",))
    return dashboard_metrics(
        records,
        now,
        reporting_timezone=reporting_timezone,
        procurement_snapshot=procurement_capture.latest_published_procurement_capture(conn),
    )


def _coverage(
    farmer_codes: set[str], task_farmers: Mapping[str, str], visits: Iterable[Mapping[str, str]],
    now: datetime, recent_days: int,
) -> dict[str, int]:
    """Compute coverage over farmers, never over repeat visit tasks.

    A TrackWick task is a visit event. A COO needs the coverage denominator to
    be the distinct kit-taking farmer population, even when the same farmer has
    several tasks over the season.
    """
    most_recent_by_farmer: dict[str, datetime] = {}
    for visit in visits:
        task_id = visit.get("task_id")
        farmer_code = task_farmers.get(task_id or "")
        if farmer_code not in farmer_codes:
            continue
        performed_at = _optional_timestamp(visit.get("performed_at"))
        if performed_at is None:
            continue
        prior = most_recent_by_farmer.get(farmer_code)
        if prior is None or performed_at > prior:
            most_recent_by_farmer[farmer_code] = performed_at
    visited_ids = set(most_recent_by_farmer)
    cutoff = now - timedelta(days=recent_days)
    recent_ids = {
        farmer_code for farmer_code, seen_at in most_recent_by_farmer.items()
        if cutoff <= seen_at <= now
    }
    return {
        "taken_kit": len(farmer_codes),
        "visited": len(visited_ids),
        "recent": len(recent_ids),
        "overdue": len(farmer_codes - recent_ids),
        "never_visited": len(farmer_codes - visited_ids),
    }


def _visit_summary(visits: Iterable[Mapping[str, str]], officers: Iterable[Mapping[str, str]], now: datetime) -> dict:
    on_day = []
    for visit in visits:
        performed_at = _optional_timestamp(visit.get("performed_at"))
        if performed_at is not None and performed_at.astimezone(now.tzinfo).date() == now.date():
            on_day.append(visit)
    filing_officers = {visit.get("filing_officer_id") for visit in on_day if visit.get("filing_officer_id")}
    active_officers = set()
    for officer in officers:
        officer_id = officer.get("officer_id")
        effective_from = _optional_timestamp(officer.get("effective_from"))
        if (
            officer_id
            and effective_from is not None
            and effective_from.astimezone(now.tzinfo).date() == now.date()
            and officer.get("active_status", "active").lower() == "active"
        ):
            active_officers.add(officer_id)
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


def _operating_outcomes(
    coverage: Mapping[str, int],
    pesticides: Mapping[str, int],
    issues: Mapping[str, Any],
    procurement_snapshot: Optional[Mapping[str, Any]],
) -> dict:
    """Name the three useful management truths without overstating the source.

    Each outcome carries its own denominator and limitation so callers cannot
    quietly relabel activity data as purchase share, EU compliance, or a crop
    diagnosis.  Procurement, laboratory, and reviewed agronomy evidence are
    separate source lanes and must be connected before those claims are shown.
    """
    eligible_farmers = int(coverage.get("taken_kit", 0))
    recently_reached = int(coverage.get("recent", 0))
    share_percent = (
        round(100 * recently_reached / eligible_farmers, 1)
        if eligible_farmers
        else None
    )
    issue_rows = issues.get("by_issue", [])
    lead_issue = issue_rows[0] if isinstance(issue_rows, list) and issue_rows else None
    purchase_capture = _purchase_capture_outcome(procurement_snapshot)
    return {
        "farmer_reach": {
            "recently_reached": recently_reached,
            "eligible_farmers": eligible_farmers,
            "share_percent": share_percent,
            "window_days": 14,
            "basis": "distinct kit-taking farmer codes with a valid visit in the reporting window",
            "limitation": "contact coverage, not crop purchase share",
        },
        "chemical_record": {
            "reported_events": int(pesticides.get("event_count", 0)),
            "review_cues": int(pesticides.get("off_kit_review_cues", 0)),
            "basis": "reported pesticide use or recommendation events",
            "limitation": "reported events, not a compliance or export-readiness verdict",
        },
        "crop_signals": {
            "observations": int(issues.get("observation_count", 0)),
            "window_days": int(issues.get("window_days", 7)),
            "lead_issue": lead_issue,
            "basis": "dated field observations",
            "limitation": "detection signal, not a diagnosis or prevalence rate",
        },
        "purchase_share": purchase_capture,
    }


def _purchase_capture_outcome(snapshot: Optional[Mapping[str, Any]]) -> dict:
    """Expose only a published aggregate capture ratio, never source rows."""
    capture = snapshot.get("capture") if isinstance(snapshot, Mapping) else None
    if not isinstance(capture, Mapping):
        return {
            "availability": "not_connected",
            "basis": "not available until Fortune publishes a one-season purchase capture snapshot",
            "limitation": "farmer reach is not crop purchase share",
        }
    return {
        "availability": "available",
        "season_code": capture.get("season_code"),
        "snapshot_date": capture.get("snapshot_date"),
        "reported_farmers": int(capture.get("reported_farmers", 0)),
        "reported_harvest_qtl": float(capture.get("reported_harvest_qtl", 0)),
        "fortune_purchase_qtl": float(capture.get("fortune_purchase_qtl", 0)),
        "share_percent": float(capture.get("purchase_share_percent", 0)),
        "basis": "Fortune purchase quantity divided by linked growers' reported harvest quantity",
        "limitation": "reported-harvest coverage, not regional market share",
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
