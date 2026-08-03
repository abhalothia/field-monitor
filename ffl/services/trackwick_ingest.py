"""Manager-triggered ingestion for the verified TrackWick task stream.

This is intentionally a read-only, aggregate-context lane.  A successful
manager refresh publishes safe normalized records for metrics only; it never
creates a farm, changes a land record, completes field work, recommends a
pesticide, or writes back to TrackWick.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
import json
import sqlite3
import threading
from typing import Callable, Optional

import httpx

from ffl.domain.models import SourceRegistry, SourceRun
from ffl.integrations.trackolap.trackwick import (
    MAPPING_VERSION,
    TrackwickApiConfig,
    TrackwickConfigurationError,
    TrackwickSourceFailure,
    normalise_trackwick,
    refresh_trackwick,
)
from ffl.persistence import repository
from ffl.services.sources import environment_credential_resolver


SOURCE_KEY = "trackwick-fortune-paddy"
_REFRESH_LOCK = threading.RLock()


@dataclass(frozen=True)
class TrackwickRefreshResult:
    source: SourceRegistry
    source_run: SourceRun
    state: str
    reason_code: Optional[str]
    valid_count: int
    quarantined_count: int


def refresh_live_trackwick(
    conn,
    owner_id: str,
    config: Optional[TrackwickApiConfig] = None,
    credential_resolver: Optional[Callable[[str], Optional[str]]] = None,
    transport: Optional[httpx.BaseTransport] = None,
    as_of: Optional[datetime] = None,
) -> TrackwickRefreshResult:
    """Fetch and store a safe, directly usable read model for manager metrics."""
    _require_owner(conn, owner_id)
    try:
        resolved_config = config if config is not None else TrackwickApiConfig.from_environment()
    except TrackwickConfigurationError:
        resolved_config = None
        configuration_error = "configuration_invalid"
    else:
        configuration_error = None
    source = _ensure_source(conn, owner_id, resolved_config)
    if resolved_config is None:
        run = repository.create_source_run(
            conn,
            source.id,
            coverage={"input": "trackwick_live_api"},
            mapping_version=MAPPING_VERSION if configuration_error else "not_configured",
            status="unavailable",
            fetched_at=_now(),
            error_summary=configuration_error or "configuration_unavailable",
        )
        return TrackwickRefreshResult(source, run, "unavailable", run.error_summary, 0, 0)

    try:
        sync_scope, created_since, created_until = _sync_window(
            conn, source, resolved_config, as_of=as_of
        )
        fetched = refresh_trackwick(
            resolved_config,
            credential_resolver or environment_credential_resolver,
            as_of=as_of,
            created_since=created_since,
            created_until=created_until,
            transport=transport,
        )
    except TrackwickSourceFailure as error:
        run = repository.create_source_run(
            conn,
            source.id,
            coverage={"input": "trackwick_live_api"},
            mapping_version=MAPPING_VERSION,
            status="unavailable" if str(error) in {"configuration_unavailable", "credentials_unavailable"} else "failed",
            fetched_at=_now(),
            error_summary=_safe_reason_code(str(error)),
        )
        return TrackwickRefreshResult(source, run, run.status, run.error_summary, 0, 0)

    normalised = normalise_trackwick(fetched, resolved_config, as_of=as_of)
    with _REFRESH_LOCK:
        try:
            conn.execute("BEGIN IMMEDIATE")
            run = repository.create_source_run(
                conn,
                source.id,
                coverage={
                    "input": "trackwick_live_api",
                    "sync_scope": sync_scope,
                    "task_pages": fetched.task_pages,
                    "task_rows": len(fetched.tasks),
                    "attendance_rows": len(fetched.attendance),
                    **(
                        {
                            "create_date_begin": created_since.isoformat(),
                            "create_date_end": created_until.isoformat(),
                        }
                        if created_since is not None and created_until is not None
                        else {}
                    ),
                },
                mapping_version=MAPPING_VERSION,
                cursor=json.dumps({"reporting_date": _as_of_date(as_of, resolved_config.reporting_timezone)}, separators=(",", ":")),
                status="quarantined" if normalised.quarantined_rows else "succeeded",
                fetched_at=_now(),
                rows_received=fetched.rows_received,
                # A single Farmer Visit expands into several safe aggregate
                # records (visit, issue and pesticide cues). Source-run counts
                # remain counts of provider rows, not derived records.
                rows_accepted=max(0, fetched.rows_received - normalised.quarantined_rows),
                error_summary="row_validation_failed" if normalised.quarantined_rows else None,
                commit=False,
            )
            repository.create_trackolap_records(
                conn,
                source.id,
                run.id,
                None,
                [
                    (
                        record.feed,
                        record.source_id,
                        record.source_updated_at,
                        record.tenant_id,
                        dict(record.values),
                    )
                    for record in normalised.records
                ],
                # A manager explicitly triggering this read-only refresh
                # accepts it as aggregate source context. It is still not an
                # accepted decision, farm fact, or completed action.
                status="published",
                commit=False,
            )
            conn.commit()
        except Exception:
            conn.rollback()
            failed = repository.create_source_run(
                conn,
                source.id,
                coverage={"input": "trackwick_live_api"},
                mapping_version=MAPPING_VERSION,
                status="failed",
                fetched_at=_now(),
                error_summary="persistence_failed",
            )
            return TrackwickRefreshResult(source, failed, "failed", "persistence_failed", 0, 0)
    return TrackwickRefreshResult(
        source,
        run,
        "quarantined" if normalised.quarantined_rows else "succeeded",
        "row_validation_failed" if normalised.quarantined_rows else None,
        len(normalised.records),
        normalised.quarantined_rows,
    )


def _ensure_source(conn, owner_id: str, config: Optional[TrackwickApiConfig]) -> SourceRegistry:
    existing = repository.get_source_registry_by_key(conn, SOURCE_KEY)
    if existing is not None:
        if existing.source_type != "trackwick" or existing.authority_level != "partner":
            raise ValueError("TrackWick source key is already registered with incompatible authority")
        return existing
    return repository.create_source_registry(
        conn,
        source_key=SOURCE_KEY,
        display_name="Fortune paddy visits (TrackWick)",
        source_type="trackwick",
        purpose="Fortune paddy visit, crop-observation, and field-activity context",
        authority_level="partner",
        owner_id=owner_id,
        credentials_reference=config.api_key_reference if config else None,
        endpoint="https://app.trackolap.com/cust/1/api",
        permitted_data_classes=[
            "officer_activity",
            "farm_task_context",
            "visit_observation",
            "issue_observation",
            "pesticide_event",
        ],
        schema_version="trackwick-v1",
        mapping_version=MAPPING_VERSION if config else "not_configured",
        default_coverage={"tenant": config.tenant_id if config else "not_configured"},
        freshness_target_hours=24,
        license_notes="Read-only TrackWick API; raw task payload, names, mobile numbers, photos, and GPS are never retained.",
        enabled=config is not None,
    )


def _require_owner(conn, owner_id: str) -> None:
    owner = conn.execute("SELECT role FROM people WHERE id = ?", (owner_id,)).fetchone()
    if owner is None:
        raise ValueError("refresh owner does not exist")
    if owner["role"] not in {"farm_manager", "operations_lead", "agronomist"}:
        raise ValueError("refresh owner must be an authorised Fortune operations lead")


def _sync_window(
    conn, source: SourceRegistry, config: TrackwickApiConfig, *, as_of: Optional[datetime]
) -> tuple[str, Optional[datetime], Optional[datetime]]:
    """Run one baseline once; later pulls overlap a small India-time creation window.

    Coverage needs historical farmer tasks.  A first source run therefore reads
    the approved Farmer Visit history.  Once that baseline exists, TrackWick's
    verified epoch-millisecond creation filters keep routine COO refreshes
    short, while the two-day overlap avoids an India-midnight boundary gap.
    """
    baseline = conn.execute(
        """SELECT 1 FROM trackolap_records
           WHERE source_id = ? AND feed = 'farmer_tasks' AND status = 'published'
           LIMIT 1""",
        (source.id,),
    ).fetchone()
    if baseline is not None:
        from zoneinfo import ZoneInfo

        current = (as_of or datetime.now(timezone.utc)).astimezone(
            ZoneInfo(config.reporting_timezone)
        )
        start_day = current.date() - timedelta(days=config.delta_lookback_days - 1)
        start = datetime.combine(start_day, time.min, tzinfo=current.tzinfo)
        end = datetime.combine(current.date() + timedelta(days=1), time.min, tzinfo=current.tzinfo)
        return "delta", start, end
    return "historical_backfill", None, None


def _as_of_date(value: Optional[datetime], timezone_name: str) -> str:
    from zoneinfo import ZoneInfo

    return (value or datetime.now(timezone.utc)).astimezone(ZoneInfo(timezone_name)).date().isoformat()


def _safe_reason_code(value: str) -> str:
    return value if value and value.replace("_", "").isalnum() and len(value) <= 64 else "provider_response_invalid"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
