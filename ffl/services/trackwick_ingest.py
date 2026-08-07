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
    PRIVATE_EVIDENCE_MAPPING_VERSION,
    TrackwickApiConfig,
    TrackwickConfigurationError,
    TrackwickSourceFailure,
    normalise_trackwick_basics,
    normalise_trackwick_private_evidence,
    normalise_trackwick,
    refresh_trackwick,
)
from ffl.persistence import repository
from ffl.services.sources import environment_credential_resolver


SOURCE_KEY = "trackwick-fortune-paddy"
LIVE_MAPPING_VERSION = "trackwick-live-v4"
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
            mapping_version=LIVE_MAPPING_VERSION if configuration_error else "not_configured",
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
            mapping_version=LIVE_MAPPING_VERSION,
            status="unavailable" if str(error) in {"configuration_unavailable", "credentials_unavailable"} else "failed",
            fetched_at=_now(),
            error_summary=_safe_reason_code(str(error)),
        )
        return TrackwickRefreshResult(source, run, run.status, run.error_summary, 0, 0)

    normalised = normalise_trackwick(fetched, resolved_config, as_of=as_of)
    basics = normalise_trackwick_basics(fetched, resolved_config, as_of=as_of)
    private_evidence = normalise_trackwick_private_evidence(fetched, resolved_config, as_of=as_of)
    all_records = (*normalised.records, *basics.records)
    quarantined_rows = (
        normalised.quarantined_rows
        + basics.quarantined_rows
        + private_evidence.quarantined_rows
    )
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
                    "customer_pages": fetched.customer_pages,
                    "customer_rows": len(fetched.customers),
                    "attendance_rows": len(fetched.attendance),
                    "private_evidence_rows": len(private_evidence.records),
                    **(
                        {
                            "create_date_begin": created_since.isoformat(),
                            "create_date_end": created_until.isoformat(),
                        }
                        if created_since is not None and created_until is not None
                        else {}
                    ),
                },
                mapping_version=LIVE_MAPPING_VERSION,
                cursor=json.dumps({"reporting_date": _as_of_date(as_of, resolved_config.reporting_timezone)}, separators=(",", ":")),
                status="quarantined" if quarantined_rows else "succeeded",
                fetched_at=_now(),
                rows_received=fetched.rows_received,
                # A single Farmer Visit expands into several safe aggregate
                # records (visit, issue and pesticide cues). Source-run counts
                # remain counts of provider rows, not derived records.
                rows_accepted=max(0, fetched.rows_received - quarantined_rows),
                error_summary="row_validation_failed" if quarantined_rows else None,
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
                    for record in all_records
                ],
                # A manager explicitly triggering this read-only refresh
                # accepts it as aggregate source context. It is still not an
                # accepted decision, farm fact, or completed action.
                status="published",
                commit=False,
            )
            repository.upsert_trackwick_private_records(
                conn,
                source.id,
                run.id,
                private_evidence.records,
                PRIVATE_EVIDENCE_MAPPING_VERSION,
                commit=False,
            )
            repository.reconcile_trackwick_task_plot_links(
                conn,
                source.id,
                run.id,
                PRIVATE_EVIDENCE_MAPPING_VERSION,
                references_enabled=(
                    resolved_config.task_plot_reference_form_key is not None
                ),
                commit=False,
            )
            conn.commit()
        except Exception as error:
            conn.rollback()
            reason_code = _safe_reason_code(
                "persistence_" + error.__class__.__name__.lower()
            )
            failed = repository.create_source_run(
                conn,
                source.id,
                coverage={"input": "trackwick_live_api"},
                mapping_version=LIVE_MAPPING_VERSION,
                status="failed",
                fetched_at=_now(),
                error_summary=reason_code,
            )
            return TrackwickRefreshResult(source, failed, "failed", reason_code, 0, 0)
    return TrackwickRefreshResult(
        source,
        run,
        "quarantined" if quarantined_rows else "succeeded",
        "row_validation_failed" if quarantined_rows else None,
        len(all_records) + len(private_evidence.records),
        quarantined_rows,
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
        purpose="Fortune farmer, farm-candidate, crop-observation, and field-activity context",
        authority_level="partner",
        owner_id=owner_id,
        credentials_reference=config.api_key_reference if config else None,
        endpoint="https://app.trackolap.com/cust/1/api",
        permitted_data_classes=[
            "officer_activity",
            "field_worker_identity_basics",
            "farmer_identity_basics",
            "farm_candidate_context",
            "farm_task_context",
            "crop_context",
            "visit_observation",
            "issue_observation",
            "pesticide_event",
            "private_contact_vault",
            "private_spatial_evidence",
            "private_media_reference",
        ],
        schema_version="trackwick-v3",
        mapping_version=LIVE_MAPPING_VERSION if config else "not_configured",
        default_coverage={"tenant": config.tenant_id if config else "not_configured"},
        freshness_target_hours=24,
        license_notes="Read-only TrackWick API. Aggregate basics are published separately; reviewed mobile, exact GPS and remote crop/plot-photo references stay in private source tables. Aadhaar, signatures, comments and raw form payloads are never retained.",
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
        # The original historical import can predate the typed private task
        # table.  In that state its child evidence (visits, locations and
        # registrations) is present but cannot be joined safely to people or
        # Farm Truth.  Repair it with one complete, read-only provider pull;
        # do not manufacture parent tasks from the child rows.  Once the
        # provider-backed graph is complete, normal small delta pulls resume.
        if _private_graph_requires_repair(conn, source.id):
            return "integrity_repair_backfill", None, None
        from zoneinfo import ZoneInfo

        current = (as_of or datetime.now(timezone.utc)).astimezone(
            ZoneInfo(config.reporting_timezone)
        )
        start_day = current.date() - timedelta(days=config.delta_lookback_days - 1)
        start = datetime.combine(start_day, time.min, tzinfo=current.tzinfo)
        end = datetime.combine(current.date() + timedelta(days=1), time.min, tzinfo=current.tzinfo)
        return "delta", start, end
    return "historical_backfill", None, None


def _private_graph_requires_repair(conn, source_id: str) -> bool:
    """Whether retained TrackWick child evidence is missing its typed task.

    This is deliberately a bounded integrity check, not a freshness heuristic.
    A missing parent means a source registration or visit cannot be combined
    with its reported farmer, worker, or review workflow without guessing.
    """
    for child_table, child_key in (
        ("trackwick_visits", "task_id"),
        ("trackwick_registrations", "task_id"),
    ):
        row = conn.execute(
            """SELECT 1
               FROM {child} AS child
               LEFT JOIN trackwick_tasks AS task ON task.id = child.{key}
               WHERE child.source_id = ?
                 AND child.data_quality_status = 'valid'
                 AND task.id IS NULL
               LIMIT 1""".format(child=child_table, key=child_key),
            (source_id,),
        ).fetchone()
        if row is not None:
            return True
    return False


def _as_of_date(value: Optional[datetime], timezone_name: str) -> str:
    from zoneinfo import ZoneInfo

    return (value or datetime.now(timezone.utc)).astimezone(ZoneInfo(timezone_name)).date().isoformat()


def _safe_reason_code(value: str) -> str:
    return value if value and value.replace("_", "").isalnum() and len(value) <= 64 else "provider_response_invalid"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
