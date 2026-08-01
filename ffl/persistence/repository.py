import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple

from ffl.domain.models import (
    AuditEvent,
    CropStageCheckpoint,
    CropAllocation,
    Decision,
    EvidenceArtifact,
    ExceptionRecord,
    FieldSignal,
    HarvestRecord,
    ImportBatch,
    ImportRow,
    LandParcel,
    OperatingUnit,
    OperationalBlock,
    Person,
    Playbook,
    RegionalSignal,
    RightToOperate,
    Season,
    SeasonReview,
    SignalTemplate,
    SourceRegistry,
    SourceRun,
    Trial,
    TrialAllocation,
    TrialConclusion,
    TrialConfounder,
    WorkItem,
)


def _new_identity() -> Tuple[str, str]:
    return str(uuid.uuid4()), datetime.now(timezone.utc).isoformat()


def _json_value(value: object) -> str:
    """Persist JSON columns consistently while accepting normal Python values."""
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except ValueError as exc:
        raise ValueError("JSON values must not contain NaN or infinity") from exc


def _validate_content_hash(content_hash: str) -> None:
    if re.fullmatch(r"[0-9a-f]{64}", content_hash) is None:
        raise ValueError("content_hash must be a lowercase SHA-256 hex digest")


def _validate_credentials_reference(credentials_reference: Optional[str]) -> None:
    if credentials_reference is None:
        return
    if re.fullmatch(r"(?:secret|env)://[A-Za-z0-9][A-Za-z0-9._/-]*", credentials_reference) is None:
        raise ValueError("credentials_reference must be a non-secret secret:// or env:// identifier")


def _require_published_template(conn: sqlite3.Connection, template_id: str, template_version: int) -> None:
    row = conn.execute(
        "SELECT status FROM signal_templates WHERE id = ? AND version = ?",
        (template_id, template_version),
    ).fetchone()
    if row is None:
        raise ValueError("signal template ID and version do not match")
    if row["status"] != "published":
        raise ValueError("signal template must be published")


def _validate_import_lifecycle(
    status: str, reviewed_at: Optional[str], reviewed_by_id: Optional[str], published_at: Optional[str]
) -> None:
    if status in ("received", "profiled") and any((reviewed_at, reviewed_by_id, published_at)):
        raise ValueError("received and profiled imports cannot have review or publish timestamps")
    if status == "review" and (reviewed_at is None or reviewed_by_id is None or published_at is not None):
        raise ValueError("review imports require reviewed_at and reviewed_by_id and cannot have published_at")
    if status == "published" and (reviewed_at is None or reviewed_by_id is None or published_at is None):
        raise ValueError("published imports require reviewed_at, reviewed_by_id, and published_at")
    if status in ("quarantined", "failed") and published_at is not None:
        raise ValueError("quarantined and failed imports cannot have published_at")


def _operating_unit(row: sqlite3.Row) -> OperatingUnit:
    return OperatingUnit(row["id"], row["name"], row["created_at"])


def _land_parcel(row: sqlite3.Row) -> LandParcel:
    return LandParcel(
        row["id"], row["operating_unit_id"], row["name"], row["area_hectares"], row["created_at"]
    )


def _operational_block(row: sqlite3.Row) -> OperationalBlock:
    return OperationalBlock(
        row["id"], row["operating_unit_id"], row["name"], row["area_hectares"], row["created_at"]
    )


def _right_to_operate(row: sqlite3.Row) -> RightToOperate:
    return RightToOperate(
        row["id"], row["land_parcel_id"], row["right_type"], row["starts_on"], row["ends_on"], row["created_at"]
    )


def _season(row: sqlite3.Row) -> Season:
    return Season(
        row["id"], row["operating_unit_id"], row["name"], row["starts_on"], row["ends_on"], row["created_at"]
    )


def _crop_allocation(row: sqlite3.Row) -> CropAllocation:
    return CropAllocation(
        row["id"], row["operating_unit_id"], row["operational_block_id"], row["season_id"],
        row["crop_name"], row["cultivar"], row["area_hectares"], row["status"], row["created_at"]
    )


def _person(row: sqlite3.Row) -> Person:
    return Person(row["id"], row["name"], row["role"], row["created_at"])


def _signal_template(row: sqlite3.Row) -> SignalTemplate:
    return SignalTemplate(
        row["id"], row["name"], row["version"], row["status"],
        json.loads(row["fields_json"]), row["owner_id"], row["published_at"],
    )


def _work_item(row: sqlite3.Row) -> WorkItem:
    return WorkItem(
        row["id"], row["allocation_id"], row["title"], row["owner_id"],
        row["due_at"], row["status"], row["created_at"],
    )


def _exception_record(row: sqlite3.Row) -> ExceptionRecord:
    return ExceptionRecord(
        row["id"], row["allocation_id"], row["title"], row["severity"],
        row["owner_id"], row["fallback_owner_id"], row["observed_at"],
        row["idempotency_key"], row["status"], row["created_at"],
    )


def _decision(row: sqlite3.Row) -> Decision:
    return Decision(
        row["id"], row["allocation_id"], row["title"], row["owner_id"],
        row["review_due_at"], row["status"], row["created_at"],
    )


def _audit_event(row: sqlite3.Row) -> AuditEvent:
    return AuditEvent(
        row["id"], row["entity_type"], row["entity_id"], row["from_status"],
        row["to_status"], row["actor_id"], row["reason"], row["created_at"],
    )


def _evidence_artifact(row: sqlite3.Row) -> EvidenceArtifact:
    return EvidenceArtifact(
        row["id"], row["content_hash"], row["media_type"], row["storage_reference"],
        row["original_filename"], row["size_bytes"], row["source_uri"],
        row["created_by_person_id"], row["created_at"],
    )


def _field_signal(row: sqlite3.Row) -> FieldSignal:
    return FieldSignal(
        row["id"], row["allocation_id"], row["template_id"], row["template_version"],
        row["observed_at"], row["received_at"], row["actor_id"], row["evidence_artifact_id"],
        json.loads(row["values_json"]), row["status"], row["supersedes_signal_id"], row["created_at"],
    )


def _crop_stage_checkpoint(row: sqlite3.Row) -> CropStageCheckpoint:
    return CropStageCheckpoint(
        row["id"], row["allocation_id"], row["stage_name"], row["planned_for"], row["status"],
        json.loads(row["expected_evidence_json"]), row["template_id"], row["template_version"],
        row["completed_at"], row["supersedes_checkpoint_id"], row["created_at"],
    )


def _harvest_record(row: sqlite3.Row) -> HarvestRecord:
    return HarvestRecord(
        row["id"], row["allocation_id"], row["harvest_starts_on"], row["harvest_ends_on"],
        row["quantity"], row["canonical_unit"], row["measurement_method"],
        json.loads(row["quality_metrics_json"]), row["evidence_artifact_id"], row["status"],
        row["correction_of_id"], row["corrected_by_person_id"], row["correction_reason"], row["created_at"],
    )


def _season_review(row: sqlite3.Row) -> SeasonReview:
    return SeasonReview(
        row["id"], row["allocation_id"], row["owner_id"],
        json.loads(row["confirmed_practices_json"]),
        json.loads(row["invalidated_assumptions_json"]),
        json.loads(row["unresolved_questions_json"]),
        json.loads(row["proposed_playbook_changes_json"]), row["status"], row["reviewed_at"], row["created_at"],
    )


def _source_registry(row: sqlite3.Row) -> SourceRegistry:
    return SourceRegistry(
        row["id"], row["source_key"], row["display_name"], row["source_type"], row["purpose"],
        row["authority_level"], row["owner_id"], row["credentials_reference"], row["endpoint"],
        json.loads(row["permitted_data_classes_json"]), row["freshness_target_hours"],
        row["license_notes"], row["schema_version"], row["mapping_version"],
        json.loads(row["default_coverage_json"]), bool(row["enabled"]), row["created_at"],
    )


def _source_run(row: sqlite3.Row) -> SourceRun:
    return SourceRun(
        row["id"], row["source_id"], row["cursor"], json.loads(row["coverage_json"]),
        row["fetched_at"], row["status"], row["rows_received"], row["rows_accepted"],
        row["error_summary"], row["next_retry_at"], row["mapping_version"], row["created_at"],
    )


def _regional_signal(row: sqlite3.Row) -> RegionalSignal:
    return RegionalSignal(
        row["id"], row["source_id"], row["source_run_id"], row["source_identifier"], row["source_url"],
        row["region"], row["signal_type"], row["observed_at"], row["received_at"], row["valid_from"],
        row["valid_to"], json.loads(row["coverage_json"]), row["resolution"],
        row["freshness_target_hours"], row["signal_kind"], json.loads(row["value_json"]), row["status"],
        row["created_at"],
    )


def _import_batch(row: sqlite3.Row) -> ImportBatch:
    return ImportBatch(
        row["id"], row["purpose"], row["status"], row["content_hash"], row["evidence_artifact_id"],
        row["mapping_version"], row["source_id"], row["owner_id"], row["received_at"],
        row["reviewed_at"], row["reviewed_by_id"], row["published_at"], json.loads(row["profile_json"]),
        row["created_at"],
    )


def _import_row(row: sqlite3.Row) -> ImportRow:
    return ImportRow(
        row["id"], row["import_batch_id"], row["row_number"], json.loads(row["raw_json"]),
        json.loads(row["mapped_json"]), row["status"], json.loads(row["validation_errors_json"]),
        row["target_entity_type"], row["target_entity_id"], row["published_record_id"], row["created_at"],
    )


def _playbook(row: sqlite3.Row) -> Playbook:
    return Playbook(
        row["id"], row["name"], row["version"], row["status"], row["owner_id"],
        json.loads(row["protocol_json"]), row["effective_from"], row["approved_by_person_id"],
        row["approved_at"], row["created_at"],
    )


def _trial(row: sqlite3.Row) -> Trial:
    return Trial(
        row["id"], row["name"], row["hypothesis"], row["owner_id"], row["protocol_version"],
        row["decision_question"], json.loads(row["treatment_json"]), json.loads(row["comparator_json"]),
        json.loads(row["eligibility_rule_json"]), json.loads(row["measurements_json"]),
        json.loads(row["guardrails_json"]), row["status"], row["starts_on"], row["ends_on"],
        row["status_reason"], row["created_at"],
    )


def _trial_allocation(row: sqlite3.Row) -> TrialAllocation:
    return TrialAllocation(
        row["id"], row["trial_id"], row["allocation_id"], row["arm"], row["status"],
        row["enrolled_at"], row["withdrawn_at"], row["reason"], row["created_at"],
    )


def _trial_confounder(row: sqlite3.Row) -> TrialConfounder:
    return TrialConfounder(
        row["id"], row["trial_id"], row["allocation_id"], row["category"], row["description"],
        row["observed_at"], row["evidence_artifact_id"], row["actor_id"], row["created_at"],
    )


def _trial_conclusion(row: sqlite3.Row) -> TrialConclusion:
    return TrialConclusion(
        row["id"], row["trial_id"], row["reviewer_id"], row["status"], json.loads(row["result_json"]),
        row["confidence_level"], json.loads(row["limitations_json"]), row["evidence_artifact_id"],
        row["playbook_id"], row["playbook_decision"], row["approved_at"], row["created_at"],
    )


def create_operating_unit(conn: sqlite3.Connection, name: str) -> OperatingUnit:
    identifier, created_at = _new_identity()
    conn.execute("INSERT INTO operating_units VALUES (?, ?, ?)", (identifier, name, created_at))
    conn.commit()
    return OperatingUnit(identifier, name, created_at)


def create_land_parcel(conn: sqlite3.Connection, operating_unit_id: str, name: str, area_hectares: float) -> LandParcel:
    identifier, created_at = _new_identity()
    conn.execute(
        "INSERT INTO land_parcels VALUES (?, ?, ?, ?, ?)",
        (identifier, operating_unit_id, name, area_hectares, created_at),
    )
    conn.commit()
    return LandParcel(identifier, operating_unit_id, name, area_hectares, created_at)


def create_operational_block(conn: sqlite3.Connection, operating_unit_id: str, name: str, area_hectares: float) -> OperationalBlock:
    identifier, created_at = _new_identity()
    conn.execute(
        "INSERT INTO operational_blocks VALUES (?, ?, ?, ?, ?)",
        (identifier, operating_unit_id, name, area_hectares, created_at),
    )
    conn.commit()
    return OperationalBlock(identifier, operating_unit_id, name, area_hectares, created_at)


def link_block_parcel(conn: sqlite3.Connection, operational_block_id: str, land_parcel_id: str) -> None:
    _, created_at = _new_identity()
    conn.execute(
        "INSERT INTO block_parcels VALUES (?, ?, ?)",
        (operational_block_id, land_parcel_id, created_at),
    )
    conn.commit()


def create_right_to_operate(conn: sqlite3.Connection, land_parcel_id: str, right_type: str, starts_on: str, ends_on: str) -> RightToOperate:
    identifier, created_at = _new_identity()
    conn.execute(
        "INSERT INTO rights_to_operate VALUES (?, ?, ?, ?, ?, ?)",
        (identifier, land_parcel_id, right_type, starts_on, ends_on, created_at),
    )
    conn.commit()
    return RightToOperate(identifier, land_parcel_id, right_type, starts_on, ends_on, created_at)


def create_season(conn: sqlite3.Connection, operating_unit_id: str, name: str, starts_on: str, ends_on: str) -> Season:
    identifier, created_at = _new_identity()
    conn.execute(
        "INSERT INTO seasons VALUES (?, ?, ?, ?, ?, ?)",
        (identifier, operating_unit_id, name, starts_on, ends_on, created_at),
    )
    conn.commit()
    return Season(identifier, operating_unit_id, name, starts_on, ends_on, created_at)


def create_crop_allocation(
    conn: sqlite3.Connection,
    operating_unit_id: str,
    operational_block_id: str,
    season_id: str,
    crop_name: str,
    cultivar: Optional[str],
    area_hectares: float,
) -> CropAllocation:
    block_row = conn.execute(
        "SELECT * FROM operational_blocks WHERE id = ?", (operational_block_id,)
    ).fetchone()
    if block_row is None:
        raise ValueError("operational block does not exist")
    block = _operational_block(block_row)
    allocated = conn.execute(
        """SELECT COALESCE(SUM(area_hectares), 0) FROM crop_allocations
           WHERE operational_block_id = ? AND season_id = ? AND status = 'active'""",
        (operational_block_id, season_id),
    ).fetchone()[0]
    if allocated + area_hectares > block.area_hectares:
        raise ValueError("crop allocation exceeds available block area")

    identifier, created_at = _new_identity()
    status = "active"
    conn.execute(
        "INSERT INTO crop_allocations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (identifier, operating_unit_id, operational_block_id, season_id, crop_name, cultivar, area_hectares, status, created_at),
    )
    conn.commit()
    return CropAllocation(
        identifier, operating_unit_id, operational_block_id, season_id, crop_name, cultivar,
        area_hectares, status, created_at,
    )


def create_person(conn: sqlite3.Connection, name: str, role: str) -> Person:
    identifier, created_at = _new_identity()
    conn.execute("INSERT INTO people VALUES (?, ?, ?, ?)", (identifier, name, role, created_at))
    conn.commit()
    return Person(identifier, name, role, created_at)


def create_signal_template(
    conn: sqlite3.Connection, name: str, version: int, status: str, fields_json: str,
    owner_id: str, published_at: str,
) -> SignalTemplate:
    identifier, _ = _new_identity()
    conn.execute(
        "INSERT INTO signal_templates VALUES (?, ?, ?, ?, ?, ?, ?)",
        (identifier, name, version, status, fields_json, owner_id, published_at),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM signal_templates WHERE id = ?", (identifier,)).fetchone()
    return _signal_template(row)


def get_signal_template(
    conn: sqlite3.Connection, name: str, version: int
) -> Optional[SignalTemplate]:
    row = conn.execute(
        "SELECT * FROM signal_templates WHERE name = ? AND version = ?", (name, version)
    ).fetchone()
    return _signal_template(row) if row is not None else None


def list_active_crop_allocations(conn: sqlite3.Connection, operating_unit_id: str) -> List[CropAllocation]:
    rows = conn.execute(
        "SELECT * FROM crop_allocations WHERE operating_unit_id = ? AND status = 'active' ORDER BY created_at",
        (operating_unit_id,),
    ).fetchall()
    return [_crop_allocation(row) for row in rows]


def create_work_item(
    conn: sqlite3.Connection, allocation_id: str, title: str, owner_id: str, due_at: str,
    initial_status: str = "in_progress",
) -> WorkItem:
    identifier, created_at = _new_identity()
    conn.execute(
        "INSERT INTO work_items VALUES (?, ?, ?, ?, ?, ?, ?)",
        (identifier, allocation_id, title, owner_id, due_at, initial_status, created_at),
    )
    conn.commit()
    return WorkItem(identifier, allocation_id, title, owner_id, due_at, initial_status, created_at)


def get_work_item(conn: sqlite3.Connection, work_item_id: str) -> Optional[WorkItem]:
    row = conn.execute("SELECT * FROM work_items WHERE id = ?", (work_item_id,)).fetchone()
    return _work_item(row) if row is not None else None


def list_work_items(conn: sqlite3.Connection, allocation_id: str) -> List[WorkItem]:
    rows = conn.execute(
        "SELECT * FROM work_items WHERE allocation_id = ? ORDER BY created_at", (allocation_id,)
    ).fetchall()
    return [_work_item(row) for row in rows]


def transition_work_item_with_audit(
    conn: sqlite3.Connection, work_item_id: str, from_status: str, to_status: str,
    actor_id: str, reason: str,
) -> WorkItem:
    audit_id, created_at = _new_identity()
    with conn:
        conn.execute("UPDATE work_items SET status = ? WHERE id = ?", (to_status, work_item_id))
        conn.execute(
            "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (audit_id, "work_item", work_item_id, from_status, to_status, actor_id, reason, created_at),
        )
    return get_work_item(conn, work_item_id)  # type: ignore[return-value]


def get_exception_by_idempotency_key(
    conn: sqlite3.Connection, idempotency_key: str
) -> Optional[ExceptionRecord]:
    row = conn.execute(
        "SELECT * FROM exception_records WHERE idempotency_key = ?", (idempotency_key,)
    ).fetchone()
    return _exception_record(row) if row is not None else None


def create_exception_record(
    conn: sqlite3.Connection, allocation_id: str, title: str, severity: str, owner_id: str,
    fallback_owner_id: str, observed_at: str, idempotency_key: str,
) -> ExceptionRecord:
    identifier, created_at = _new_identity()
    status = "reported"
    try:
        conn.execute(
            "INSERT INTO exception_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (identifier, allocation_id, title, severity, owner_id, fallback_owner_id, observed_at,
             idempotency_key, status, created_at),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        row = conn.execute(
            "SELECT * FROM exception_records WHERE idempotency_key = ?", (idempotency_key,)
        ).fetchone()
        if row is None:
            raise
        return _exception_record(row)
    return ExceptionRecord(identifier, allocation_id, title, severity, owner_id, fallback_owner_id,
                           observed_at, idempotency_key, status, created_at)


def get_exception_record(conn: sqlite3.Connection, exception_id: str) -> Optional[ExceptionRecord]:
    row = conn.execute("SELECT * FROM exception_records WHERE id = ?", (exception_id,)).fetchone()
    return _exception_record(row) if row is not None else None


def transition_exception_with_audit(
    conn: sqlite3.Connection, exception_id: str, from_status: str, to_status: str,
    actor_id: str, reason: str,
) -> ExceptionRecord:
    audit_id, created_at = _new_identity()
    with conn:
        conn.execute("UPDATE exception_records SET status = ? WHERE id = ?", (to_status, exception_id))
        conn.execute(
            "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (audit_id, "exception_record", exception_id, from_status, to_status, actor_id, reason, created_at),
        )
    return get_exception_record(conn, exception_id)  # type: ignore[return-value]


def create_decision(
    conn: sqlite3.Connection, allocation_id: str, title: str, owner_id: str, review_due_at: str
) -> Decision:
    identifier, created_at = _new_identity()
    status = "open"
    conn.execute(
        "INSERT INTO decisions VALUES (?, ?, ?, ?, ?, ?, ?)",
        (identifier, allocation_id, title, owner_id, review_due_at, status, created_at),
    )
    conn.commit()
    return Decision(identifier, allocation_id, title, owner_id, review_due_at, status, created_at)


def create_audit_event(
    conn: sqlite3.Connection, entity_type: str, entity_id: str, from_status: str,
    to_status: str, actor_id: str, reason: str,
) -> AuditEvent:
    identifier, created_at = _new_identity()
    conn.execute(
        "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (identifier, entity_type, entity_id, from_status, to_status, actor_id, reason, created_at),
    )
    conn.commit()
    return AuditEvent(identifier, entity_type, entity_id, from_status, to_status, actor_id, reason, created_at)


def list_audit_events(conn: sqlite3.Connection, entity_type: str, entity_id: str) -> List[AuditEvent]:
    rows = conn.execute(
        "SELECT * FROM audit_events WHERE entity_type = ? AND entity_id = ? ORDER BY rowid",
        (entity_type, entity_id),
    ).fetchall()
    return [_audit_event(row) for row in rows]


# V1 shared records. These helpers deliberately only append records; publishing,
# approval, and adapter workflows belong to the dependent service layers.
def create_evidence_artifact(
    conn: sqlite3.Connection, content_hash: str, media_type: str, storage_reference: str,
    original_filename: Optional[str] = None, size_bytes: Optional[int] = None,
    source_uri: Optional[str] = None, created_by_person_id: Optional[str] = None,
) -> EvidenceArtifact:
    _validate_content_hash(content_hash)
    identifier, created_at = _new_identity()
    try:
        conn.execute(
            """INSERT INTO evidence_artifacts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (identifier, content_hash, media_type, storage_reference, original_filename, size_bytes,
             source_uri, created_by_person_id, created_at),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        existing = get_evidence_artifact_by_hash(conn, content_hash)
        if existing is None:
            raise
        return existing
    return EvidenceArtifact(identifier, content_hash, media_type, storage_reference, original_filename,
                            size_bytes, source_uri, created_by_person_id, created_at)


def create_evidence_artifact_if_absent(
    conn: sqlite3.Connection, content_hash: str, media_type: str, storage_reference: str,
    original_filename: Optional[str] = None, size_bytes: Optional[int] = None,
    source_uri: Optional[str] = None, created_by_person_id: Optional[str] = None,
) -> Tuple[EvidenceArtifact, bool]:
    """Atomically insert a content-addressed artifact and report whether this call won."""
    _validate_content_hash(content_hash)
    identifier, created_at = _new_identity()
    cursor = conn.execute(
        """INSERT OR IGNORE INTO evidence_artifacts
           (id, content_hash, media_type, storage_reference, original_filename, size_bytes, source_uri,
            created_by_person_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (identifier, content_hash, media_type, storage_reference, original_filename, size_bytes,
         source_uri, created_by_person_id, created_at),
    )
    conn.commit()
    artifact = get_evidence_artifact_by_hash(conn, content_hash)
    if artifact is None:
        raise RuntimeError("evidence artifact insert did not return a record")
    return artifact, cursor.rowcount == 1


def get_evidence_artifact(conn: sqlite3.Connection, artifact_id: str) -> Optional[EvidenceArtifact]:
    row = conn.execute("SELECT * FROM evidence_artifacts WHERE id = ?", (artifact_id,)).fetchone()
    return _evidence_artifact(row) if row is not None else None


def get_evidence_artifact_by_hash(conn: sqlite3.Connection, content_hash: str) -> Optional[EvidenceArtifact]:
    row = conn.execute("SELECT * FROM evidence_artifacts WHERE content_hash = ?", (content_hash,)).fetchone()
    return _evidence_artifact(row) if row is not None else None


def list_evidence_artifacts(conn: sqlite3.Connection) -> List[EvidenceArtifact]:
    return [_evidence_artifact(row) for row in conn.execute(
        "SELECT * FROM evidence_artifacts ORDER BY created_at"
    ).fetchall()]


def create_field_signal(
    conn: sqlite3.Connection, allocation_id: str, template_id: str, template_version: int,
    observed_at: str, actor_id: str, values: Any, evidence_artifact_id: Optional[str] = None,
    status: str = "submitted", received_at: Optional[str] = None,
    supersedes_signal_id: Optional[str] = None,
) -> FieldSignal:
    _require_published_template(conn, template_id, template_version)
    identifier, created_at = _new_identity()
    received_at = received_at or created_at
    conn.execute(
        "INSERT INTO field_signals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (identifier, allocation_id, template_id, template_version, observed_at, received_at, actor_id,
         evidence_artifact_id, _json_value(values), status, supersedes_signal_id, created_at),
    )
    conn.commit()
    return get_field_signal(conn, identifier)  # type: ignore[return-value]


def get_field_signal(conn: sqlite3.Connection, signal_id: str) -> Optional[FieldSignal]:
    row = conn.execute("SELECT * FROM field_signals WHERE id = ?", (signal_id,)).fetchone()
    return _field_signal(row) if row is not None else None


def list_field_signals(conn: sqlite3.Connection, allocation_id: str) -> List[FieldSignal]:
    return [_field_signal(row) for row in conn.execute(
        "SELECT * FROM field_signals WHERE allocation_id = ? ORDER BY observed_at, created_at", (allocation_id,)
    ).fetchall()]


def create_crop_stage_checkpoint(
    conn: sqlite3.Connection, allocation_id: str, stage_name: str, planned_for: str,
    expected_evidence: Any, template_id: Optional[str] = None, template_version: Optional[int] = None,
    status: str = "planned", completed_at: Optional[str] = None,
    supersedes_checkpoint_id: Optional[str] = None,
) -> CropStageCheckpoint:
    if (template_id is None) != (template_version is None):
        raise ValueError("template ID and version must be supplied together")
    if template_id is not None and template_version is not None:
        _require_published_template(conn, template_id, template_version)
    identifier, created_at = _new_identity()
    conn.execute(
        "INSERT INTO crop_stage_checkpoints VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (identifier, allocation_id, stage_name, planned_for, status, _json_value(expected_evidence), template_id,
         template_version, completed_at, supersedes_checkpoint_id, created_at),
    )
    conn.commit()
    return get_crop_stage_checkpoint(conn, identifier)  # type: ignore[return-value]


def get_crop_stage_checkpoint(conn: sqlite3.Connection, checkpoint_id: str) -> Optional[CropStageCheckpoint]:
    row = conn.execute("SELECT * FROM crop_stage_checkpoints WHERE id = ?", (checkpoint_id,)).fetchone()
    return _crop_stage_checkpoint(row) if row is not None else None


def list_crop_stage_checkpoints(conn: sqlite3.Connection, allocation_id: str) -> List[CropStageCheckpoint]:
    return [_crop_stage_checkpoint(row) for row in conn.execute(
        "SELECT * FROM crop_stage_checkpoints WHERE allocation_id = ? ORDER BY planned_for, created_at", (allocation_id,)
    ).fetchall()]


def create_harvest_record(
    conn: sqlite3.Connection, allocation_id: str, harvest_starts_on: str, quantity: float,
    canonical_unit: str, measurement_method: str, quality_metrics: Any,
    harvest_ends_on: Optional[str] = None, evidence_artifact_id: Optional[str] = None,
    status: str = "preliminary", correction_of_id: Optional[str] = None,
    corrected_by_person_id: Optional[str] = None, correction_reason: Optional[str] = None,
) -> HarvestRecord:
    if correction_of_id is not None and status != "corrected":
        raise ValueError("a harvest correction must use corrected status")
    if correction_of_id is None and status == "corrected":
        raise ValueError("corrected status requires correction_of_id")
    if correction_of_id is None and any((corrected_by_person_id, correction_reason)):
        raise ValueError("correction actor and reason require correction_of_id")
    if correction_of_id is not None:
        prior = get_harvest_record(conn, correction_of_id)
        if prior is None:
            raise ValueError("prior harvest record does not exist")
        if prior.allocation_id != allocation_id:
            raise ValueError("harvest correction must use the predecessor allocation")
    identifier, created_at = _new_identity()
    conn.execute(
        "INSERT INTO harvest_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (identifier, allocation_id, harvest_starts_on, harvest_ends_on, quantity, canonical_unit,
         measurement_method, _json_value(quality_metrics), evidence_artifact_id, status, correction_of_id,
         corrected_by_person_id, correction_reason, created_at),
    )
    conn.commit()
    return get_harvest_record(conn, identifier)  # type: ignore[return-value]


def create_harvest_correction(
    conn: sqlite3.Connection, prior_record_id: str, corrected_by_person_id: str, correction_reason: str,
    quantity: float, quality_metrics: Any, harvest_starts_on: Optional[str] = None,
    harvest_ends_on: Optional[str] = None, canonical_unit: Optional[str] = None,
    measurement_method: Optional[str] = None, evidence_artifact_id: Optional[str] = None,
) -> HarvestRecord:
    prior = get_harvest_record(conn, prior_record_id)
    if prior is None:
        raise ValueError("prior harvest record does not exist")
    return create_harvest_record(
        conn, prior.allocation_id, harvest_starts_on or prior.harvest_starts_on, quantity,
        canonical_unit or prior.canonical_unit, measurement_method or prior.measurement_method, quality_metrics,
        harvest_ends_on=harvest_ends_on if harvest_ends_on is not None else prior.harvest_ends_on,
        evidence_artifact_id=evidence_artifact_id, status="corrected", correction_of_id=prior.id,
        corrected_by_person_id=corrected_by_person_id, correction_reason=correction_reason,
    )


def get_harvest_record(conn: sqlite3.Connection, harvest_record_id: str) -> Optional[HarvestRecord]:
    row = conn.execute("SELECT * FROM harvest_records WHERE id = ?", (harvest_record_id,)).fetchone()
    return _harvest_record(row) if row is not None else None


def list_harvest_records(conn: sqlite3.Connection, allocation_id: str) -> List[HarvestRecord]:
    return [_harvest_record(row) for row in conn.execute(
        "SELECT * FROM harvest_records WHERE allocation_id = ? ORDER BY created_at", (allocation_id,)
    ).fetchall()]


def create_season_review(
    conn: sqlite3.Connection, allocation_id: str, owner_id: str, confirmed_practices: Any,
    invalidated_assumptions: Any, unresolved_questions: Any, proposed_playbook_changes: Any,
    status: str = "draft", reviewed_at: Optional[str] = None,
) -> SeasonReview:
    identifier, created_at = _new_identity()
    conn.execute(
        "INSERT INTO season_reviews VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (identifier, allocation_id, owner_id, _json_value(confirmed_practices), _json_value(invalidated_assumptions),
         _json_value(unresolved_questions), _json_value(proposed_playbook_changes), status, reviewed_at, created_at),
    )
    conn.commit()
    return get_season_review(conn, identifier)  # type: ignore[return-value]


def get_season_review(conn: sqlite3.Connection, review_id: str) -> Optional[SeasonReview]:
    row = conn.execute("SELECT * FROM season_reviews WHERE id = ?", (review_id,)).fetchone()
    return _season_review(row) if row is not None else None


def list_season_reviews(conn: sqlite3.Connection, allocation_id: str) -> List[SeasonReview]:
    return [_season_review(row) for row in conn.execute(
        "SELECT * FROM season_reviews WHERE allocation_id = ? ORDER BY created_at", (allocation_id,)
    ).fetchall()]


def create_source_registry(
    conn: sqlite3.Connection, source_key: str, display_name: str, source_type: str, purpose: str,
    authority_level: str, owner_id: str, permitted_data_classes: Any, schema_version: str,
    mapping_version: str, default_coverage: Any, credentials_reference: Optional[str] = None,
    endpoint: Optional[str] = None, freshness_target_hours: Optional[float] = None,
    license_notes: Optional[str] = None, enabled: bool = False,
) -> SourceRegistry:
    _validate_credentials_reference(credentials_reference)
    identifier, created_at = _new_identity()
    try:
        conn.execute(
            """INSERT INTO source_registry VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (identifier, source_key, display_name, source_type, purpose, authority_level, owner_id,
             credentials_reference, endpoint, _json_value(permitted_data_classes), freshness_target_hours,
             license_notes, schema_version, mapping_version, _json_value(default_coverage), int(enabled), created_at),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        existing = get_source_registry_by_key(conn, source_key)
        if existing is None:
            raise
        return existing
    return get_source_registry(conn, identifier)  # type: ignore[return-value]


def get_source_registry(conn: sqlite3.Connection, source_id: str) -> Optional[SourceRegistry]:
    row = conn.execute("SELECT * FROM source_registry WHERE id = ?", (source_id,)).fetchone()
    return _source_registry(row) if row is not None else None


def get_source_registry_by_key(conn: sqlite3.Connection, source_key: str) -> Optional[SourceRegistry]:
    row = conn.execute("SELECT * FROM source_registry WHERE source_key = ?", (source_key,)).fetchone()
    return _source_registry(row) if row is not None else None


def list_source_registry(conn: sqlite3.Connection) -> List[SourceRegistry]:
    return [_source_registry(row) for row in conn.execute(
        "SELECT * FROM source_registry ORDER BY source_key"
    ).fetchall()]


def create_source_run(
    conn: sqlite3.Connection, source_id: str, coverage: Any, mapping_version: str,
    status: str = "pending", cursor: Optional[str] = None, fetched_at: Optional[str] = None,
    rows_received: int = 0, rows_accepted: int = 0, error_summary: Optional[str] = None,
    next_retry_at: Optional[str] = None,
) -> SourceRun:
    identifier, created_at = _new_identity()
    conn.execute(
        "INSERT INTO source_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (identifier, source_id, cursor, _json_value(coverage), fetched_at, status, rows_received,
         rows_accepted, error_summary, next_retry_at, mapping_version, created_at),
    )
    conn.commit()
    return get_source_run(conn, identifier)  # type: ignore[return-value]


def get_source_run(conn: sqlite3.Connection, source_run_id: str) -> Optional[SourceRun]:
    row = conn.execute("SELECT * FROM source_runs WHERE id = ?", (source_run_id,)).fetchone()
    return _source_run(row) if row is not None else None


def list_source_runs(conn: sqlite3.Connection, source_id: str) -> List[SourceRun]:
    return [_source_run(row) for row in conn.execute(
        "SELECT * FROM source_runs WHERE source_id = ? ORDER BY created_at", (source_id,)
    ).fetchall()]


def create_regional_signal(
    conn: sqlite3.Connection, source_id: str, source_identifier: str, region: str, signal_type: str,
    observed_at: str, value: Any, coverage: Any, signal_kind: str,
    source_run_id: Optional[str] = None, source_url: Optional[str] = None,
    received_at: Optional[str] = None, valid_from: Optional[str] = None, valid_to: Optional[str] = None,
    resolution: Optional[str] = None, freshness_target_hours: Optional[float] = None,
    status: str = "available",
) -> RegionalSignal:
    if source_run_id is not None:
        source_run = get_source_run(conn, source_run_id)
        if source_run is None:
            raise ValueError("source run does not exist")
        if source_run.source_id != source_id:
            raise ValueError("regional signal source_run must belong to source_id")
    identifier, created_at = _new_identity()
    received_at = received_at or created_at
    conn.execute(
        """INSERT INTO regional_signals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (identifier, source_id, source_run_id, source_identifier, source_url, region, signal_type, observed_at,
         received_at, valid_from, valid_to, _json_value(coverage), resolution, freshness_target_hours,
         signal_kind, _json_value(value), status, created_at),
    )
    conn.commit()
    return get_regional_signal(conn, identifier)  # type: ignore[return-value]


def get_regional_signal(conn: sqlite3.Connection, regional_signal_id: str) -> Optional[RegionalSignal]:
    row = conn.execute("SELECT * FROM regional_signals WHERE id = ?", (regional_signal_id,)).fetchone()
    return _regional_signal(row) if row is not None else None


def list_regional_signals(conn: sqlite3.Connection, region: str) -> List[RegionalSignal]:
    return [_regional_signal(row) for row in conn.execute(
        "SELECT * FROM regional_signals WHERE region = ? ORDER BY observed_at, created_at", (region,)
    ).fetchall()]


def create_import_batch(
    conn: sqlite3.Connection, purpose: str, content_hash: str, evidence_artifact_id: str,
    mapping_version: str, owner_id: str, profile: Any, status: str = "received",
    source_id: Optional[str] = None, received_at: Optional[str] = None,
    reviewed_at: Optional[str] = None, published_at: Optional[str] = None,
    reviewed_by_id: Optional[str] = None, commit: bool = True,
) -> ImportBatch:
    _validate_content_hash(content_hash)
    artifact = get_evidence_artifact(conn, evidence_artifact_id)
    if artifact is None:
        raise ValueError("evidence artifact does not exist")
    if artifact.content_hash != content_hash:
        raise ValueError("import content_hash must match its evidence artifact")
    _validate_import_lifecycle(status, reviewed_at, reviewed_by_id, published_at)
    identifier, created_at = _new_identity()
    received_at = received_at or created_at
    try:
        conn.execute(
            """INSERT INTO import_batches
               (id, purpose, status, content_hash, evidence_artifact_id, mapping_version, source_id, owner_id,
                received_at, reviewed_at, reviewed_by_id, published_at, profile_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (identifier, purpose, status, content_hash, evidence_artifact_id, mapping_version, source_id, owner_id,
             received_at, reviewed_at, reviewed_by_id, published_at, _json_value(profile), created_at),
        )
        if commit:
            conn.commit()
    except sqlite3.IntegrityError:
        if not commit:
            raise
        conn.rollback()
        existing = get_import_batch_by_content_hash(conn, content_hash)
        if existing is None:
            raise
        return existing
    return get_import_batch(conn, identifier)  # type: ignore[return-value]


def get_import_batch(conn: sqlite3.Connection, import_batch_id: str) -> Optional[ImportBatch]:
    row = conn.execute("SELECT * FROM import_batches WHERE id = ?", (import_batch_id,)).fetchone()
    return _import_batch(row) if row is not None else None


def get_import_batch_by_content_hash(conn: sqlite3.Connection, content_hash: str) -> Optional[ImportBatch]:
    row = conn.execute("SELECT * FROM import_batches WHERE content_hash = ?", (content_hash,)).fetchone()
    return _import_batch(row) if row is not None else None


def list_import_batches(conn: sqlite3.Connection, purpose: Optional[str] = None) -> List[ImportBatch]:
    if purpose is None:
        rows = conn.execute("SELECT * FROM import_batches ORDER BY received_at, created_at").fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM import_batches WHERE purpose = ? ORDER BY received_at, created_at", (purpose,)
        ).fetchall()
    return [_import_batch(row) for row in rows]


def create_import_row(
    conn: sqlite3.Connection, import_batch_id: str, row_number: int, raw: Any, mapped: Any,
    validation_errors: Any, status: str = "pending", target_entity_type: Optional[str] = None,
    target_entity_id: Optional[str] = None, published_record_id: Optional[str] = None, commit: bool = True,
) -> ImportRow:
    identifier, created_at = _new_identity()
    conn.execute(
        "INSERT INTO import_rows VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (identifier, import_batch_id, row_number, _json_value(raw), _json_value(mapped), status,
         _json_value(validation_errors), target_entity_type, target_entity_id, published_record_id, created_at),
    )
    if commit:
        conn.commit()
    return get_import_row(conn, identifier)  # type: ignore[return-value]


def get_import_row(conn: sqlite3.Connection, import_row_id: str) -> Optional[ImportRow]:
    row = conn.execute("SELECT * FROM import_rows WHERE id = ?", (import_row_id,)).fetchone()
    return _import_row(row) if row is not None else None


def list_import_rows(conn: sqlite3.Connection, import_batch_id: str) -> List[ImportRow]:
    return [_import_row(row) for row in conn.execute(
        "SELECT * FROM import_rows WHERE import_batch_id = ? ORDER BY row_number", (import_batch_id,)
    ).fetchall()]


def review_import_batch(
    conn: sqlite3.Connection, import_batch_id: str, reviewed_by_id: str, reviewed_at: str
) -> ImportBatch:
    """Move a profiled import into the human-review state without changing its rows."""
    batch = get_import_batch(conn, import_batch_id)
    if batch is None:
        raise ValueError("import batch does not exist")
    if batch.status == "review":
        if batch.reviewed_by_id != reviewed_by_id:
            raise ValueError("import batch was already reviewed by a different reviewer")
        return batch
    if batch.status != "profiled":
        raise ValueError("only profiled imports can be reviewed")
    conn.execute(
        "UPDATE import_batches SET status = ?, reviewed_at = ?, reviewed_by_id = ? WHERE id = ?",
        ("review", reviewed_at, reviewed_by_id, import_batch_id),
    )
    conn.commit()
    return get_import_batch(conn, import_batch_id)  # type: ignore[return-value]


def publish_import_batch(
    conn: sqlite3.Connection, import_batch_id: str, published_at: str
) -> ImportBatch:
    """Publish reviewed, wholly-valid rows atomically; no operating record is mutated here."""
    batch = get_import_batch(conn, import_batch_id)
    if batch is None:
        raise ValueError("import batch does not exist")
    if batch.status == "published":
        return batch
    if batch.status != "review":
        raise ValueError("only reviewed imports can be published")
    if batch.reviewed_by_id is None:
        raise ValueError("reviewed imports require a reviewer")
    bad_rows = conn.execute(
        "SELECT COUNT(*) AS count FROM import_rows WHERE import_batch_id = ? AND status != 'valid'",
        (import_batch_id,),
    ).fetchone()["count"]
    if bad_rows:
        raise ValueError("imports with invalid or quarantined rows cannot be published")
    if not list_import_rows(conn, import_batch_id):
        raise ValueError("imports without rows cannot be published")
    try:
        conn.execute(
            "UPDATE import_rows SET status = 'published' WHERE import_batch_id = ? AND status = 'valid'",
            (import_batch_id,),
        )
        conn.execute(
            "UPDATE import_batches SET status = ?, published_at = ? WHERE id = ?",
            ("published", published_at, import_batch_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return get_import_batch(conn, import_batch_id)  # type: ignore[return-value]


def create_playbook(
    conn: sqlite3.Connection, name: str, version: int, owner_id: str, protocol: Any,
    status: str = "draft", effective_from: Optional[str] = None,
    approved_by_person_id: Optional[str] = None, approved_at: Optional[str] = None,
) -> Playbook:
    identifier, created_at = _new_identity()
    conn.execute(
        "INSERT INTO playbooks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (identifier, name, version, status, owner_id, _json_value(protocol), effective_from,
         approved_by_person_id, approved_at, created_at),
    )
    conn.commit()
    return get_playbook(conn, identifier)  # type: ignore[return-value]


def get_playbook(conn: sqlite3.Connection, playbook_id: str) -> Optional[Playbook]:
    row = conn.execute("SELECT * FROM playbooks WHERE id = ?", (playbook_id,)).fetchone()
    return _playbook(row) if row is not None else None


def list_playbooks(conn: sqlite3.Connection, name: Optional[str] = None) -> List[Playbook]:
    if name is None:
        rows = conn.execute("SELECT * FROM playbooks ORDER BY name, version").fetchall()
    else:
        rows = conn.execute("SELECT * FROM playbooks WHERE name = ? ORDER BY version", (name,)).fetchall()
    return [_playbook(row) for row in rows]


def create_trial(
    conn: sqlite3.Connection, name: str, hypothesis: str, owner_id: str, protocol_version: str,
    decision_question: str, treatment: Any, comparator: Any, eligibility_rule: Any,
    measurements: Any, guardrails: Any, status: str = "draft", starts_on: Optional[str] = None,
    ends_on: Optional[str] = None, status_reason: Optional[str] = None,
) -> Trial:
    identifier, created_at = _new_identity()
    conn.execute(
        "INSERT INTO trials VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (identifier, name, hypothesis, owner_id, protocol_version, decision_question, _json_value(treatment),
         _json_value(comparator), _json_value(eligibility_rule), _json_value(measurements),
         _json_value(guardrails), status, starts_on, ends_on, status_reason, created_at),
    )
    conn.commit()
    return get_trial(conn, identifier)  # type: ignore[return-value]


def get_trial(conn: sqlite3.Connection, trial_id: str) -> Optional[Trial]:
    row = conn.execute("SELECT * FROM trials WHERE id = ?", (trial_id,)).fetchone()
    return _trial(row) if row is not None else None


def list_trials(conn: sqlite3.Connection, owner_id: Optional[str] = None) -> List[Trial]:
    if owner_id is None:
        rows = conn.execute("SELECT * FROM trials ORDER BY created_at").fetchall()
    else:
        rows = conn.execute("SELECT * FROM trials WHERE owner_id = ? ORDER BY created_at", (owner_id,)).fetchall()
    return [_trial(row) for row in rows]


def create_trial_allocation(
    conn: sqlite3.Connection, trial_id: str, allocation_id: str, arm: str,
    status: str = "enrolled", enrolled_at: Optional[str] = None,
    withdrawn_at: Optional[str] = None, reason: Optional[str] = None,
) -> TrialAllocation:
    identifier, created_at = _new_identity()
    enrolled_at = enrolled_at or created_at
    conn.execute(
        "INSERT INTO trial_allocations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (identifier, trial_id, allocation_id, arm, status, enrolled_at, withdrawn_at, reason, created_at),
    )
    conn.commit()
    return get_trial_allocation(conn, identifier)  # type: ignore[return-value]


def get_trial_allocation(conn: sqlite3.Connection, trial_allocation_id: str) -> Optional[TrialAllocation]:
    row = conn.execute("SELECT * FROM trial_allocations WHERE id = ?", (trial_allocation_id,)).fetchone()
    return _trial_allocation(row) if row is not None else None


def list_trial_allocations(conn: sqlite3.Connection, trial_id: str) -> List[TrialAllocation]:
    return [_trial_allocation(row) for row in conn.execute(
        "SELECT * FROM trial_allocations WHERE trial_id = ? ORDER BY created_at", (trial_id,)
    ).fetchall()]


def create_trial_confounder(
    conn: sqlite3.Connection, trial_id: str, category: str, description: str, observed_at: str,
    actor_id: str, allocation_id: Optional[str] = None, evidence_artifact_id: Optional[str] = None,
) -> TrialConfounder:
    if allocation_id is not None:
        allocation = conn.execute(
            """SELECT 1 FROM trial_allocations
               WHERE trial_id = ? AND allocation_id = ? AND status IN ('enrolled', 'withdrawn')""",
            (trial_id, allocation_id),
        ).fetchone()
        if allocation is None:
            raise ValueError("trial confounder allocation must participate in the trial")
    identifier, created_at = _new_identity()
    conn.execute(
        "INSERT INTO trial_confounders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (identifier, trial_id, allocation_id, category, description, observed_at, evidence_artifact_id,
         actor_id, created_at),
    )
    conn.commit()
    return get_trial_confounder(conn, identifier)  # type: ignore[return-value]


def get_trial_confounder(conn: sqlite3.Connection, confounder_id: str) -> Optional[TrialConfounder]:
    row = conn.execute("SELECT * FROM trial_confounders WHERE id = ?", (confounder_id,)).fetchone()
    return _trial_confounder(row) if row is not None else None


def list_trial_confounders(conn: sqlite3.Connection, trial_id: str) -> List[TrialConfounder]:
    return [_trial_confounder(row) for row in conn.execute(
        "SELECT * FROM trial_confounders WHERE trial_id = ? ORDER BY observed_at, created_at", (trial_id,)
    ).fetchall()]


def create_trial_conclusion(
    conn: sqlite3.Connection, trial_id: str, reviewer_id: str, result: Any, confidence_level: str,
    limitations: Any, evidence_artifact_id: str, playbook_decision: str = "none", status: str = "draft",
    playbook_id: Optional[str] = None,
    approved_at: Optional[str] = None,
) -> TrialConclusion:
    if playbook_decision == "promote" and (status != "approved" or approved_at is None or playbook_id is None):
        raise ValueError("promoting a playbook requires an approved conclusion, timestamp, and playbook")
    identifier, created_at = _new_identity()
    conn.execute(
        "INSERT INTO trial_conclusions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (identifier, trial_id, reviewer_id, status, _json_value(result), confidence_level,
         _json_value(limitations), evidence_artifact_id, playbook_id, playbook_decision, approved_at, created_at),
    )
    conn.commit()
    return get_trial_conclusion(conn, identifier)  # type: ignore[return-value]


def get_trial_conclusion(conn: sqlite3.Connection, conclusion_id: str) -> Optional[TrialConclusion]:
    row = conn.execute("SELECT * FROM trial_conclusions WHERE id = ?", (conclusion_id,)).fetchone()
    return _trial_conclusion(row) if row is not None else None


def list_trial_conclusions(conn: sqlite3.Connection, trial_id: str) -> List[TrialConclusion]:
    return [_trial_conclusion(row) for row in conn.execute(
        "SELECT * FROM trial_conclusions WHERE trial_id = ? ORDER BY created_at", (trial_id,)
    ).fetchall()]
