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


KNOWN_PURPOSES = {"land_register", "field_visit", "soil_measurement"}
PURPOSE_COLUMNS = {
    "land_register": ("land_parcel_id",),
    "field_visit": ("allocation_id", "observed_at", "observation"),
    "soil_measurement": ("land_parcel_id", "sampled_on", "measurement", "value", "unit"),
}
IDENTITY_LIKE_COLUMNS = {"name", "phone", "plot", "plot_name", "parcel", "farmer_name"}
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


def _validate_row(
    conn, purpose: str, normalized_headers: List[str], row: List[str], header_problems: bool,
) -> Tuple[Dict[str, str], str, List[Dict[str, str]]]:
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
) -> Dict[str, Any]:
    """Retain and profile CSV rows.  It never creates or overwrites farm records."""
    if purpose not in KNOWN_PURPOSES:
        raise ValueError("unsupported import purpose")
    if conn.execute("SELECT 1 FROM people WHERE id = ?", (owner_id,)).fetchone() is None:
        raise ValueError("import owner does not exist")
    artifact = retain_evidence(
        conn, content, "text/csv", original_filename=original_filename,
        created_by_person_id=owner_id, directory=evidence_directory,
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
