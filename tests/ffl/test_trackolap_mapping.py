from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from ffl.integrations.trackolap.csv_ingest import parse_csv_bundle
from ffl.integrations.trackolap.mapping import MappingManifest, normalise_row
from ffl.integrations.trackolap.mapping import MappingManifestError
import pytest


VISIT_MANIFEST = MappingManifest.from_dict(
    {
        "version": "fortune-paddy-v1",
        "feeds": {
            "visits": {
                "source_id": "visit_key",
                "source_updated_at": "updated",
                "tenant_id": "tenant",
                "visit_id": "visit_key",
                "task_id": "task_key",
                "filing_officer_id": "filed_by",
                "performed_at": "performed",
                "submitted_at": "submitted",
                "visit_status": "status",
            }
        },
    }
)


def _zip_bytes(files: dict[str, str]) -> bytes:
    stream = BytesIO()
    with ZipFile(stream, "w", compression=ZIP_DEFLATED) as archive:
        for filename, content in files.items():
            archive.writestr(filename, content)
    return stream.getvalue()


def test_mapping_keeps_filing_officer_separate_from_territory_owner():
    result = normalise_row(
        "visits",
        {
            "visit_key": "visit-1",
            "task_key": "task-1",
            "filed_by": "officer-1",
            "performed": "2026-08-03T09:00:00+05:30",
            "submitted": "2026-08-03T09:05:00+05:30",
            "status": "complete",
            "tenant": "fortune-paddy",
            "updated": "2026-08-03T09:05:00+05:30",
        },
        VISIT_MANIFEST,
    )

    assert result.errors == ()
    assert result.record is not None
    assert result.record.values["filing_officer_id"] == "officer-1"
    assert "territory_owner_id" not in result.record.values


def test_csv_bundle_reports_unknown_header_and_never_guesses_mapping():
    bundle = _zip_bytes({"visits.csv": "visit_key,wrong\nv-1,value\n"})

    parsed = parse_csv_bundle(bundle, VISIT_MANIFEST)

    assert parsed.rows[0].errors[0]["code"] == "missing_mapped_column"


def test_mapping_manifest_rejects_contact_or_gps_source_columns():
    with pytest.raises(MappingManifestError, match="forbidden source column"):
        MappingManifest.from_dict(
            {
                "version": "unsafe-v1",
                "feeds": {
                    "visits": {
                        "source_id": "visit_key",
                        "source_updated_at": "updated",
                        "tenant_id": "tenant",
                        "visit_id": "visit_key",
                        "task_id": "task_key",
                        "filing_officer_id": "farmer_phone",
                        "performed_at": "performed",
                        "submitted_at": "submitted",
                        "visit_status": "status",
                    }
                },
            }
        )
