"""Manager-authorised export of the canonical operating ledger.

This is a narrow portability seam, deliberately not a communications export.
It contains only the canonical operating records that a manager needs to take
into a spreadsheet or another approved system.  Provider receipts, contact
addresses, raw message text, attachment URLs, private media, and candidate
drafts never cross this boundary.
"""

import csv
import io
import json
import sqlite3
from typing import Any, Dict, List

from ffl.persistence import repository


_COLUMNS = (
    "record_type",
    "record_id",
    "allocation_id",
    "field_name",
    "crop_name",
    "cultivar",
    "season_name",
    "record_status",
    "recorded_at",
    "owner_person_id",
    "summary",
    "structured_values",
    "evidence_artifact_id",
)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":"))


def _cell(value: Any) -> str:
    """Return a spreadsheet-safe value without changing the underlying record."""
    if value is None:
        return ""
    text = str(value)
    # Formula interpretation is a data-exfiltration risk when a manager opens
    # a field-created title or structured value in a spreadsheet application.
    return "'" + text if text[:1] in {"=", "+", "-", "@"} else text


def _base(allocation: sqlite3.Row) -> Dict[str, Any]:
    return {
        "allocation_id": allocation["allocation_id"],
        "field_name": allocation["field_name"],
        "crop_name": allocation["crop_name"],
        "cultivar": allocation["cultivar"],
        "season_name": allocation["season_name"],
    }


def operating_ledger_rows(conn: sqlite3.Connection, operating_unit_id: str) -> List[Dict[str, Any]]:
    """Return a deterministic, record-level export for one operating unit.

    The list uses only canonical work, exception, signal, checkpoint, and
    harvest tables.  Communications are purpose-limited records, so they are
    intentionally absent even when they originated a later accepted record.
    """
    if repository.get_operating_unit(conn, operating_unit_id) is None:
        raise LookupError("operating unit not found")

    allocations = conn.execute(
        """SELECT crop_allocations.id AS allocation_id, operational_blocks.name AS field_name,
                  crop_allocations.crop_name, crop_allocations.cultivar, seasons.name AS season_name
           FROM crop_allocations
           JOIN operational_blocks ON operational_blocks.id = crop_allocations.operational_block_id
           JOIN seasons ON seasons.id = crop_allocations.season_id
           WHERE crop_allocations.operating_unit_id = ?
           ORDER BY crop_allocations.created_at, crop_allocations.id""",
        (operating_unit_id,),
    ).fetchall()
    rows: List[Dict[str, Any]] = []
    for allocation in allocations:
        base = _base(allocation)
        allocation_id = allocation["allocation_id"]
        for record in conn.execute(
            "SELECT * FROM work_items WHERE allocation_id = ? ORDER BY due_at, created_at, id", (allocation_id,)
        ).fetchall():
            rows.append({
                "record_type": "work_item", "record_id": record["id"], **base,
                "record_status": record["status"], "recorded_at": record["due_at"],
                "owner_person_id": record["owner_id"], "summary": record["title"],
                "structured_values": "", "evidence_artifact_id": "",
            })
        for record in conn.execute(
            "SELECT * FROM exception_records WHERE allocation_id = ? ORDER BY observed_at, created_at, id", (allocation_id,)
        ).fetchall():
            rows.append({
                "record_type": "exception_record", "record_id": record["id"], **base,
                "record_status": record["status"], "recorded_at": record["observed_at"],
                "owner_person_id": record["owner_id"], "summary": record["title"],
                "structured_values": _json({"severity": record["severity"], "fallback_owner_id": record["fallback_owner_id"]}),
                "evidence_artifact_id": "",
            })
        for record in conn.execute(
            """SELECT field_signals.*, signal_templates.name AS template_name
               FROM field_signals
               JOIN signal_templates ON signal_templates.id = field_signals.template_id
               WHERE field_signals.allocation_id = ? AND field_signals.status != 'draft'
               ORDER BY field_signals.observed_at, field_signals.created_at, field_signals.id""",
            (allocation_id,),
        ).fetchall():
            rows.append({
                "record_type": "field_signal", "record_id": record["id"], **base,
                "record_status": record["status"], "recorded_at": record["observed_at"],
                "owner_person_id": record["actor_id"],
                "summary": "{0} v{1}".format(record["template_name"], record["template_version"]),
                "structured_values": record["values_json"],
                "evidence_artifact_id": record["evidence_artifact_id"] or "",
            })
        for record in conn.execute(
            "SELECT * FROM crop_stage_checkpoints WHERE allocation_id = ? ORDER BY planned_for, created_at, id", (allocation_id,)
        ).fetchall():
            rows.append({
                "record_type": "crop_stage_checkpoint", "record_id": record["id"], **base,
                "record_status": record["status"], "recorded_at": record["planned_for"],
                "owner_person_id": "", "summary": record["stage_name"],
                "structured_values": record["expected_evidence_json"], "evidence_artifact_id": "",
            })
        for record in conn.execute(
            "SELECT * FROM harvest_records WHERE allocation_id = ? ORDER BY harvest_starts_on, created_at, id", (allocation_id,)
        ).fetchall():
            rows.append({
                "record_type": "harvest_record", "record_id": record["id"], **base,
                "record_status": record["status"], "recorded_at": record["harvest_starts_on"],
                "owner_person_id": "", "summary": "{0} {1}".format(record["quantity"], record["canonical_unit"]),
                "structured_values": _json({
                    "harvest_ends_on": record["harvest_ends_on"],
                    "measurement_method": record["measurement_method"],
                    "quality_metrics": json.loads(record["quality_metrics_json"]),
                    "correction_of_id": record["correction_of_id"],
                }),
                "evidence_artifact_id": record["evidence_artifact_id"] or "",
            })
    return rows


def operating_ledger_csv(conn: sqlite3.Connection, operating_unit_id: str) -> str:
    """Render the canonical ledger as safe UTF-8 CSV with a stable column set."""
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=_COLUMNS, extrasaction="raise")
    writer.writeheader()
    for row in operating_ledger_rows(conn, operating_unit_id):
        writer.writerow({column: _cell(row[column]) for column in _COLUMNS})
    return stream.getvalue()
