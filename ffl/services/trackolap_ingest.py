"""Private CSV lifecycle for the read-only TrackOlap/TrackWick source lane."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import sqlite3
import threading
from typing import Any, Callable, Optional

import httpx

from ffl.domain.models import ImportBatch, SourceRegistry, SourceRun
from ffl.integrations.trackolap.api import (
    LiveRefreshResult,
    TrackolapApiConfig,
    TrackolapConfigurationError,
    refresh_trackolap,
)
from ffl.integrations.trackolap.contracts import ParsedBundle
from ffl.integrations.trackolap.csv_ingest import parse_csv_bundle
from ffl.integrations.trackolap.mapping import MappingManifest, normalise_row
from ffl.persistence import repository
from ffl.services.evidence import retain_evidence
from ffl.services.evidence_store import EvidenceStore
from ffl.services.sources import environment_credential_resolver


SOURCE_KEY = "trackolap-fortune-paddy"
IMPORT_PURPOSE = "trackolap_csv_bundle"
_INGEST_LOCK = threading.RLock()


@dataclass(frozen=True)
class TrackolapIngestResult:
    source: SourceRegistry
    batch: ImportBatch
    source_run: Optional[SourceRun]
    valid_count: int
    quarantined_count: int
    idempotent: bool


@dataclass(frozen=True)
class TrackolapRefreshIngestResult:
    source: SourceRegistry
    source_run: SourceRun
    state: str
    reason_code: Optional[str]
    valid_count: int
    quarantined_count: int


def ingest_csv_bundle(
    conn,
    content: bytes,
    manifest: MappingManifest,
    owner_id: str,
    original_filename: str = "trackolap-export.zip",
    evidence_directory: Optional[str] = None,
    evidence_store: Optional[EvidenceStore] = None,
) -> TrackolapIngestResult:
    """Retain one approved export and create only normalized, source-backed rows.

    Parsing occurs before retention so unsupported feed configuration fails
    before an operator persists a bundle.  Parsed raw CSV cells are retained
    solely in the private evidence artifact; the database receives only
    allowed normalized values and safe row receipts.
    """
    _require_owner(conn, owner_id)
    manifest.requires_all_feeds()
    parsed = parse_csv_bundle(content, manifest)
    if any(error.get("code") == "unsupported_source_header" for error in parsed.errors):
        raise ValueError("CSV bundle contains unsupported source headers")
    source = _ensure_source(conn, owner_id, manifest.version)
    artifact = retain_evidence(
        conn,
        content,
        "application/zip",
        original_filename=original_filename,
        created_by_person_id=owner_id,
        directory=evidence_directory,
        store=evidence_store,
    )

    with _INGEST_LOCK:
        existing = repository.get_import_batch_by_content_hash(conn, artifact.content_hash)
        if existing is not None:
            if existing.purpose != IMPORT_PURPOSE:
                raise ValueError("content is already registered under a different import purpose")
            return _result_for_existing(conn, source, existing)
        try:
            conn.execute("BEGIN IMMEDIATE")
            existing = repository.get_import_batch_by_content_hash(conn, artifact.content_hash)
            if existing is not None:
                conn.rollback()
                if existing.purpose != IMPORT_PURPOSE:
                    raise ValueError("content is already registered under a different import purpose")
                return _result_for_existing(conn, source, existing)

            profile = _profile(parsed, manifest.version)
            valid_count = sum(row.record is not None for row in parsed.rows)
            quarantined_count = len(parsed.errors) + sum(bool(row.errors) for row in parsed.rows)
            run = repository.create_source_run(
                conn,
                source.id,
                coverage={"input": "csv_bundle", "feeds": profile["feeds"]},
                mapping_version=manifest.version,
                status="quarantined" if quarantined_count else "succeeded",
                fetched_at=_now(),
                rows_received=len(parsed.rows) + len(parsed.errors),
                rows_accepted=valid_count,
                error_summary="row_validation_failed" if quarantined_count else None,
                commit=False,
            )
            batch = repository.create_import_batch(
                conn,
                IMPORT_PURPOSE,
                artifact.content_hash,
                artifact.id,
                manifest.version,
                owner_id,
                profile,
                status="profiled",
                source_id=source.id,
                commit=False,
            )
            _store_rows(conn, batch.id, source.id, run.id, parsed)
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            established = repository.get_import_batch_by_content_hash(conn, artifact.content_hash)
            if established is None:
                raise
            if established.purpose != IMPORT_PURPOSE:
                raise ValueError("content is already registered under a different import purpose")
            return _result_for_existing(conn, source, established)
        except Exception:
            conn.rollback()
            raise

    return TrackolapIngestResult(
        source=source,
        batch=batch,
        source_run=run,
        valid_count=valid_count,
        quarantined_count=quarantined_count,
        idempotent=False,
    )


def review_trackolap_import(conn, import_batch_id: str, reviewer_id: str) -> ImportBatch:
    """Record a human review before source context is eligible for metrics."""
    batch = _trackolap_batch(conn, import_batch_id)
    if conn.execute("SELECT 1 FROM people WHERE id = ?", (reviewer_id,)).fetchone() is None:
        raise ValueError("reviewer does not exist")
    return repository.review_import_batch(conn, batch.id, reviewer_id, _now())


def publish_trackolap_import(conn, import_batch_id: str, manager_id: str) -> ImportBatch:
    """Publish the reviewed batch and its valid normalized rows atomically."""
    batch = _trackolap_batch(conn, import_batch_id)
    if batch.reviewed_by_id != manager_id:
        raise ValueError("only the named manager reviewer may publish this TrackOlap import")
    published = repository.publish_import_batch(conn, batch.id, _now())
    repository.publish_trackolap_records(conn, published.id)
    return published


def refresh_live_source(
    conn,
    owner_id: str,
    config: Optional[TrackolapApiConfig] = None,
    credential_resolver: Optional[Callable[[str], Optional[str]]] = None,
    transport: Optional[httpx.BaseTransport] = None,
) -> TrackolapRefreshIngestResult:
    """Run the reviewed API lane and persist selected normalized revisions only.

    Absent, malformed, or credential-less configuration becomes a durable
    unavailable run.  No provider request occurs in those cases and raw API
    payloads never leave process memory.
    """
    _require_owner(conn, owner_id)
    try:
        resolved_config = config if config is not None else TrackolapApiConfig.from_environment()
    except TrackolapConfigurationError:
        resolved_config = None
        configuration_error = "configuration_invalid"
    else:
        configuration_error = None
    mapping_version = resolved_config.mapping_manifest.version if resolved_config else "not_configured"
    source = _ensure_source(conn, owner_id, mapping_version)
    if resolved_config is None:
        run = repository.create_source_run(
            conn,
            source.id,
            coverage={"input": "live_api"},
            mapping_version=mapping_version,
            status="unavailable",
            fetched_at=_now(),
            error_summary=configuration_error or "configuration_unavailable",
        )
        return TrackolapRefreshIngestResult(source, run, "unavailable", run.error_summary, 0, 0)

    outcome = refresh_trackolap(
        source,
        resolved_config,
        credential_resolver or environment_credential_resolver,
        transport=transport,
        cursor=_latest_cursor(conn, source.id),
    )
    if outcome.status != "succeeded":
        run = repository.create_source_run(
            conn,
            source.id,
            coverage={"input": "live_api"},
            mapping_version=resolved_config.mapping_manifest.version,
            status=outcome.status,
            fetched_at=_now(),
            error_summary=outcome.reason_code,
        )
        return TrackolapRefreshIngestResult(source, run, outcome.status, outcome.reason_code, 0, 0)

    mapped = [
        (feed, normalise_row(feed, row, resolved_config.mapping_manifest))
        for feed, fetched in outcome.feed_results.items()
        for row in fetched.rows
    ]
    valid = [result.record for _, result in mapped if result.record is not None]
    quarantined = sum(result.record is None for _, result in mapped)
    with _INGEST_LOCK:
        try:
            conn.execute("BEGIN IMMEDIATE")
            run = repository.create_source_run(
                conn,
                source.id,
                coverage={"input": "live_api", "feeds": sorted(outcome.feed_results)},
                mapping_version=resolved_config.mapping_manifest.version,
                status="quarantined" if quarantined else "succeeded",
                cursor=json.dumps(dict(outcome.cursor), sort_keys=True, separators=(",", ":")),
                fetched_at=_now(),
                rows_received=outcome.rows_received,
                rows_accepted=len(valid),
                error_summary="row_validation_failed" if quarantined else None,
                commit=False,
            )
            for record in valid:
                repository.create_trackolap_record(
                    conn,
                    source.id,
                    run.id,
                    None,
                    record.feed,
                    record.source_id,
                    record.source_updated_at,
                    record.tenant_id,
                    dict(record.values),
                    status="valid",
                    commit=False,
                )
            conn.commit()
        except Exception:
            conn.rollback()
            failed = repository.create_source_run(
                conn,
                source.id,
                coverage={"input": "live_api"},
                mapping_version=resolved_config.mapping_manifest.version,
                status="failed",
                fetched_at=_now(),
                error_summary="persistence_failed",
            )
            return TrackolapRefreshIngestResult(source, failed, "failed", "persistence_failed", 0, 0)
    state = "quarantined" if quarantined else "succeeded"
    return TrackolapRefreshIngestResult(source, run, state, None, len(valid), quarantined)


def _store_rows(conn, batch_id: str, source_id: str, source_run_id: str, parsed: ParsedBundle) -> None:
    row_number = 0
    for parsed_row in parsed.rows:
        row_number += 1
        receipt = {"feed": parsed_row.feed, "source_row_number": parsed_row.row_number}
        if parsed_row.record is None:
            repository.create_import_row(
                conn,
                batch_id,
                row_number,
                receipt,
                {},
                [dict(error) for error in parsed_row.errors],
                status="quarantined",
                commit=False,
            )
            continue
        record = parsed_row.record
        mapped = {
            "feed": record.feed,
            "source_id": record.source_id,
            "source_updated_at": record.source_updated_at,
            "tenant_id": record.tenant_id,
            "values": dict(record.values),
        }
        import_row = repository.create_import_row(
            conn, batch_id, row_number, receipt, mapped, [], status="valid", commit=False
        )
        repository.create_trackolap_record(
            conn,
            source_id,
            source_run_id,
            batch_id,
            record.feed,
            record.source_id,
            record.source_updated_at,
            record.tenant_id,
            dict(record.values),
            status="valid",
            commit=False,
        )
        # The import row deliberately has no target entity.  It is source
        # context, not a canonical farm, field, allocation, or completed task.
        assert import_row.target_entity_id is None

    for bundle_error in parsed.errors:
        row_number += 1
        repository.create_import_row(
            conn,
            batch_id,
            row_number,
            {"scope": "bundle"},
            {},
            [dict(bundle_error)],
            status="quarantined",
            commit=False,
        )


def _result_for_existing(conn, source: SourceRegistry, batch: ImportBatch) -> TrackolapIngestResult:
    rows = repository.list_import_rows(conn, batch.id)
    counts = Counter(row.status for row in rows)
    runs = repository.list_source_runs(conn, source.id)
    return TrackolapIngestResult(
        source=source,
        batch=batch,
        source_run=runs[-1] if runs else None,
        valid_count=counts["valid"] + counts["published"],
        quarantined_count=counts["quarantined"] + counts["invalid"],
        idempotent=True,
    )


def _latest_cursor(conn, source_id: str) -> dict[str, Optional[str]]:
    for run in reversed(repository.list_source_runs(conn, source_id)):
        if not run.cursor:
            continue
        try:
            parsed = json.loads(run.cursor)
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(parsed, dict):
            continue
        cursor = {
            str(feed): value
            for feed, value in parsed.items()
            if isinstance(feed, str) and (value is None or isinstance(value, str))
        }
        if cursor:
            return cursor
    return {}


def _profile(parsed: ParsedBundle, mapping_version: str) -> dict[str, Any]:
    feed_counts = Counter(row.feed for row in parsed.rows)
    return {
        "format": "zip_csv",
        "mapping_version": mapping_version,
        "feeds": dict(sorted(feed_counts.items())),
        "row_count": len(parsed.rows),
        "bundle_error_count": len(parsed.errors),
        "policy": "normalized source context only; no task completion or farm creation",
    }


def _ensure_source(conn, owner_id: str, mapping_version: str) -> SourceRegistry:
    existing = repository.get_source_registry_by_key(conn, SOURCE_KEY)
    if existing is not None:
        if existing.source_type != "trackolap" or existing.authority_level != "partner":
            raise ValueError("TrackOlap source key is already registered with incompatible authority")
        return existing
    return repository.create_source_registry(
        conn,
        source_key=SOURCE_KEY,
        display_name="Fortune paddy operations (TrackOlap/TrackWick)",
        source_type="trackolap",
        purpose="Fortune paddy field-operations context",
        authority_level="partner",
        owner_id=owner_id,
        permitted_data_classes=[
            "officer_activity",
            "farm_task_context",
            "visit_observation",
            "issue_observation",
            "pesticide_event",
        ],
        schema_version="trackolap-v1",
        mapping_version=mapping_version,
        default_coverage={"tenant": "fortune-paddy"},
        license_notes="Read-only partner export; human review required before use.",
        enabled=False,
    )


def _trackolap_batch(conn, import_batch_id: str) -> ImportBatch:
    batch = repository.get_import_batch(conn, import_batch_id)
    if batch is None or batch.purpose != IMPORT_PURPOSE:
        raise LookupError("TrackOlap import batch not found")
    return batch


def _require_owner(conn, owner_id: str) -> None:
    if conn.execute("SELECT 1 FROM people WHERE id = ?", (owner_id,)).fetchone() is None:
        raise ValueError("import owner does not exist")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
