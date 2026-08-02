"""Private procurement-history aggregation without retaining farmer identity.

The customer may have a historical purchase ledger before it has a clean plot
manifest. That ledger is valuable commercial context, but it is not a farm
directory. This module turns an approved ledger into month/village/variety
cohorts in memory, drops personal and transaction identifiers, and retains only
the aggregate evidence needed for a manager review.
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import io
import sqlite3
import threading
from typing import Any, Dict, Iterable, Optional

from ffl.persistence import repository
from ffl.services import imports
from ffl.services.evidence import retain_evidence
from ffl.services.evidence_store import EvidenceStore


PURPOSE = "procurement_history"
MAPPING_VERSION = "procurement-history-v1"
_LOCK = threading.RLock()
_REQUIRED_SOURCE_COLUMNS = {
    "entry_date", "village", "rate_per_qtl", "paddy_quantity_qtl", "variety_type",
}
_ALLOWED_SOURCE_COLUMNS = _REQUIRED_SOURCE_COLUMNS | {
    "purchase_paddy_purchase_number", "farmer_name", "bag", "po_name", "supply_bill_no_1st_attempt",
}
_DROPPED_COLUMNS = {
    "purchase_paddy_purchase_number", "farmer_name", "po_name", "supply_bill_no_1st_attempt",
}
_AGGREGATE_COLUMNS = (
    "month", "village_name", "variety_name", "purchase_count", "quantity_qtl", "bag_count",
    "weighted_rate_per_qtl",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_header(value: str) -> str:
    return "_".join(
        "".join(character if character.isalnum() else " " for character in value.lower()).split()
    )


def _text(value: str) -> str:
    return value.strip()


def _number(value: str, field: str, line_number: int) -> float:
    cleaned = value.strip().replace(",", "").replace("₹", "")
    try:
        parsed = float(cleaned)
    except ValueError as error:
        raise ValueError("{0} must be numeric on row {1}".format(field, line_number)) from error
    if parsed < 0:
        raise ValueError("{0} must not be negative on row {1}".format(field, line_number))
    return parsed


def _month(value: str, line_number: int) -> str:
    candidate = value.strip()
    for format_string in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y"):
        try:
            return datetime.strptime(candidate, format_string).strftime("%Y-%m")
        except ValueError:
            pass
    raise ValueError("entry_date must be a calendar date on row {0}".format(line_number))


def _parse(content: bytes) -> tuple[list[str], list[tuple[int, dict[str, str]]]]:
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("procurement CSV must be UTF-8 encoded") from error
    try:
        reader = csv.DictReader(io.StringIO(decoded, newline=""), strict=True)
        if reader.fieldnames is None:
            raise ValueError("procurement CSV must include a header row")
        headers = [_canonical_header(header or "") for header in reader.fieldnames]
        if not all(headers) or len(headers) != len(set(headers)):
            raise ValueError("procurement CSV headers must be non-empty and unique")
        unsupported = sorted(set(headers) - _ALLOWED_SOURCE_COLUMNS)
        if unsupported:
            raise ValueError("procurement CSV contains unsupported columns: " + ", ".join(unsupported))
        missing = sorted(_REQUIRED_SOURCE_COLUMNS - set(headers))
        if missing:
            raise ValueError("procurement CSV is missing required columns: " + ", ".join(missing))
        rows = []
        for row in reader:
            if None in row:
                raise ValueError("procurement CSV row has more cells than its header")
            rows.append((reader.line_num, {_canonical_header(key): value or "" for key, value in row.items()}))
        return headers, rows
    except csv.Error as error:
        raise ValueError("procurement CSV is malformed") from error


def _aggregate(rows: Iterable[tuple[int, dict[str, str]]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    cohorts: dict[tuple[str, str, str], dict[str, float]] = defaultdict(
        lambda: {"purchase_count": 0.0, "quantity_qtl": 0.0, "bag_count": 0.0, "rate_quantity": 0.0}
    )
    counts = Counter()
    for line_number, row in rows:
        counts["input"] += 1
        try:
            month = _month(row["entry_date"], line_number)
            village = _text(row["village"])
            variety = _text(row["variety_type"])
            if not village or not variety:
                raise ValueError("village and variety_type must be non-empty on row {0}".format(line_number))
            quantity = _number(row["paddy_quantity_qtl"], "paddy_quantity_qtl", line_number)
            if quantity == 0:
                raise ValueError("paddy_quantity_qtl must be positive on row {0}".format(line_number))
            rate = _number(row["rate_per_qtl"], "rate_per_qtl", line_number)
            bags = _number(row.get("bag", "0") or "0", "bag", line_number)
        except ValueError:
            counts["invalid"] += 1
            continue
        cohort = cohorts[(month, village, variety)]
        cohort["purchase_count"] += 1
        cohort["quantity_qtl"] += quantity
        cohort["bag_count"] += bags
        cohort["rate_quantity"] += rate * quantity
        counts["accepted"] += 1
    result = []
    for (month, village, variety), values in sorted(cohorts.items()):
        quantity = values["quantity_qtl"]
        result.append({
            "month": month,
            "village_name": village,
            "variety_name": variety,
            "purchase_count": int(values["purchase_count"]),
            "quantity_qtl": round(quantity, 3),
            "bag_count": round(values["bag_count"], 3),
            "weighted_rate_per_qtl": round(values["rate_quantity"] / quantity, 3),
        })
    return result, {"input": counts["input"], "accepted": counts["accepted"], "invalid": counts["invalid"]}


def _aggregate_content(cohorts: list[dict[str, Any]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=_AGGREGATE_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(cohorts)
    return buffer.getvalue().encode("utf-8")


def _summary(conn, batch_id: str) -> dict:
    batch = repository.get_import_batch(conn, batch_id)
    if batch is None or batch.purpose != PURPOSE:
        raise LookupError("procurement history batch not found")
    rows = repository.list_import_rows(conn, batch.id)
    cohorts = [row.mapped for row in rows if row.status in {"valid", "published"}]
    counts = Counter(row.status for row in rows)
    total_quantity = sum(float(cohort["quantity_qtl"]) for cohort in cohorts)
    total_rate_quantity = sum(float(cohort["quantity_qtl"]) * float(cohort["weighted_rate_per_qtl"]) for cohort in cohorts)
    return {
        "batch": batch,
        "counters": {
            "cohorts": len(rows),
            "valid": counts["valid"],
            "published": counts["published"],
            "invalid_source_rows": int(batch.profile.get("invalid_source_rows", 0)),
            "input_source_rows": int(batch.profile.get("input_source_rows", 0)),
            "accepted_source_rows": int(batch.profile.get("accepted_source_rows", 0)),
        },
        "coverage": {
            "months": sorted({cohort["month"] for cohort in cohorts}),
            "villages": len({cohort["village_name"] for cohort in cohorts}),
            "varieties": len({cohort["variety_name"] for cohort in cohorts}),
            "quantity_qtl": round(total_quantity, 3),
            "weighted_rate_per_qtl": round(total_rate_quantity / total_quantity, 3) if total_quantity else None,
        },
        "privacy_policy": "farmer, purchase, PO, and bill identifiers are discarded before retention",
    }


def register_procurement_history(
    conn,
    content: bytes,
    owner_id: str,
    original_filename: Optional[str] = None,
    evidence_directory: Optional[str] = None,
    evidence_store: Optional[EvidenceStore] = None,
) -> dict:
    """Sanitize a purchase ledger before retaining aggregated evidence."""
    if conn.execute("SELECT 1 FROM people WHERE id = ?", (owner_id,)).fetchone() is None:
        raise ValueError("procurement history owner does not exist")
    headers, rows = _parse(content)
    cohorts, counts = _aggregate(rows)
    if not cohorts:
        raise ValueError("procurement CSV has no valid rows to aggregate")
    sanitized = _aggregate_content(cohorts)
    artifact = retain_evidence(
        conn, sanitized, "text/csv", original_filename="procurement-cohorts.csv",
        created_by_person_id=owner_id, directory=evidence_directory, store=evidence_store,
    )
    profile = {
        "schema": MAPPING_VERSION,
        "source_content_sha256": hashlib.sha256(content).hexdigest(),
        "input_source_rows": counts["input"],
        "accepted_source_rows": counts["accepted"],
        "invalid_source_rows": counts["invalid"],
        "cohort_count": len(cohorts),
        "discarded_identifier_columns": sorted(set(headers).intersection(_DROPPED_COLUMNS)),
        "original_filename_present": bool(original_filename),
    }
    with _LOCK:
        existing = repository.get_import_batch_by_content_hash(conn, artifact.content_hash)
        if existing is not None:
            if existing.purpose != PURPOSE:
                raise ValueError("sanitized content is already registered under a different import purpose")
            result = _summary(conn, existing.id)
            result["idempotent"] = True
            return result
        try:
            conn.execute("BEGIN IMMEDIATE")
            existing = repository.get_import_batch_by_content_hash(conn, artifact.content_hash)
            if existing is not None:
                conn.rollback()
                if existing.purpose != PURPOSE:
                    raise ValueError("sanitized content is already registered under a different import purpose")
                result = _summary(conn, existing.id)
                result["idempotent"] = True
                return result
            batch = repository.create_import_batch(
                conn, PURPOSE, artifact.content_hash, artifact.id, MAPPING_VERSION, owner_id, profile,
                status="profiled", commit=False,
            )
            for row_number, cohort in enumerate(cohorts, start=2):
                repository.create_import_row(
                    conn, batch.id, row_number, cohort, cohort, [], status="valid",
                    target_entity_type="procurement_cohort", commit=False,
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    result = _summary(conn, batch.id)
    result["idempotent"] = False
    return result


def review_procurement_history(conn, batch_id: str, manager_id: str):
    batch = repository.get_import_batch(conn, batch_id)
    if batch is None or batch.purpose != PURPOSE:
        raise ValueError("procurement history batch does not exist")
    return imports.review_import(conn, batch_id, manager_id)


def publish_procurement_history(conn, batch_id: str, manager_id: str) -> dict:
    batch = repository.get_import_batch(conn, batch_id)
    if batch is None or batch.purpose != PURPOSE:
        raise LookupError("procurement history batch not found")
    if batch.reviewed_by_id != manager_id:
        raise ValueError("only the named manager reviewer may publish this procurement history")
    imports.publish_import(conn, batch_id)
    return _summary(conn, batch_id)


def procurement_history_summary(conn, batch_id: str) -> dict:
    return _summary(conn, batch_id)
