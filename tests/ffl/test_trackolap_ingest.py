from __future__ import annotations

import csv
from io import StringIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from ffl.integrations.trackolap.contracts import COMMON_FIELDS, REQUIRED_FIELDS
from ffl.integrations.trackolap.mapping import MappingManifest
from ffl.persistence import repository
from ffl.services.trackolap_ingest import (
    ingest_csv_bundle,
    publish_trackolap_import,
    review_trackolap_import,
)


MANIFEST = MappingManifest.from_dict(
    {
        "version": "fortune-paddy-v1",
        "feeds": {
            feed: {field: field for field in (*COMMON_FIELDS, *fields)}
            for feed, fields in REQUIRED_FIELDS.items()
        },
    }
)


def _csv(headers: tuple[str, ...], values: dict[str, str]) -> str:
    stream = StringIO()
    writer = csv.DictWriter(stream, fieldnames=headers)
    writer.writeheader()
    writer.writerow(values)
    return stream.getvalue()


def _bundle(*, bad_visit: bool = False, unsafe_visit_column: bool = False) -> bytes:
    common = {
        "tenant_id": "fortune-paddy",
        "source_updated_at": "2026-08-03T09:05:00+05:30",
    }
    rows = {
        "officers": {
            **common,
            "source_id": "officers-1",
            "officer_id": "po-riya",
            "display_name": "Riya Singh",
            "role": "PO",
            "active_status": "active",
            "territory_owner_id": "po-riya",
            "effective_from": "2026-06-01",
        },
        "attendance": {
            **common,
            "source_id": "attendance-1",
            "attendance_id": "attendance-1",
            "officer_id": "po-riya",
            "punch_status": "present",
            "observed_at": "2026-08-03T08:00:00+05:30",
        },
        "farmer_tasks": {
            **common,
            "source_id": "task-1",
            "task_id": "task-1",
            "farmer_code": "farmer-1",
            "territory_owner_id": "po-riya",
            "village_key": "village-1",
            "task_status": "active",
            "kit_status": "taken",
        },
        "visits": {
            **common,
            "source_id": "visit-1",
            "visit_id": "visit-1",
            "task_id": "task-1",
            "filing_officer_id": "po-riya",
            "performed_at": "not-a-timestamp" if bad_visit else "2026-08-03T09:00:00+05:30",
            "submitted_at": "2026-08-03T09:05:00+05:30",
            "visit_status": "complete",
        },
        "issue_observations": {
            **common,
            "source_id": "issue-1",
            "observation_id": "issue-1",
            "visit_id": "visit-1",
            "task_id": "task-1",
            "issue_code": "stem-borer",
            "severity": "high",
            "observed_at": "2026-08-03T09:00:00+05:30",
        },
        "pesticide_events": {
            **common,
            "source_id": "event-1",
            "event_id": "event-1",
            "task_id": "task-1",
            "product_code": "product-1",
            "event_kind": "recommended",
            "occurred_at": "2026-08-03T09:00:00+05:30",
            "kit_version": "pb-1-2026",
        },
    }
    stream = StringIO()
    # ``ZipFile`` needs a bytes-capable target, so convert after producing the
    # small source files below.
    del stream
    from io import BytesIO

    archive_bytes = BytesIO()
    with ZipFile(archive_bytes, "w", compression=ZIP_DEFLATED) as archive:
        for feed, values in rows.items():
            headers = (*COMMON_FIELDS, *REQUIRED_FIELDS[feed])
            if feed == "visits" and unsafe_visit_column:
                headers = (*headers, "farmer_phone")
                values = {**values, "farmer_phone": "9999999999"}
            archive.writestr(feed + ".csv", _csv(headers, values))
    return archive_bytes.getvalue()


def test_csv_bundle_retains_one_evidence_artifact_and_quarantines_bad_rows(ffl_db, owner, tmp_path):
    result = ingest_csv_bundle(
        ffl_db, _bundle(bad_visit=True), MANIFEST, owner.id, evidence_directory=str(tmp_path)
    )

    records = repository.list_trackolap_records(ffl_db, result.source.id)
    assert result.valid_count == 5
    assert result.quarantined_count == 1
    assert {record.feed for record in records} == {
        "officers", "attendance", "farmer_tasks", "issue_observations", "pesticide_events"
    }
    assert len(repository.list_evidence_artifacts(ffl_db)) == 1


def test_replaying_identical_bundle_is_idempotent(ffl_db, owner, tmp_path):
    bundle = _bundle()

    first = ingest_csv_bundle(ffl_db, bundle, MANIFEST, owner.id, evidence_directory=str(tmp_path))
    replay = ingest_csv_bundle(ffl_db, bundle, MANIFEST, owner.id, evidence_directory=str(tmp_path))

    assert replay.idempotent is True
    assert replay.batch.id == first.batch.id
    assert len(repository.list_trackolap_records(ffl_db, first.source.id)) == 6


def test_only_manager_reviewed_csv_records_are_published_for_metrics(ffl_db, owner, tmp_path):
    result = ingest_csv_bundle(ffl_db, _bundle(), MANIFEST, owner.id, evidence_directory=str(tmp_path))

    review_trackolap_import(ffl_db, result.batch.id, owner.id)
    publish_trackolap_import(ffl_db, result.batch.id, owner.id)

    assert len(repository.list_trackolap_records(ffl_db, result.source.id, statuses=("published",))) == 6


def test_unmapped_csv_column_is_rejected_before_private_evidence_retention(ffl_db, owner, tmp_path):
    with pytest.raises(ValueError, match="unsupported source headers"):
        ingest_csv_bundle(
            ffl_db,
            _bundle(unsafe_visit_column=True),
            MANIFEST,
            owner.id,
            evidence_directory=str(tmp_path),
        )

    assert repository.list_evidence_artifacts(ffl_db) == []
