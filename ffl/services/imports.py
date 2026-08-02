"""Safe CSV import profiling and review lifecycle for the local pilot."""

import csv
import io
import sqlite3
import threading
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ffl.domain.models import ImportBatch
from ffl.persistence import repository
from ffl.services.evidence import retain_evidence
from ffl.services.evidence_store import EvidenceStore


KNOWN_PURPOSES = {"land_register", "field_visit", "soil_measurement", "farm_manifest"}
PURPOSE_COLUMNS = {
    "land_register": ("land_parcel_id",),
    "field_visit": ("allocation_id", "observed_at", "observation"),
    "soil_measurement": ("land_parcel_id", "sampled_on", "measurement", "value", "unit"),
    # This manifest deliberately names an opaque upstream farm record rather
    # than a person.  It provides reviewed location context and crop/season
    # context; it does not establish land rights or create a canonical field.
    "farm_manifest": (
        "source_farm_id", "record_status", "state_name", "district_name",
        "village_name", "pincode", "source_recorded_at", "source_record_ref",
    ),
}
IDENTITY_LIKE_COLUMNS = {"name", "phone", "plot", "plot_name", "parcel", "farmer_name"}
FARM_MANIFEST_OPTIONAL_COLUMNS = {
    "crop_name", "cultivar", "season_name", "latitude", "longitude",
    "location_precision", "boundary_evidence_ref",
}
FARM_MANIFEST_FORBIDDEN_COLUMNS = {
    "name", "farmer_name", "farmer_phone", "phone", "mobile", "email",
    "contact_name", "contact_phone", "person_name", "account_number",
    "bank_account", "aadhaar",
}
FARM_MANIFEST_STATUSES = {"active", "inactive", "pending_review"}
FARM_MANIFEST_PRECISIONS = {"village", "field_verified"}
_IMPORT_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _error(code: str, message: str, field: Optional[str] = None) -> Dict[str, str]:
    value = {"code": code, "message": message}
    if field is not None:
        value["field"] = field
    return value


def _decode_csv(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV must be UTF-8 encoded") from exc


def _parse_csv(content: bytes) -> Tuple[List[str], List[Tuple[int, List[str]]], List[Dict[str, str]]]:
    reader = csv.reader(io.StringIO(_decode_csv(content), newline=""), strict=True)
    try:
        headers = next(reader)
    except StopIteration:
        raise ValueError("CSV must include a header row")
    except csv.Error as exc:
        raise ValueError("malformed CSV header") from exc
    rows: List[Tuple[int, List[str]]] = []
    errors: List[Dict[str, str]] = []
    try:
        for row in reader:
            rows.append((reader.line_num, row))
    except csv.Error:
        errors.append(_error("malformed_csv", "CSV quoting or structure is malformed"))
    return headers, rows, errors


def _profile(headers: List[str], rows: Iterable[Tuple[int, List[str]]], parse_errors: List[Dict[str, str]]) -> Dict[str, Any]:
    normalized = [header.strip() for header in headers]
    duplicates = sorted({header for header in normalized if header and normalized.count(header) > 1})
    return {
        "headers": headers,
        "normalized_headers": normalized,
        "row_count": len(list(rows)),
        "blank_headers": [index + 1 for index, header in enumerate(normalized) if not header],
        "duplicate_headers": duplicates,
        "parse_errors": parse_errors,
        "format": "csv",
        "mapping_version": "csv-v1",
    }


def _reference_exists(conn, purpose: str, mapped: Dict[str, str]) -> Optional[Dict[str, str]]:
    if purpose == "farm_manifest":
        return None
    if purpose in ("land_register", "soil_measurement"):
        identifier = mapped.get("land_parcel_id", "")
        table, column = "land_parcels", "land_parcel_id"
    else:
        identifier = mapped.get("allocation_id", "")
        table, column = "crop_allocations", "allocation_id"
    if conn.execute("SELECT 1 FROM {0} WHERE id = ?".format(table), (identifier,)).fetchone() is None:
        return _error("unresolved_stable_identifier", "stable identifier is not known to FFL", column)
    return None


def _is_iso_date(value: str) -> bool:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _is_iso_timestamp(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.tzinfo is not None
    except ValueError:
        return False


def _slug(value: str) -> str:
    return "".join(character if character.isalnum() else "-" for character in value.lower()).strip("-")


def _canonical_header(value: str) -> str:
    return "_".join(_slug(value).split("-"))


def _farm_manifest_row(
    normalized_headers: List[str], row: List[str], header_problems: bool,
) -> Tuple[Dict[str, str], str, List[Dict[str, str]]]:
    raw = {normalized_headers[index]: value for index, value in enumerate(row) if index < len(normalized_headers)}
    if len(row) != len(normalized_headers):
        return raw, "quarantined", [_error("malformed_row", "row has a different number of cells than its header")]
    if header_problems:
        return raw, "quarantined", [_error("ambiguous_headers", "CSV headers are blank, duplicated, or unsafe")]
    required = PURPOSE_COLUMNS["farm_manifest"]
    missing_columns = [column for column in required if column not in normalized_headers]
    if missing_columns:
        return raw, "quarantined", [
            _error("missing_required_columns", "farm manifest requires stable, non-person columns", column)
            for column in missing_columns
        ]
    mapped = {column: raw.get(column, "").strip() for column in required + tuple(FARM_MANIFEST_OPTIONAL_COLUMNS)}
    mapped = {key: value for key, value in mapped.items() if value}
    errors: List[Dict[str, str]] = []
    for column in required:
        if not mapped.get(column):
            errors.append(_error("missing_value", "required value is blank", column))
    source_farm_id = mapped.get("source_farm_id", "")
    if source_farm_id and (len(source_farm_id) > 128 or not all(character.isalnum() or character in "._:-" for character in source_farm_id)):
        errors.append(_error("invalid_source_farm_id", "source_farm_id must be an opaque stable identifier", "source_farm_id"))
    if mapped.get("record_status") and mapped["record_status"] not in FARM_MANIFEST_STATUSES:
        errors.append(_error("invalid_record_status", "record_status must be active, inactive, or pending_review", "record_status"))
    if mapped.get("pincode") and (len(mapped["pincode"]) != 6 or not mapped["pincode"].isdigit()):
        errors.append(_error("invalid_pincode", "pincode must be a six-digit Indian PIN", "pincode"))
    if mapped.get("source_recorded_at") and not _is_iso_timestamp(mapped["source_recorded_at"]):
        errors.append(_error("invalid_timestamp", "source_recorded_at must be an ISO-8601 timestamp with timezone", "source_recorded_at"))
    has_latitude = "latitude" in mapped
    has_longitude = "longitude" in mapped
    if has_latitude != has_longitude:
        errors.append(_error("incomplete_coordinate", "latitude and longitude must be supplied together", "latitude"))
    if has_latitude and has_longitude:
        try:
            latitude, longitude = float(mapped["latitude"]), float(mapped["longitude"])
        except ValueError:
            errors.append(_error("invalid_coordinate", "coordinates must be numeric", "latitude"))
        else:
            if not (6.0 <= latitude <= 38.0 and 68.0 <= longitude <= 98.0):
                errors.append(_error("coordinate_outside_india", "coordinates must be within India", "latitude"))
        if mapped.get("location_precision") != "field_verified":
            errors.append(_error("unverified_coordinate", "coordinates require location_precision=field_verified", "location_precision"))
        if not mapped.get("boundary_evidence_ref"):
            errors.append(_error("missing_boundary_evidence", "coordinates require a boundary_evidence_ref", "boundary_evidence_ref"))
    elif mapped.get("location_precision") and mapped["location_precision"] not in FARM_MANIFEST_PRECISIONS:
        errors.append(_error("invalid_location_precision", "location_precision must be village or field_verified", "location_precision"))
    elif mapped.get("location_precision") == "field_verified":
        errors.append(_error("missing_coordinate", "field_verified location_precision requires coordinates", "latitude"))
    if not errors:
        mapped["district_context_key"] = "in:" + _slug(mapped["state_name"]) + ":" + _slug(mapped["district_name"])
        mapped["map_eligibility"] = "field_verified" if has_latitude else "village_context_only"
    return mapped, "invalid" if errors else "valid", errors


def _validate_row(
    conn, purpose: str, normalized_headers: List[str], row: List[str], header_problems: bool,
) -> Tuple[Dict[str, str], str, List[Dict[str, str]]]:
    if purpose == "farm_manifest":
        return _farm_manifest_row(normalized_headers, row, header_problems)
    raw = {normalized_headers[index]: value for index, value in enumerate(row) if index < len(normalized_headers)}
    if len(row) != len(normalized_headers):
        return raw, "quarantined", [_error("malformed_row", "row has a different number of cells than its header")]
    if header_problems:
        return raw, "quarantined", [_error("ambiguous_headers", "CSV headers are blank or duplicated")]
    required = PURPOSE_COLUMNS[purpose]
    missing_columns = [column for column in required if column not in normalized_headers]
    if missing_columns:
        identity_values = any(raw.get(column, "").strip() for column in IDENTITY_LIKE_COLUMNS)
        code = "ambiguous_identity" if identity_values else "missing_required_columns"
        return raw, "quarantined", [_error(code, "stable mapping columns are required; names, phones, and plots are not matched")]
    mapped = {column: raw.get(column, "").strip() for column in required}
    blank = [column for column, value in mapped.items() if not value]
    if blank:
        return mapped, "invalid", [_error("missing_value", "required value is blank", column) for column in blank]
    reference_error = _reference_exists(conn, purpose, mapped)
    if reference_error:
        return mapped, "quarantined", [reference_error]
    errors: List[Dict[str, str]] = []
    if purpose == "field_visit" and not _is_iso_date(mapped["observed_at"]):
        errors.append(_error("invalid_timestamp", "observed_at must be ISO-8601", "observed_at"))
    if purpose == "soil_measurement":
        if not _is_iso_date(mapped["sampled_on"]):
            errors.append(_error("invalid_date", "sampled_on must be ISO-8601", "sampled_on"))
        try:
            float(mapped["value"])
        except ValueError:
            errors.append(_error("invalid_number", "value must be numeric", "value"))
    return mapped, "invalid" if errors else "valid", errors


def _summary(conn, batch: ImportBatch, idempotent: bool = False) -> Dict[str, Any]:
    rows = repository.list_import_rows(conn, batch.id)
    counts = Counter(row.status for row in rows)
    return {
        "batch": batch,
        "idempotent": idempotent,
        "counters": {
            "total": len(rows),
            "valid": counts["valid"],
            "invalid": counts["invalid"],
            "quarantined": counts["quarantined"],
            "published": counts["published"],
        },
    }


def review_import(conn, import_batch_id: str, reviewer_id: str) -> ImportBatch:
    """Explicitly record that a known FFL user reviewed the retained rows."""
    if conn.execute("SELECT 1 FROM people WHERE id = ?", (reviewer_id,)).fetchone() is None:
        raise ValueError("reviewer does not exist")
    return repository.review_import_batch(conn, import_batch_id, reviewer_id, _now())


def register_csv_import(
    conn,
    content: bytes,
    purpose: str,
    owner_id: str,
    original_filename: Optional[str] = None,
    evidence_directory: Optional[str] = None,
    evidence_store: Optional[EvidenceStore] = None,
) -> Dict[str, Any]:
    """Retain and profile CSV rows.  It never creates or overwrites farm records."""
    if purpose not in KNOWN_PURPOSES:
        raise ValueError("unsupported import purpose")
    if conn.execute("SELECT 1 FROM people WHERE id = ?", (owner_id,)).fetchone() is None:
        raise ValueError("import owner does not exist")
    artifact = retain_evidence(
        conn, content, "text/csv", original_filename=original_filename,
        created_by_person_id=owner_id, directory=evidence_directory, store=evidence_store,
    )
    headers, rows, parse_errors = _parse_csv(content)
    profile = _profile(headers, rows, parse_errors)
    normalized_headers = profile["normalized_headers"]
    header_problems = bool(profile["blank_headers"] or profile["duplicate_headers"] or parse_errors)
    # A FastAPI app uses a shared pilot SQLite connection.  The process lock
    # protects same-process requests; BEGIN IMMEDIATE serializes separate local
    # processes.  Batch and row writes deliberately share one transaction.
    with _IMPORT_LOCK:
        existing = repository.get_import_batch_by_content_hash(conn, artifact.content_hash)
        if existing is not None:
            if existing.purpose != purpose:
                raise ValueError("content is already registered under a different import purpose")
            return _summary(conn, existing, idempotent=True)
        try:
            conn.execute("BEGIN IMMEDIATE")
            existing = repository.get_import_batch_by_content_hash(conn, artifact.content_hash)
            if existing is not None:
                conn.rollback()
                if existing.purpose != purpose:
                    raise ValueError("content is already registered under a different import purpose")
                return _summary(conn, existing, idempotent=True)
            batch = repository.create_import_batch(
                conn, purpose, artifact.content_hash, artifact.id, "csv-v1", owner_id, profile,
                status="profiled", commit=False,
            )
            for row_number, row in rows:
                mapped, row_status, errors = _validate_row(conn, purpose, normalized_headers, row, header_problems)
                raw = {"headers": headers, "cells": row}
                repository.create_import_row(
                    conn, batch.id, row_number, raw, mapped, errors, status=row_status, commit=False
                )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            established = repository.get_import_batch_by_content_hash(conn, artifact.content_hash)
            if established is None:
                raise
            if established.purpose != purpose:
                raise ValueError("content is already registered under a different import purpose")
            return _summary(conn, established, idempotent=True)
        except Exception:
            conn.rollback()
            raise
    return _summary(conn, batch)


def register_farm_manifest(
    conn,
    content: bytes,
    owner_id: str,
    original_filename: Optional[str] = None,
    evidence_directory: Optional[str] = None,
    evidence_store: Optional[EvidenceStore] = None,
) -> Dict[str, Any]:
    """Retain a minimal, non-person farm manifest after strict preflight.

    This has no side effect on operating units, land, fields, or maps. A
    named manager must still review and publish the retained batch. The CSV is
    checked before evidence retention so an accidental contact roster is never
    copied into FFL storage.
    """
    headers, rows, parse_errors = _parse_csv(content)
    normalized_headers = [header.strip() for header in headers]
    canonical_headers = [_canonical_header(header) for header in normalized_headers]
    forbidden = sorted(set(canonical_headers).intersection(FARM_MANIFEST_FORBIDDEN_COLUMNS))
    if forbidden:
        raise ValueError("farm manifest must not contain personal or payment columns: " + ", ".join(forbidden))
    required = set(PURPOSE_COLUMNS["farm_manifest"])
    missing = sorted(required - set(canonical_headers))
    if missing:
        raise ValueError("farm manifest is missing required columns: " + ", ".join(missing))
    schema_columns = required.union(FARM_MANIFEST_OPTIONAL_COLUMNS)
    aliases = sorted(
        header for header, canonical in zip(normalized_headers, canonical_headers)
        if canonical in schema_columns and header != canonical
    )
    if aliases:
        raise ValueError("farm manifest columns must use the documented snake_case names: " + ", ".join(aliases))
    if parse_errors:
        raise ValueError("farm manifest CSV is malformed")
    id_index = canonical_headers.index("source_farm_id")
    identifiers = [row[id_index].strip() for _, row in rows if len(row) > id_index and row[id_index].strip()]
    duplicates = sorted({identifier for identifier in identifiers if identifiers.count(identifier) > 1})
    if duplicates:
        raise ValueError("farm manifest contains duplicate source_farm_id values")
    return register_csv_import(
        conn, content, "farm_manifest", owner_id, original_filename,
        evidence_directory=evidence_directory, evidence_store=evidence_store,
    )


def farm_manifest_summary(conn, import_batch_id: str) -> Dict[str, Any]:
    """Return manager-safe coverage counters, never raw rows or coordinates."""
    batch = repository.get_import_batch(conn, import_batch_id)
    if batch is None or batch.purpose != "farm_manifest":
        raise LookupError("farm manifest not found")
    rows = repository.list_import_rows(conn, batch.id)
    counts = Counter(row.status for row in rows)
    mapped = [row.mapped for row in rows if row.status in {"valid", "published"}]
    districts = sorted({row.get("district_context_key") for row in mapped if row.get("district_context_key")})
    return {
        "batch": batch,
        "counters": {
            "total": len(rows),
            "valid": counts["valid"],
            "invalid": counts["invalid"],
            "quarantined": counts["quarantined"],
            "published": counts["published"],
            "field_verified": sum(row.get("map_eligibility") == "field_verified" for row in mapped),
            "village_context_only": sum(row.get("map_eligibility") == "village_context_only" for row in mapped),
        },
        "district_context_keys": districts,
        "map_policy": "only field_verified rows with boundary evidence may become field markers",
    }


def review_farm_manifest(conn, import_batch_id: str, reviewer_id: str) -> ImportBatch:
    person = conn.execute("SELECT role FROM people WHERE id = ?", (reviewer_id,)).fetchone()
    if person is None or person["role"] not in {"farm_manager", "operations_lead", "agronomist"}:
        raise ValueError("farm manifest requires a named manager reviewer")
    batch = repository.get_import_batch(conn, import_batch_id)
    if batch is None or batch.purpose != "farm_manifest":
        raise ValueError("farm manifest does not exist")
    return review_import(conn, import_batch_id, reviewer_id)


def publish_farm_manifest(conn, import_batch_id: str, manager_id: str) -> Dict[str, Any]:
    batch = repository.get_import_batch(conn, import_batch_id)
    if batch is None or batch.purpose != "farm_manifest":
        raise LookupError("farm manifest not found")
    if batch.reviewed_by_id != manager_id:
        raise ValueError("only the named manager reviewer may publish this farm manifest")
    publish_import(conn, import_batch_id)
    return farm_manifest_summary(conn, import_batch_id)


def get_import(conn, import_batch_id: str) -> Dict[str, Any]:
    batch = repository.get_import_batch(conn, import_batch_id)
    if batch is None:
        raise LookupError("import batch not found")
    result = _summary(conn, batch)
    result["rows"] = repository.list_import_rows(conn, batch.id)
    return result


def publish_import(conn, import_batch_id: str) -> Dict[str, Any]:
    """Advance only a reviewed, entirely valid batch; rows stay evidence-only."""
    batch = repository.publish_import_batch(conn, import_batch_id, _now())
    return _summary(conn, batch)
