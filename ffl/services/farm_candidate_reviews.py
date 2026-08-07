"""Registration-level review queue for safe Farm + Grower establishment.

This is intentionally adjacent to, not a shortcut through, Farm Truth: it
never creates a Field, plot geometry, crop allocation, acreage, or land right.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any, Mapping

from ffl.persistence import repository


_QUEUE_LIMIT = 100


def list_operating_units(conn) -> list[dict[str, str]]:
    rows = conn.execute("SELECT id, name FROM operating_units ORDER BY name, id").fetchall()
    return [{"id": row["id"], "name": row["name"]} for row in rows]


def refresh_cases(conn, limit: int = _QUEUE_LIMIT, registration_id: str | None = None) -> list[dict[str, Any]]:
    """Build allowlisted receipts from completed, valid registrations."""
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= _QUEUE_LIMIT:
        raise ValueError("limit must be between 1 and 100")
    sql = """SELECT registration.id AS registration_id, registration.source_id,
                  registration.source_fingerprint AS registration_fingerprint,
                  registration.village_name, registration.block_name, registration.district_name,
                  registration.reported_total_area_acres, registration.reported_plot_count,
                  farmer.display_name AS farmer_name,
                  COALESCE(registration_task.provider_completed_at,
                           registration_task.provider_created_at, registration_task.created_at) AS registered_at,
                  SUM(CASE WHEN work.task_status IN ('pending', 'in_progress') THEN 1 ELSE 0 END) AS open_work_count
           FROM trackwick_registrations AS registration
           JOIN trackwick_parties AS farmer ON farmer.id = registration.farmer_party_id
             AND farmer.source_id = registration.source_id
             AND farmer.party_kind = 'farmer' AND farmer.data_quality_status = 'valid'
           JOIN trackwick_tasks AS registration_task ON registration_task.id = registration.task_id
             AND registration_task.source_id = registration.source_id
             AND registration_task.task_status = 'completed' AND registration_task.data_quality_status = 'valid'
           LEFT JOIN trackwick_tasks AS work ON work.farmer_party_id = registration.farmer_party_id
             AND work.source_id = registration.source_id AND work.data_quality_status = 'valid'
           WHERE registration.registration_status = 'completed'
             AND registration.data_quality_status = 'valid'
             """ + ("AND registration.id = ?" if registration_id is not None else "") + """
           GROUP BY registration.id, registration.source_id, registration.source_fingerprint,
                    registration.village_name, registration.block_name, registration.district_name,
                    registration.reported_total_area_acres, registration.reported_plot_count,
                    farmer.display_name, registration_task.provider_completed_at,
                    registration_task.provider_created_at, registration_task.created_at
           ORDER BY registered_at DESC, registration.id"""
    rows = conn.execute(sql, (() if registration_id is None else (registration_id,))).fetchall()
    for row in rows:
        summary = _summary(row)
        repository.create_or_refresh_farm_candidate_review_case(
            conn, row["source_id"], row["registration_id"], _fingerprint(row), summary,
        )
    cases = repository.list_farm_candidate_review_cases(conn, "open", limit)
    if registration_id is not None:
        cases = [case for case in cases if case.registration_id == registration_id]
    return [_serialize(case) for case in cases]


def list_cases(conn, status: str = "open", limit: int = _QUEUE_LIMIT) -> list[dict[str, Any]]:
    return [_serialize(case) for case in repository.list_farm_candidate_review_cases(conn, status, limit)]


def _fingerprint(row: Mapping[str, Any]) -> str:
    material = json.dumps({
        "registration": row["registration_fingerprint"],
        "farmer": row["farmer_name"],
        "place": _place(row),
        "registered_at": row["registered_at"],
    }, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _place(row: Mapping[str, Any]) -> str:
    return ", ".join(str(value).strip() for value in (
        row["village_name"], row["block_name"], row["district_name"],
    ) if isinstance(value, str) and value.strip()) or "Reported place not available"


def _summary(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "farm_name_suggestion": _place(row),
        "farmer_name": row["farmer_name"],
        "registered_at": row["registered_at"],
        "reported_plot_count": row["reported_plot_count"],
        "reported_area_acres": row["reported_total_area_acres"],
        "open_source_work_count": int(row["open_work_count"] or 0),
        "limitations": [
            "This approval creates a Farm and reviewed Grower relationship only.",
            "No Field, boundary, crop, area, ownership, or right-to-operate is created.",
        ],
    }


def _serialize(case: repository.FarmCandidateReviewCase) -> dict[str, Any]:
    summary = dict(case.evidence_summary)
    return {
        "id": case.id, "status": case.status, "updated_at": case.updated_at,
        "farm_name_suggestion": summary.get("farm_name_suggestion"),
        "farmer_name": summary.get("farmer_name"), "registered_at": summary.get("registered_at"),
        "reported_plot_count": summary.get("reported_plot_count"),
        "reported_area_acres": summary.get("reported_area_acres"),
        "open_source_work_count": summary.get("open_source_work_count"),
        "limitations": summary.get("limitations", []),
        "accepted_farm_id": case.accepted_farm_id,
        "accepted_grower_person_id": case.accepted_grower_person_id,
    }
