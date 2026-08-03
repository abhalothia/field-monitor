"""Privacy-minimising crop-purchase capture for one Fortune season.

The source export is allowed to use the opaque farmer code shared with the
Fortune field programme.  That code is used only in memory to make sure each
grower appears once in a coherent snapshot, then is discarded.  The retained
record is a season aggregate: it can show Fortune's share of *reported
harvest*, but never exposes a farmer, bill, payment, or individual quantity.
"""

from __future__ import annotations

import csv
from collections import Counter
from datetime import datetime
import hashlib
import io
import re
import threading
from typing import Any, Iterable, Optional

from ffl.persistence import repository
from ffl.services import imports
from ffl.services.evidence import retain_evidence
from ffl.services.evidence_store import EvidenceStore


PURPOSE = "procurement_capture"
MAPPING_VERSION = "procurement-capture-v1"
_LOCK = threading.RLock()
_OPAQUE_CODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_REQUIRED_SOURCE_COLUMNS = {
    "season_code", "farmer_code", "harvested_quantity_qtl",
    "fortune_purchase_quantity_qtl", "snapshot_date",
}
_AGGREGATE_COLUMNS = (
    "season_code", "snapshot_date", "reported_farmers", "reported_harvest_qtl",
    "fortune_purchase_qtl", "purchase_share_percent",
)


def _canonical_header(value: str) -> str:
    return "_".join(
        "".join(character if character.isalnum() else " " for character in value.lower()).split()
    )


def _number(value: str, field: str, line_number: int, *, positive: bool) -> float:
    try:
        parsed = float(value.strip().replace(",", ""))
    except ValueError as error:
        raise ValueError("{0} must be numeric on row {1}".format(field, line_number)) from error
    if parsed < 0 or (positive and parsed == 0):
        qualifier = "positive" if positive else "non-negative"
        raise ValueError("{0} must be {1} on row {2}".format(field, qualifier, line_number))
    return parsed


def _snapshot_date(value: str, line_number: int) -> str:
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date().isoformat()
    except ValueError as error:
        raise ValueError("snapshot_date must be YYYY-MM-DD on row {0}".format(line_number)) from error


def _parse(content: bytes) -> tuple[list[str], list[tuple[int, dict[str, str]]]]:
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("procurement capture CSV must be UTF-8 encoded") from error
    try:
        reader = csv.DictReader(io.StringIO(decoded, newline=""), strict=True)
        if reader.fieldnames is None:
            raise ValueError("procurement capture CSV must include a header row")
        headers = [_canonical_header(header or "") for header in reader.fieldnames]
        if not all(headers) or len(headers) != len(set(headers)):
            raise ValueError("procurement capture CSV headers must be non-empty and unique")
        unsupported = sorted(set(headers) - _REQUIRED_SOURCE_COLUMNS)
        if unsupported:
            raise ValueError("procurement capture CSV contains unsupported columns: " + ", ".join(unsupported))
        missing = sorted(_REQUIRED_SOURCE_COLUMNS - set(headers))
        if missing:
            raise ValueError("procurement capture CSV is missing required columns: " + ", ".join(missing))
        rows = []
        for row in reader:
            if None in row:
                raise ValueError("procurement capture CSV row has more cells than its header")
            rows.append((reader.line_num, {_canonical_header(key): value or "" for key, value in row.items()}))
        return headers, rows
    except csv.Error as error:
        raise ValueError("procurement capture CSV is malformed") from error


def _aggregate(rows: Iterable[tuple[int, dict[str, str]]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    counts = Counter()
    codes: set[str] = set()
    seasons: set[str] = set()
    snapshot_dates: set[str] = set()
    harvested = 0.0
    purchased = 0.0
    for line_number, row in rows:
        counts["input"] += 1
        try:
            farmer_code = row["farmer_code"].strip()
            if _OPAQUE_CODE.fullmatch(farmer_code) is None:
                raise ValueError("farmer_code must be a stable opaque code on row {0}".format(line_number))
            if farmer_code in codes:
                raise ValueError("farmer_code appears more than once on row {0}".format(line_number))
            season_code = row["season_code"].strip()
            if _OPAQUE_CODE.fullmatch(season_code) is None:
                raise ValueError("season_code must be a stable opaque code on row {0}".format(line_number))
            snapshot_date = _snapshot_date(row["snapshot_date"], line_number)
            reported_harvest = _number(row["harvested_quantity_qtl"], "harvested_quantity_qtl", line_number, positive=True)
            fortune_purchase = _number(
                row["fortune_purchase_quantity_qtl"], "fortune_purchase_quantity_qtl", line_number, positive=False
            )
            if fortune_purchase > reported_harvest:
                raise ValueError("fortune_purchase_quantity_qtl cannot exceed reported harvest on row {0}".format(line_number))
        except ValueError:
            counts["invalid"] += 1
            continue
        codes.add(farmer_code)
        seasons.add(season_code)
        snapshot_dates.add(snapshot_date)
        harvested += reported_harvest
        purchased += fortune_purchase
        counts["accepted"] += 1
    if not counts["accepted"]:
        raise ValueError("procurement capture CSV has no valid rows")
    if len(seasons) != 1 or len(snapshot_dates) != 1:
        raise ValueError("procurement capture CSV must be one season and one snapshot date")
    share = 100 * purchased / harvested
    return [{
        "season_code": next(iter(seasons)),
        "snapshot_date": next(iter(snapshot_dates)),
        "reported_farmers": len(codes),
        "reported_harvest_qtl": round(harvested, 3),
        "fortune_purchase_qtl": round(purchased, 3),
        "purchase_share_percent": round(share, 1),
    }], {"input": counts["input"], "accepted": counts["accepted"], "invalid": counts["invalid"]}


def _aggregate_content(cohorts: list[dict[str, Any]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=_AGGREGATE_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(cohorts)
    return buffer.getvalue().encode("utf-8")


def _summary(conn, batch_id: str) -> dict:
    batch = repository.get_import_batch(conn, batch_id)
    if batch is None or batch.purpose != PURPOSE:
        raise LookupError("procurement capture batch not found")
    rows = repository.list_import_rows(conn, batch.id)
    cohorts = [row.mapped for row in rows if row.status in {"valid", "published"}]
    counts = Counter(row.status for row in rows)
    current = cohorts[0] if len(cohorts) == 1 else None
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
        "capture": current,
        "privacy_policy": "farmer codes, names, payment, purchase, and bill identifiers are discarded before retention",
    }


def register_procurement_capture(
    conn,
    content: bytes,
    owner_id: str,
    original_filename: Optional[str] = None,
    evidence_directory: Optional[str] = None,
    evidence_store: Optional[EvidenceStore] = None,
) -> dict:
    """Validate a one-season purchase snapshot and retain only its aggregate."""
    if conn.execute("SELECT 1 FROM people WHERE id = ?", (owner_id,)).fetchone() is None:
        raise ValueError("procurement capture owner does not exist")
    headers, rows = _parse(content)
    cohorts, counts = _aggregate(rows)
    artifact = retain_evidence(
        conn, _aggregate_content(cohorts), "text/csv", original_filename="procurement-capture.csv",
        created_by_person_id=owner_id, directory=evidence_directory, store=evidence_store,
    )
    profile = {
        "schema": MAPPING_VERSION,
        "source_content_sha256": hashlib.sha256(content).hexdigest(),
        "input_source_rows": counts["input"],
        "accepted_source_rows": counts["accepted"],
        "invalid_source_rows": counts["invalid"],
        "cohort_count": len(cohorts),
        "discarded_identifier_columns": ["farmer_code"],
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
            batch = repository.create_import_batch(
                conn, PURPOSE, artifact.content_hash, artifact.id, MAPPING_VERSION, owner_id, profile,
                status="profiled", commit=False,
            )
            for row_number, cohort in enumerate(cohorts, start=2):
                repository.create_import_row(
                    conn, batch.id, row_number, cohort, cohort, [], status="valid",
                    target_entity_type="procurement_capture", commit=False,
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    result = _summary(conn, batch.id)
    result["idempotent"] = False
    return result


def review_procurement_capture(conn, batch_id: str, manager_id: str):
    batch = repository.get_import_batch(conn, batch_id)
    if batch is None or batch.purpose != PURPOSE:
        raise ValueError("procurement capture batch does not exist")
    return imports.review_import(conn, batch_id, manager_id)


def publish_procurement_capture(conn, batch_id: str, manager_id: str) -> dict:
    batch = repository.get_import_batch(conn, batch_id)
    if batch is None or batch.purpose != PURPOSE:
        raise LookupError("procurement capture batch not found")
    if batch.reviewed_by_id != manager_id:
        raise ValueError("only the named manager reviewer may publish this procurement capture")
    imports.publish_import(conn, batch_id)
    return _summary(conn, batch_id)


def procurement_capture_summary(conn, batch_id: str) -> dict:
    return _summary(conn, batch_id)


def latest_published_procurement_capture(conn) -> Optional[dict]:
    """Return the newest reviewed season snapshot, never a draft or raw row."""
    row = conn.execute(
        """SELECT id FROM import_batches
           WHERE purpose = ? AND status = 'published'
           ORDER BY published_at DESC, received_at DESC, id DESC LIMIT 1""",
        (PURPOSE,),
    ).fetchone()
    return _summary(conn, row["id"]) if row is not None else None
