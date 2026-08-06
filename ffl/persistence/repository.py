import json
import hashlib
import math
import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, List, Mapping, Optional, Sequence, Tuple

from ffl.domain.models import (
    AuditEvent,
    CropStageCheckpoint,
    CropAllocation,
    Decision,
    EvidenceArtifact,
    ExceptionRecord,
    FieldCaptureCandidate,
    FieldCapturePass,
    FieldSignal,
    FieldInformationRequest,
    FieldInformationRequestEvent,
    HarvestRecord,
    ImportBatch,
    ImportRow,
    LandParcel,
    OperatingUnit,
    OperatingUnitLocation,
    OperationalBlock,
    Person,
    PersonOperatingRelationship,
    Playbook,
    RegionalSignal,
    RightToOperate,
    Season,
    SeasonReview,
    SignalTemplate,
    SoilBaseline,
    SourceRegistry,
    SourceRun,
    Trial,
    TrialAllocation,
    TrialConclusion,
    TrialConfounder,
    TrackolapStoredRecord,
    WorkItem,
)


PERSON_OPERATING_SCOPE_TABLES = {
    "operating_unit": ("operating_units", "operating_unit_id"),
    "land_parcel": ("land_parcels", "land_parcel_id"),
    "operational_block": ("operational_blocks", "operational_block_id"),
    "crop_allocation": ("crop_allocations", "crop_allocation_id"),
}
PERSON_OPERATING_RELATIONSHIP_ROLES = {
    "grower", "landholder", "lessee", "field_operator", "manager",
    "agronomist", "reviewer", "buyer_contact",
}
FIELD_INFORMATION_REQUEST_KINDS = {
    "field_check", "evidence_photo", "irrigation_status", "input_application",
    "pest_or_deviation", "harvest_update",
}
FIELD_INFORMATION_REQUEST_STATUSES = {
    "draft", "ready", "dispatched", "responded", "expired", "cancelled",
}
FIELD_INFORMATION_REQUEST_TRANSITIONS = {
    "draft": {"ready", "expired", "cancelled"},
    "ready": {"dispatched", "expired", "cancelled"},
    "dispatched": {"responded", "expired", "cancelled"},
    "responded": set(),
    "expired": set(),
    "cancelled": set(),
}
_FIELD_INFORMATION_REQUEST_IDEMPOTENCY_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}")
_FIELD_INFORMATION_REQUEST_SYSTEM_ACTOR = re.compile(r"system:[a-z][a-z0-9._-]{2,80}")
_FIELD_CAPTURE_TOKEN_HASH = re.compile(r"[0-9a-f]{64}")
_FIELD_CAPTURE_IDEMPOTENCY_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}")
FARM_TRUTH_CASE_STATUSES = {"open", "accepting", "needs_evidence", "accepted", "rejected"}
FARM_TRUTH_MISSING_EVIDENCE_KINDS = {
    "plot_area", "crop_season", "right_to_operate", "farmer_identity",
    "field_worker_assignment",
}


class FarmTruthConflict(ValueError):
    """A Farm Truth decision lost an optimistic or uniqueness race."""


@dataclass(frozen=True)
class Farm:
    """A reviewed canonical farm within one operating unit."""

    id: str
    operating_unit_id: str
    name: str
    status: str
    reviewed_by_person_id: str
    created_at: str


@dataclass(frozen=True)
class FarmField:
    """A reviewed, time-bounded association between a farm and a field."""

    id: str
    farm_id: str
    operational_block_id: str
    starts_on: str
    ends_on: Optional[str]
    status: str
    reviewed_by_person_id: str
    created_at: str


@dataclass(frozen=True)
class FarmTruthReviewCase:
    """Private review state joining one source registration to one source plot."""

    id: str
    source_id: str
    registration_id: str
    plot_id: str
    candidate_fingerprint: str
    status: str
    evidence_summary: Mapping[str, Any]
    review_reason: Optional[str]
    missing_evidence_kind: Optional[str]
    owner_person_id: Optional[str]
    reviewed_by_person_id: Optional[str]
    reviewed_at: Optional[str]
    accepted_land_parcel_id: Optional[str]
    accepted_operational_block_id: Optional[str]
    accepted_crop_allocation_id: Optional[str]
    accepted_grower_person_id: Optional[str]
    accepted_field_worker_person_id: Optional[str]
    created_at: str
    updated_at: str

_TRACKWICK_PRIVATE_TABLES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "trackwick_parties": (
        ("id", "party_kind", "provider_identifier", "display_name", "crm_status", "provider_owner_identifier", "provider_tag", "provider_created_at"),
        ("source_id", "party_kind", "provider_identifier"),
    ),
    "trackwick_contact_points": (
        ("id", "party_id", "contact_kind", "contact_value", "value_fingerprint", "consent_status"),
        ("party_id", "contact_kind", "value_fingerprint"),
    ),
    "trackwick_tasks": (
        ("id", "provider_task_id", "farmer_party_id", "field_worker_party_id", "provider_customer_identifier", "task_type", "task_status", "provider_created_at", "provider_started_at", "provider_completed_at", "provider_follow_up_at", "provider_plot_reference"),
        ("source_id", "provider_task_id"),
    ),
    "trackwick_visits": (
        ("task_id", "observed_at", "transplanted_on", "crop_stage", "water_condition", "crop_condition_score", "kit_status"),
        ("task_id",),
    ),
    "trackwick_visit_findings": (
        ("id", "visit_task_id", "finding_kind", "reported_value", "source_field", "declared_severity", "observed_at"),
        ("visit_task_id", "finding_kind", "source_field", "reported_value"),
    ),
    "trackwick_crop_inputs": (
        ("id", "visit_task_id", "input_kind", "event_kind", "reported_product", "source_field", "occurred_at"),
        ("visit_task_id", "input_kind", "event_kind", "source_field", "reported_product"),
    ),
    "trackwick_registrations": (
        ("id", "task_id", "farmer_party_id", "registration_status", "village_name", "block_name", "district_name", "reported_total_area_acres", "reported_plot_count", "reported_pb1_area_acres", "reported_1718_area_acres"),
        ("task_id",),
    ),
    "trackwick_registration_plots": (
        ("id", "registration_id", "ordinal", "gata_number", "reported_area_bigha", "plot_type", "village_name"),
        ("registration_id", "ordinal"),
    ),
    "trackwick_media_references": (
        ("id", "task_id", "provider_media_key", "media_kind", "remote_url", "provider_created_at", "source_access_state", "content_state", "exif_state", "content_hash", "content_type", "size_bytes"),
        ("source_id", "provider_media_key"),
    ),
    "trackwick_location_observations": (
        ("id", "party_id", "task_id", "registration_id", "media_reference_id", "provider_location_key", "location_kind", "location_confidence", "latitude", "longitude", "provider_address", "provider_geo_address", "provider_accuracy_m", "observed_at"),
        ("source_id", "provider_location_key"),
    ),
    "trackwick_worker_days": (
        ("id", "field_worker_party_id", "observed_on", "attendance_status", "reported_start_time", "reported_total_time"),
        ("field_worker_party_id", "observed_on"),
    ),
    "trackwick_task_plot_links": (
        (
            "id", "task_id", "registration_id", "plot_id", "association_kind",
        ),
        ("task_id",),
    ),
}


def _new_identity() -> Tuple[str, str]:
    return str(uuid.uuid4()), datetime.now(timezone.utc).isoformat()


def _json_value(value: object) -> str:
    """Persist JSON columns consistently while accepting normal Python values."""
    def primitive(item: object) -> float:
        if isinstance(item, Decimal) and item.is_finite():
            return float(item)
        raise TypeError("JSON values must contain only finite primitive values")

    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False,
            default=primitive,
        )
    except (TypeError, ValueError) as exc:
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


def _operating_unit_location(row: sqlite3.Row) -> OperatingUnitLocation:
    return OperatingUnitLocation(
        row["id"], row["operating_unit_id"], row["country_code"], row["state_name"],
        row["district_name"], row["district_context_key"], row["subdistrict_name"],
        row["village_name"], row["pincode"], row["verification_method"],
        row["verified_by_person_id"], row["verified_at"], row["status"],
        row["supersedes_location_id"], row["created_at"],
    )


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


def _farm(row: sqlite3.Row) -> Farm:
    return Farm(
        row["id"], row["operating_unit_id"], row["name"], row["status"],
        row["reviewed_by_person_id"], row["created_at"],
    )


def _farm_field(row: sqlite3.Row) -> FarmField:
    return FarmField(
        row["id"], row["farm_id"], row["operational_block_id"], row["starts_on"],
        row["ends_on"], row["status"], row["reviewed_by_person_id"], row["created_at"],
    )


def _person_operating_relationship(row: sqlite3.Row) -> PersonOperatingRelationship:
    return PersonOperatingRelationship(
        row["id"], row["person_id"], row["scope_type"], row["operating_unit_id"],
        row["land_parcel_id"], row["operational_block_id"], row["crop_allocation_id"],
        row["role"], row["starts_on"], row["ends_on"], row["status"], row["provenance"],
        row["reviewed_by_person_id"], row["ended_by_person_id"], row["ended_at"], row["created_at"],
    )


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


def _field_information_request(row: sqlite3.Row) -> FieldInformationRequest:
    return FieldInformationRequest(
        row["id"], row["allocation_id"], row["target_person_id"], row["work_item_id"],
        row["request_kind"], bool(row["evidence_required"]), row["due_at"],
        row["request_copy_en"], row["request_copy_hi"], row["initiated_by_person_id"],
        row["initiated_by_system_key"], row["idempotency_key"], row["status"], row["created_at"],
    )


def _field_information_request_event(row: sqlite3.Row) -> FieldInformationRequestEvent:
    return FieldInformationRequestEvent(
        row["id"], row["field_information_request_id"], row["from_status"], row["to_status"],
        row["actor_person_id"], row["actor_system_key"], row["reason"], row["created_at"],
    )


def _field_capture_pass(row: sqlite3.Row) -> FieldCapturePass:
    return FieldCapturePass(
        row["id"], row["field_information_request_id"], row["signal_template_id"],
        row["signal_template_version"], row["token_hash"], row["issued_by_person_id"],
        row["expires_at"], row["status"], row["created_at"], row["revoked_at"],
    )


def _field_capture_candidate(row: sqlite3.Row) -> FieldCaptureCandidate:
    return FieldCaptureCandidate(
        row["id"], row["field_information_request_id"], row["field_capture_pass_id"],
        row["allocation_id"], row["actor_person_id"], row["signal_template_id"],
        row["signal_template_version"], row["observed_at"], json.loads(row["values_json"]),
        row["evidence_artifact_id"], row["idempotency_key"], row["status"],
        row["reviewed_by_person_id"], row["reviewed_at"], row["accepted_signal_id"],
        row["created_at"],
    )


def _farm_truth_review_case(row: sqlite3.Row) -> FarmTruthReviewCase:
    return FarmTruthReviewCase(
        row["id"], row["source_id"], row["registration_id"], row["plot_id"],
        row["candidate_fingerprint"], row["status"], json.loads(row["evidence_summary_json"]),
        row["review_reason"], row["missing_evidence_kind"], row["owner_person_id"],
        row["reviewed_by_person_id"], row["reviewed_at"], row["accepted_land_parcel_id"],
        row["accepted_operational_block_id"], row["accepted_crop_allocation_id"],
        row["accepted_grower_person_id"], row["accepted_field_worker_person_id"],
        row["created_at"], row["updated_at"],
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


def _soil_baseline(row: sqlite3.Row) -> SoilBaseline:
    return SoilBaseline(
        row["id"], row["operating_unit_id"], row["sampled_on"], row["depth_cm_start"],
        row["depth_cm_end"], row["lab_name"], json.loads(row["measurements_json"]),
        row["evidence_artifact_id"], row["reviewed_by_person_id"], row["status"], row["created_at"],
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


def _trackolap_record(row: sqlite3.Row) -> TrackolapStoredRecord:
    return TrackolapStoredRecord(
        row["id"], row["source_id"], row["source_run_id"], row["import_batch_id"],
        row["feed"], row["source_identifier"], row["source_updated_at"], row["tenant_id"],
        json.loads(row["values_json"]), row["status"], row["created_at"],
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


def get_operating_unit(conn: sqlite3.Connection, operating_unit_id: str) -> Optional[OperatingUnit]:
    row = conn.execute("SELECT * FROM operating_units WHERE id = ?", (operating_unit_id,)).fetchone()
    return _operating_unit(row) if row is not None else None


def get_person(conn: sqlite3.Connection, person_id: str) -> Optional[Person]:
    row = conn.execute("SELECT * FROM people WHERE id = ?", (person_id,)).fetchone()
    return _person(row) if row is not None else None


def create_farm(
    conn: sqlite3.Connection, operating_unit_id: str, name: str, reviewed_by_person_id: str,
) -> Farm:
    """Create an active farm only after its operating unit and reviewer exist."""
    operating_unit_id = _required_text(operating_unit_id, "operating_unit_id", 128)
    if get_operating_unit(conn, operating_unit_id) is None:
        raise ValueError("operating unit does not exist")
    reviewed_by_person_id = _required_text(reviewed_by_person_id, "reviewed_by_person_id", 128)
    if get_person(conn, reviewed_by_person_id) is None:
        raise ValueError("reviewed_by_person_id does not exist")
    name = _required_text(name, "name")
    identifier, created_at = _new_identity()
    conn.execute(
        """INSERT INTO farms
           (id, operating_unit_id, name, status, reviewed_by_person_id, created_at)
           VALUES (?, ?, ?, 'active', ?, ?)""",
        (identifier, operating_unit_id, name, reviewed_by_person_id, created_at),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM farms WHERE id = ?", (identifier,)).fetchone()
    return _farm(row)  # type: ignore[arg-type]


def assign_field_to_farm(
    conn: sqlite3.Connection, farm_id: str, operational_block_id: str, starts_on: str,
    reviewed_by_person_id: str,
) -> FarmField:
    """Start one reviewed field membership, leaving uniqueness to the schema."""
    farm_id = _required_text(farm_id, "farm_id", 128)
    farm_row = conn.execute("SELECT * FROM farms WHERE id = ?", (farm_id,)).fetchone()
    if farm_row is None:
        raise ValueError("farm does not exist")
    if farm_row["status"] != "active":
        raise ValueError("farm must be active")
    operational_block_id = _required_text(operational_block_id, "operational_block_id", 128)
    if conn.execute(
        "SELECT 1 FROM operational_blocks WHERE id = ?", (operational_block_id,)
    ).fetchone() is None:
        raise ValueError("operational block does not exist")
    starts_on = _require_iso_date(starts_on, "starts_on")
    reviewed_by_person_id = _required_text(reviewed_by_person_id, "reviewed_by_person_id", 128)
    if get_person(conn, reviewed_by_person_id) is None:
        raise ValueError("reviewed_by_person_id does not exist")
    identifier, created_at = _new_identity()
    conn.execute(
        """INSERT INTO farm_fields
           (id, farm_id, operational_block_id, starts_on, ends_on, status,
            reviewed_by_person_id, created_at)
           VALUES (?, ?, ?, ?, NULL, 'active', ?, ?)""",
        (identifier, farm_id, operational_block_id, starts_on, reviewed_by_person_id, created_at),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM farm_fields WHERE id = ?", (identifier,)).fetchone()
    return _farm_field(row)  # type: ignore[arg-type]


def end_farm_field_assignment(
    conn: sqlite3.Connection, farm_field_id: str, ends_on: str, reviewed_by_person_id: str,
) -> FarmField:
    """End exactly one active membership; historical rows stay immutable."""
    farm_field_id = _required_text(farm_field_id, "farm_field_id", 128)
    row = conn.execute("SELECT * FROM farm_fields WHERE id = ?", (farm_field_id,)).fetchone()
    if row is None:
        raise ValueError("farm field assignment does not exist")
    if row["status"] != "active":
        raise ValueError("farm field assignment is not active")
    ends_on = _require_iso_date(ends_on, "ends_on")
    if date.fromisoformat(ends_on) < date.fromisoformat(row["starts_on"]):
        raise ValueError("ends_on must be on or after starts_on")
    reviewed_by_person_id = _required_text(reviewed_by_person_id, "reviewed_by_person_id", 128)
    if get_person(conn, reviewed_by_person_id) is None:
        raise ValueError("reviewed_by_person_id does not exist")
    conn.execute(
        """UPDATE farm_fields
           SET ends_on = ?, status = 'ended', reviewed_by_person_id = ?
           WHERE id = ? AND status = 'active'""",
        (ends_on, reviewed_by_person_id, farm_field_id),
    )
    conn.commit()
    updated = conn.execute("SELECT * FROM farm_fields WHERE id = ?", (farm_field_id,)).fetchone()
    return _farm_field(updated)  # type: ignore[arg-type]


def list_active_farm_fields(conn: sqlite3.Connection, farm_id: str) -> List[FarmField]:
    farm_id = _required_text(farm_id, "farm_id", 128)
    rows = conn.execute(
        """SELECT * FROM farm_fields WHERE farm_id = ? AND status = 'active'
           ORDER BY starts_on, created_at, id""",
        (farm_id,),
    ).fetchall()
    return [_farm_field(row) for row in rows]


def list_people_for_farm(conn: sqlite3.Connection, farm_id: str) -> List[Person]:
    """Return reviewed active field and allocation roles for one active farm.

    TrackWick source parties and tasks are intentionally absent from this
    query: only reviewed canonical operating relationships establish this view.
    """
    farm_id = _required_text(farm_id, "farm_id", 128)
    rows = conn.execute(
        """SELECT DISTINCT people.id, people.name, relationships.role, people.created_at
           FROM farm_fields
           JOIN person_operating_relationships AS relationships
             ON relationships.status = 'active'
            AND relationships.reviewed_by_person_id IS NOT NULL
            AND (
                (relationships.scope_type = 'operational_block'
                 AND relationships.operational_block_id = farm_fields.operational_block_id)
                OR
                (relationships.scope_type = 'crop_allocation'
                 AND relationships.crop_allocation_id IN (
                     SELECT crop_allocations.id
                     FROM crop_allocations
                     WHERE crop_allocations.operational_block_id = farm_fields.operational_block_id
                 ))
            )
           JOIN people ON people.id = relationships.person_id
           WHERE farm_fields.farm_id = ? AND farm_fields.status = 'active'
           ORDER BY people.name, relationships.role, people.id""",
        (farm_id,),
    ).fetchall()
    return [_person(row) for row in rows]


def _required_text(value: object, name: str, maximum: int = 200) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise ValueError("{0} must be non-empty text up to {1} characters".format(name, maximum))
    return value.strip()


def _optional_text(value: object, name: str, maximum: int = 200) -> Optional[str]:
    if value is None:
        return None
    return _required_text(value, name, maximum)


def _validate_soil_measurements(measurements: Any) -> None:
    if not isinstance(measurements, dict) or not measurements:
        raise ValueError("soil measurements must be a non-empty object")
    for metric, measurement in measurements.items():
        _required_text(metric, "soil measurement name", 80)
        if not isinstance(measurement, dict):
            raise ValueError("each soil measurement must include a value and unit")
        value = measurement.get("value")
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
            raise ValueError("each soil measurement value must be a finite number")
        _required_text(measurement.get("unit"), "soil measurement unit", 40)


def _require_iso_date(value: object, name: str) -> str:
    parsed = _required_text(value, name, 32)
    try:
        date.fromisoformat(parsed)
    except ValueError as error:
        raise ValueError("{0} must be an ISO-8601 date".format(name)) from error
    return parsed


def _require_iso_timestamp(value: object, name: str) -> str:
    parsed = _required_text(value, name, 64)
    try:
        timestamp = datetime.fromisoformat(parsed.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("{0} must be an ISO-8601 timestamp".format(name)) from error
    if timestamp.tzinfo is None:
        raise ValueError("{0} must include a timezone".format(name))
    return parsed


def create_operating_unit_location(
    conn: sqlite3.Connection, operating_unit_id: str, state_name: str, district_name: str,
    district_context_key: str, verified_by_person_id: str, verified_at: str,
    verification_method: str = "field_verified", subdistrict_name: Optional[str] = None,
    village_name: Optional[str] = None, pincode: Optional[str] = None,
) -> OperatingUnitLocation:
    """Append a reviewed administrative location and supersede the former one.

    A location is intentionally not a parcel boundary, ownership claim, or GPS
    observation.  Its district context key is the stable internal join for a
    later approved IMD mapping.
    """
    if get_operating_unit(conn, operating_unit_id) is None:
        raise ValueError("operating unit does not exist")
    if get_person(conn, verified_by_person_id) is None:
        raise ValueError("location verifier does not exist")
    state_name = _required_text(state_name, "state_name")
    district_name = _required_text(district_name, "district_name")
    district_context_key = _required_text(district_context_key, "district_context_key", 120)
    if verification_method not in {"field_verified", "lgd_reference"}:
        raise ValueError("verification_method must be field_verified or lgd_reference")
    subdistrict_name = _optional_text(subdistrict_name, "subdistrict_name")
    village_name = _optional_text(village_name, "village_name")
    if pincode is not None and (not isinstance(pincode, str) or re.fullmatch(r"[0-9]{6}", pincode) is None):
        raise ValueError("pincode must be a six-digit Indian PIN when supplied")
    verified_at = _require_iso_timestamp(verified_at, "verified_at")

    identifier, created_at = _new_identity()
    with conn:
        prior_row = conn.execute(
            "SELECT * FROM operating_unit_locations WHERE operating_unit_id = ? AND status = 'active'",
            (operating_unit_id,),
        ).fetchone()
        if prior_row is not None:
            conn.execute("UPDATE operating_unit_locations SET status = 'superseded' WHERE id = ?", (prior_row["id"],))
            audit_id, audit_created_at = _new_identity()
            conn.execute(
                "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (audit_id, "operating_unit_location", prior_row["id"], "active", "superseded",
                 verified_by_person_id, "superseded_by_new_verified_location", audit_created_at),
            )
        conn.execute(
            """INSERT INTO operating_unit_locations
               (id, operating_unit_id, country_code, state_name, district_name, district_context_key,
                subdistrict_name, village_name, pincode, verification_method, verified_by_person_id,
                verified_at, status, supersedes_location_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (identifier, operating_unit_id, "IN", state_name, district_name, district_context_key,
             subdistrict_name, village_name, pincode, verification_method, verified_by_person_id,
             verified_at, "active", prior_row["id"] if prior_row is not None else None, created_at),
        )
    return get_operating_unit_location(conn, identifier)  # type: ignore[return-value]


def get_operating_unit_location(
    conn: sqlite3.Connection, location_id: str
) -> Optional[OperatingUnitLocation]:
    row = conn.execute("SELECT * FROM operating_unit_locations WHERE id = ?", (location_id,)).fetchone()
    return _operating_unit_location(row) if row is not None else None


def get_active_operating_unit_location(
    conn: sqlite3.Connection, operating_unit_id: str
) -> Optional[OperatingUnitLocation]:
    row = conn.execute(
        """SELECT * FROM operating_unit_locations
           WHERE operating_unit_id = ? AND status = 'active' ORDER BY verified_at DESC, created_at DESC LIMIT 1""",
        (operating_unit_id,),
    ).fetchone()
    return _operating_unit_location(row) if row is not None else None


def create_soil_baseline(
    conn: sqlite3.Connection, operating_unit_id: str, sampled_on: str, lab_name: str,
    measurements: Any, evidence_artifact_id: str, reviewed_by_person_id: str,
    depth_cm_start: Optional[float] = None, depth_cm_end: Optional[float] = None,
) -> SoilBaseline:
    """Append a reviewed soil baseline backed by a retained FFL evidence artifact."""
    if get_operating_unit(conn, operating_unit_id) is None:
        raise ValueError("operating unit does not exist")
    if get_person(conn, reviewed_by_person_id) is None:
        raise ValueError("soil reviewer does not exist")
    if get_evidence_artifact(conn, evidence_artifact_id) is None:
        raise ValueError("soil evidence artifact does not exist")
    sampled_on = _require_iso_date(sampled_on, "sampled_on")
    lab_name = _required_text(lab_name, "lab_name")
    _validate_soil_measurements(measurements)
    for value, name in ((depth_cm_start, "depth_cm_start"), (depth_cm_end, "depth_cm_end")):
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or value < 0):
            raise ValueError("{0} must be a finite non-negative number when supplied".format(name))
    if depth_cm_start is not None and depth_cm_end is not None and depth_cm_end < depth_cm_start:
        raise ValueError("depth_cm_end must be at least depth_cm_start")
    identifier, created_at = _new_identity()
    conn.execute(
        """INSERT INTO soil_baselines
           (id, operating_unit_id, sampled_on, depth_cm_start, depth_cm_end, lab_name, measurements_json,
            evidence_artifact_id, reviewed_by_person_id, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (identifier, operating_unit_id, sampled_on, depth_cm_start, depth_cm_end, lab_name,
         _json_value(measurements), evidence_artifact_id, reviewed_by_person_id, "reviewed", created_at),
    )
    conn.commit()
    return get_soil_baseline(conn, identifier)  # type: ignore[return-value]


def get_soil_baseline(conn: sqlite3.Connection, soil_baseline_id: str) -> Optional[SoilBaseline]:
    row = conn.execute("SELECT * FROM soil_baselines WHERE id = ?", (soil_baseline_id,)).fetchone()
    return _soil_baseline(row) if row is not None else None


def list_soil_baselines(conn: sqlite3.Connection, operating_unit_id: str) -> List[SoilBaseline]:
    rows = conn.execute(
        """SELECT * FROM soil_baselines WHERE operating_unit_id = ? AND status = 'reviewed'
           ORDER BY sampled_on DESC, created_at DESC""", (operating_unit_id,)
    ).fetchall()
    return [_soil_baseline(row) for row in rows]


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


def get_season(conn: sqlite3.Connection, season_id: str) -> Optional[Season]:
    row = conn.execute("SELECT * FROM seasons WHERE id = ?", (season_id,)).fetchone()
    return _season(row) if row is not None else None


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


def get_crop_allocation(conn: sqlite3.Connection, allocation_id: str) -> Optional[CropAllocation]:
    row = conn.execute("SELECT * FROM crop_allocations WHERE id = ?", (allocation_id,)).fetchone()
    return _crop_allocation(row) if row is not None else None


def create_person(conn: sqlite3.Connection, name: str, role: str) -> Person:
    identifier, created_at = _new_identity()
    conn.execute("INSERT INTO people VALUES (?, ?, ?, ?)", (identifier, name, role, created_at))
    conn.commit()
    return Person(identifier, name, role, created_at)


def _validate_person_operating_scope(conn: sqlite3.Connection, scope_type: object, scope_id: object) -> tuple[str, str, str]:
    if not isinstance(scope_type, str) or scope_type not in PERSON_OPERATING_SCOPE_TABLES:
        raise ValueError("scope_type must be operating_unit, land_parcel, operational_block, or crop_allocation")
    identifier = _required_text(scope_id, "scope_id", 128)
    table, column = PERSON_OPERATING_SCOPE_TABLES[scope_type]
    if conn.execute("SELECT 1 FROM {0} WHERE id = ?".format(table), (identifier,)).fetchone() is None:
        raise ValueError("{0} scope does not exist".format(scope_type.replace("_", " ")))
    return scope_type, identifier, column


def _validate_relationship_role(role: object) -> str:
    if not isinstance(role, str) or role not in PERSON_OPERATING_RELATIONSHIP_ROLES:
        raise ValueError(
            "role must be grower, landholder, lessee, field_operator, manager, agronomist, reviewer, or buyer_contact"
        )
    return role


def _validate_relationship_dates(starts_on: object, ends_on: Optional[object]) -> tuple[str, Optional[str]]:
    starts = _require_iso_date(starts_on, "starts_on")
    if ends_on is None:
        return starts, None
    ends = _require_iso_date(ends_on, "ends_on")
    if date.fromisoformat(ends) < date.fromisoformat(starts):
        raise ValueError("ends_on must be on or after starts_on")
    return starts, ends


def get_person_operating_relationship(
    conn: sqlite3.Connection, relationship_id: str
) -> Optional[PersonOperatingRelationship]:
    row = conn.execute(
        "SELECT * FROM person_operating_relationships WHERE id = ?", (relationship_id,)
    ).fetchone()
    return _person_operating_relationship(row) if row is not None else None


def create_person_operating_relationship(
    conn: sqlite3.Connection, person_id: str, scope_type: str, scope_id: str, role: str,
    starts_on: str, ends_on: Optional[str] = None, provenance: Optional[str] = None,
    reviewed_by_person_id: Optional[str] = None,
) -> PersonOperatingRelationship:
    """Append a scoped person relationship without inferring land ownership.

    Active records are protected by four database-level partial unique indexes,
    one for each supported scope.  The preflight check makes ordinary client
    errors readable; the constraint remains the concurrency-safe authority.
    """
    person_id = _required_text(person_id, "person_id", 128)
    if get_person(conn, person_id) is None:
        raise ValueError("person does not exist")
    scope_type, scope_id, scope_column = _validate_person_operating_scope(conn, scope_type, scope_id)
    role = _validate_relationship_role(role)
    starts_on, ends_on = _validate_relationship_dates(starts_on, ends_on)
    provenance = _optional_text(provenance, "provenance", 1000)
    if reviewed_by_person_id is not None:
        reviewed_by_person_id = _required_text(reviewed_by_person_id, "reviewed_by_person_id", 128)
        if get_person(conn, reviewed_by_person_id) is None:
            raise ValueError("reviewed_by_person_id does not exist")
    if provenance is None and reviewed_by_person_id is None:
        raise ValueError("provenance or reviewed_by_person_id is required")

    status = "active" if ends_on is None else "ended"
    if status == "active":
        existing = conn.execute(
            """SELECT id FROM person_operating_relationships
               WHERE person_id = ? AND scope_type = ? AND {0} = ? AND role = ? AND status = 'active'""".format(
                scope_column
            ),
            (person_id, scope_type, scope_id, role),
        ).fetchone()
        if existing is not None:
            raise ValueError("an active relationship already exists for this person, scope, and role")

    identifier, created_at = _new_identity()
    scope_values = {
        "operating_unit_id": None,
        "land_parcel_id": None,
        "operational_block_id": None,
        "crop_allocation_id": None,
    }
    scope_values[scope_column] = scope_id
    try:
        conn.execute(
            """INSERT INTO person_operating_relationships (
                id, person_id, scope_type, operating_unit_id, land_parcel_id, operational_block_id,
                crop_allocation_id, role, starts_on, ends_on, status, provenance,
                reviewed_by_person_id, ended_by_person_id, ended_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                identifier, person_id, scope_type, scope_values["operating_unit_id"],
                scope_values["land_parcel_id"], scope_values["operational_block_id"],
                scope_values["crop_allocation_id"], role, starts_on, ends_on, status, provenance,
                reviewed_by_person_id, None, None, created_at,
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError as error:
        conn.rollback()
        if status == "active":
            existing = conn.execute(
                """SELECT id FROM person_operating_relationships
                   WHERE person_id = ? AND scope_type = ? AND {0} = ? AND role = ? AND status = 'active'""".format(
                    scope_column
                ),
                (person_id, scope_type, scope_id, role),
            ).fetchone()
            if existing is not None:
                raise ValueError("an active relationship already exists for this person, scope, and role") from error
        raise
    return get_person_operating_relationship(conn, identifier)  # type: ignore[return-value]


def list_person_operating_relationships(
    conn: sqlite3.Connection, person_id: Optional[str] = None, scope_type: Optional[str] = None,
    scope_id: Optional[str] = None, status: Optional[str] = None,
) -> List[PersonOperatingRelationship]:
    """List relationship history without making a public people directory."""
    if scope_id is not None and scope_type is None:
        raise ValueError("scope_type is required when scope_id is supplied")
    where = []
    params: List[object] = []
    if person_id is not None:
        where.append("person_id = ?")
        params.append(_required_text(person_id, "person_id", 128))
    if scope_type is not None:
        normalized_scope_type = _validate_person_operating_scope_name(scope_type)
        scope_column = PERSON_OPERATING_SCOPE_TABLES[normalized_scope_type][1]
        if scope_id is not None:
            _, normalized_scope_id, _ = _validate_person_operating_scope(
                conn, normalized_scope_type, scope_id
            )
        where.append("scope_type = ?")
        params.append(normalized_scope_type)
        if scope_id is not None:
            where.append("{0} = ?".format(scope_column))
            params.append(normalized_scope_id)
    if status is not None:
        if status not in {"active", "ended"}:
            raise ValueError("status must be active or ended")
        where.append("status = ?")
        params.append(status)
    query = "SELECT * FROM person_operating_relationships"
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY starts_on DESC, created_at DESC, id DESC"
    rows = conn.execute(query, tuple(params)).fetchall()
    return [_person_operating_relationship(row) for row in rows]


def _validate_person_operating_scope_name(scope_type: object) -> str:
    if not isinstance(scope_type, str) or scope_type not in PERSON_OPERATING_SCOPE_TABLES:
        raise ValueError("scope_type must be operating_unit, land_parcel, operational_block, or crop_allocation")
    return scope_type


def end_person_operating_relationship(
    conn: sqlite3.Connection, relationship_id: str, ends_on: str, ended_by_person_id: str, reason: str,
) -> PersonOperatingRelationship:
    """Close a current relationship with an audit event; it is never deleted."""
    relationship = get_person_operating_relationship(conn, relationship_id)
    if relationship is None:
        raise ValueError("person operating relationship does not exist")
    if relationship.status != "active":
        raise ValueError("only an active person operating relationship can be ended")
    _, normalized_ends_on = _validate_relationship_dates(relationship.starts_on, ends_on)
    ended_by_person_id = _required_text(ended_by_person_id, "ended_by_person_id", 128)
    if get_person(conn, ended_by_person_id) is None:
        raise ValueError("ended_by_person_id does not exist")
    reason = _required_text(reason, "reason", 500)
    audit_id, ended_at = _new_identity()
    with conn:
        updated = conn.execute(
            """UPDATE person_operating_relationships
               SET ends_on = ?, status = 'ended', ended_by_person_id = ?, ended_at = ?
               WHERE id = ? AND status = 'active'""",
            (normalized_ends_on, ended_by_person_id, ended_at, relationship_id),
        )
        if updated.rowcount != 1:
            raise ValueError("only an active person operating relationship can be ended")
        conn.execute(
            "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (audit_id, "person_operating_relationship", relationship_id, "active", "ended",
             ended_by_person_id, reason, ended_at),
        )
    return get_person_operating_relationship(conn, relationship_id)  # type: ignore[return-value]


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


def _validate_field_information_request_actor(
    conn: sqlite3.Connection, initiated_by_person_id: Optional[object], initiated_by_system_key: Optional[object],
) -> tuple[Optional[str], Optional[str]]:
    """Require one durable actor without treating a provider endpoint as one.

    Managers are represented by existing people.  Deterministic internal jobs
    use a restricted ``system:`` key, which makes their intent auditable while
    keeping this foundation independent from a communications provider.
    """
    if initiated_by_person_id is not None and initiated_by_system_key is not None:
        raise ValueError("provide either initiated_by_person_id or initiated_by_system_key, not both")
    if initiated_by_person_id is not None:
        person_id = _required_text(initiated_by_person_id, "initiated_by_person_id", 128)
        if get_person(conn, person_id) is None:
            raise ValueError("initiating person does not exist")
        return person_id, None
    if not isinstance(initiated_by_system_key, str) or (
        _FIELD_INFORMATION_REQUEST_SYSTEM_ACTOR.fullmatch(initiated_by_system_key) is None
    ):
        raise ValueError("initiated_by_system_key must be a safe system:<name> identifier")
    return None, initiated_by_system_key


def _validate_field_information_request_values(
    conn: sqlite3.Connection, allocation_id: object, target_person_id: object,
    work_item_id: Optional[object], request_kind: object, evidence_required: object,
    due_at: object, request_copy_en: object, request_copy_hi: object, idempotency_key: object,
) -> tuple[str, str, Optional[str], str, int, str, str, str, str]:
    normalized_allocation_id = _required_text(allocation_id, "allocation_id", 128)
    if get_crop_allocation(conn, normalized_allocation_id) is None:
        raise ValueError("crop allocation does not exist")
    normalized_target_person_id = _required_text(target_person_id, "target_person_id", 128)
    if get_person(conn, normalized_target_person_id) is None:
        raise ValueError("target person does not exist")
    normalized_work_item_id = None
    if work_item_id is not None:
        normalized_work_item_id = _required_text(work_item_id, "work_item_id", 128)
        work_item = get_work_item(conn, normalized_work_item_id)
        if work_item is None:
            raise ValueError("linked work item does not exist")
        if work_item.allocation_id != normalized_allocation_id:
            raise ValueError("linked work item must belong to the same crop allocation")
    if not isinstance(request_kind, str) or request_kind not in FIELD_INFORMATION_REQUEST_KINDS:
        raise ValueError(
            "request_kind must be field_check, evidence_photo, irrigation_status, input_application, "
            "pest_or_deviation, or harvest_update"
        )
    if not isinstance(evidence_required, bool):
        raise ValueError("evidence_required must be a boolean")
    normalized_due_at = _require_iso_timestamp(due_at, "due_at")
    normalized_copy_en = _required_text(request_copy_en, "request_copy_en", 1600)
    normalized_copy_hi = _required_text(request_copy_hi, "request_copy_hi", 1600)
    if not isinstance(idempotency_key, str) or (
        _FIELD_INFORMATION_REQUEST_IDEMPOTENCY_KEY.fullmatch(idempotency_key) is None
    ):
        raise ValueError("idempotency_key must be 8-128 safe characters")
    return (
        normalized_allocation_id, normalized_target_person_id, normalized_work_item_id,
        request_kind, int(evidence_required), normalized_due_at, normalized_copy_en,
        normalized_copy_hi, idempotency_key,
    )


def get_field_information_request(
    conn: sqlite3.Connection, field_information_request_id: str
) -> Optional[FieldInformationRequest]:
    row = conn.execute(
        "SELECT * FROM field_information_requests WHERE id = ?", (field_information_request_id,)
    ).fetchone()
    return _field_information_request(row) if row is not None else None


def get_field_information_request_by_idempotency_key(
    conn: sqlite3.Connection, idempotency_key: str
) -> Optional[FieldInformationRequest]:
    row = conn.execute(
        "SELECT * FROM field_information_requests WHERE idempotency_key = ?", (idempotency_key,)
    ).fetchone()
    return _field_information_request(row) if row is not None else None


def create_field_information_request(
    conn: sqlite3.Connection, allocation_id: str, target_person_id: str, request_kind: str,
    evidence_required: bool, due_at: str, request_copy_en: str, request_copy_hi: str,
    idempotency_key: str, *, work_item_id: Optional[str] = None,
    initiated_by_person_id: Optional[str] = None, initiated_by_system_key: Optional[str] = None,
) -> FieldInformationRequest:
    """Create one draft request and its append-only creation event.

    The idempotency key identifies this logical request, not a message attempt.
    A provider adapter must never create a second request merely because a
    delivery operation is retried.
    """
    (
        allocation_id, target_person_id, work_item_id, request_kind, evidence_required,
        due_at, request_copy_en, request_copy_hi, idempotency_key,
    ) = _validate_field_information_request_values(
        conn, allocation_id, target_person_id, work_item_id, request_kind, evidence_required,
        due_at, request_copy_en, request_copy_hi, idempotency_key,
    )
    initiated_by_person_id, initiated_by_system_key = _validate_field_information_request_actor(
        conn, initiated_by_person_id, initiated_by_system_key
    )
    existing = get_field_information_request_by_idempotency_key(conn, idempotency_key)
    if existing is not None:
        return existing
    identifier, created_at = _new_identity()
    event_id, event_created_at = _new_identity()
    try:
        with conn:
            conn.execute(
                """INSERT INTO field_information_requests (
                    id, allocation_id, target_person_id, work_item_id, request_kind, evidence_required,
                    due_at, request_copy_en, request_copy_hi, initiated_by_person_id,
                    initiated_by_system_key, idempotency_key, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?)""",
                (
                    identifier, allocation_id, target_person_id, work_item_id, request_kind,
                    evidence_required, due_at, request_copy_en, request_copy_hi,
                    initiated_by_person_id, initiated_by_system_key, idempotency_key, created_at,
                ),
            )
            conn.execute(
                """INSERT INTO field_information_request_events (
                    id, field_information_request_id, from_status, to_status, actor_person_id,
                    actor_system_key, reason, created_at
                ) VALUES (?, ?, 'created', 'draft', ?, ?, 'created', ?)""",
                (
                    event_id, identifier, initiated_by_person_id, initiated_by_system_key,
                    event_created_at,
                ),
            )
    except sqlite3.IntegrityError:
        # The unique key is the durable concurrency guard.  Re-read rather
        # than sending or creating another logical request after a retry race.
        existing = get_field_information_request_by_idempotency_key(conn, idempotency_key)
        if existing is not None:
            return existing
        raise
    return get_field_information_request(conn, identifier)  # type: ignore[return-value]


def list_field_information_requests(
    conn: sqlite3.Connection, *, allocation_id: Optional[str] = None,
    target_person_id: Optional[str] = None, status: Optional[str] = None,
) -> List[FieldInformationRequest]:
    where: List[str] = []
    params: List[object] = []
    if allocation_id is not None:
        where.append("allocation_id = ?")
        params.append(_required_text(allocation_id, "allocation_id", 128))
    if target_person_id is not None:
        where.append("target_person_id = ?")
        params.append(_required_text(target_person_id, "target_person_id", 128))
    if status is not None:
        if status not in FIELD_INFORMATION_REQUEST_STATUSES:
            raise ValueError("invalid field information request status")
        where.append("status = ?")
        params.append(status)
    query = "SELECT * FROM field_information_requests"
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY due_at, created_at, id"
    return [_field_information_request(row) for row in conn.execute(query, tuple(params)).fetchall()]


def list_field_information_request_events(
    conn: sqlite3.Connection, field_information_request_id: str
) -> List[FieldInformationRequestEvent]:
    field_information_request_id = _required_text(
        field_information_request_id, "field_information_request_id", 128
    )
    rows = conn.execute(
        """SELECT * FROM field_information_request_events
           WHERE field_information_request_id = ? ORDER BY created_at, id""",
        (field_information_request_id,),
    ).fetchall()
    return [_field_information_request_event(row) for row in rows]


def transition_field_information_request(
    conn: sqlite3.Connection, field_information_request_id: str, target_status: str,
    *, actor_person_id: Optional[str] = None, actor_system_key: Optional[str] = None,
    reason: str,
) -> FieldInformationRequest:
    request = get_field_information_request(conn, field_information_request_id)
    if request is None:
        raise ValueError("field information request does not exist")
    if target_status not in FIELD_INFORMATION_REQUEST_TRANSITIONS.get(request.status, set()):
        raise ValueError("invalid field information request transition")
    actor_person_id, actor_system_key = _validate_field_information_request_actor(
        conn, actor_person_id, actor_system_key
    )
    reason = _required_text(reason, "reason", 500)
    event_id, event_created_at = _new_identity()
    with conn:
        updated = conn.execute(
            """UPDATE field_information_requests SET status = ?
               WHERE id = ? AND status = ?""",
            (target_status, request.id, request.status),
        )
        if updated.rowcount != 1:
            raise ValueError("invalid field information request transition")
        conn.execute(
            """INSERT INTO field_information_request_events (
                id, field_information_request_id, from_status, to_status, actor_person_id,
                actor_system_key, reason, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event_id, request.id, request.status, target_status, actor_person_id,
                actor_system_key, reason, event_created_at,
            ),
        )
    return get_field_information_request(conn, request.id)  # type: ignore[return-value]


def _require_field_capture_pass_values(
    conn: sqlite3.Connection, field_information_request_id: object, signal_template_id: object,
    signal_template_version: object, token_hash: object, issued_by_person_id: object, expires_at: object,
) -> tuple[str, str, int, str, str, str]:
    request_id = _required_text(field_information_request_id, "field_information_request_id", 128)
    if get_field_information_request(conn, request_id) is None:
        raise ValueError("field information request does not exist")
    template_id = _required_text(signal_template_id, "signal_template_id", 128)
    if not isinstance(signal_template_version, int) or isinstance(signal_template_version, bool) or signal_template_version < 1:
        raise ValueError("signal_template_version must be a positive integer")
    _require_published_template(conn, template_id, signal_template_version)
    if not isinstance(token_hash, str) or _FIELD_CAPTURE_TOKEN_HASH.fullmatch(token_hash) is None:
        raise ValueError("field capture token hash is invalid")
    issuer_id = _required_text(issued_by_person_id, "issued_by_person_id", 128)
    if get_person(conn, issuer_id) is None:
        raise ValueError("field capture issuer does not exist")
    return (
        request_id, template_id, signal_template_version, token_hash, issuer_id,
        _require_iso_timestamp(expires_at, "expires_at"),
    )


def get_field_capture_pass_by_token_hash(conn: sqlite3.Connection, token_hash: str) -> Optional[FieldCapturePass]:
    if not isinstance(token_hash, str) or _FIELD_CAPTURE_TOKEN_HASH.fullmatch(token_hash) is None:
        return None
    row = conn.execute(
        "SELECT * FROM field_capture_passes WHERE token_hash = ?", (token_hash,)
    ).fetchone()
    return _field_capture_pass(row) if row is not None else None


def get_field_capture_pass(conn: sqlite3.Connection, field_capture_pass_id: str) -> Optional[FieldCapturePass]:
    row = conn.execute(
        "SELECT * FROM field_capture_passes WHERE id = ?", (field_capture_pass_id,)
    ).fetchone()
    return _field_capture_pass(row) if row is not None else None


def create_field_capture_pass(
    conn: sqlite3.Connection, field_information_request_id: str, signal_template_id: str,
    signal_template_version: int, token_hash: str, issued_by_person_id: str, expires_at: str,
) -> FieldCapturePass:
    (
        request_id, template_id, template_version, token_hash, issuer_id, expires_at,
    ) = _require_field_capture_pass_values(
        conn, field_information_request_id, signal_template_id, signal_template_version,
        token_hash, issued_by_person_id, expires_at,
    )
    identifier, created_at = _new_identity()
    try:
        conn.execute(
            """INSERT INTO field_capture_passes (
                id, field_information_request_id, signal_template_id, signal_template_version,
                token_hash, issued_by_person_id, expires_at, status, created_at, revoked_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, NULL)""",
            (identifier, request_id, template_id, template_version, token_hash, issuer_id, expires_at, created_at),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        raise
    return get_field_capture_pass(conn, identifier)  # type: ignore[return-value]


def get_field_capture_candidate(conn: sqlite3.Connection, candidate_id: str) -> Optional[FieldCaptureCandidate]:
    row = conn.execute(
        "SELECT * FROM field_capture_candidates WHERE id = ?", (candidate_id,)
    ).fetchone()
    return _field_capture_candidate(row) if row is not None else None


def get_field_capture_candidate_by_pass_and_idempotency(
    conn: sqlite3.Connection, field_capture_pass_id: str, idempotency_key: str,
) -> Optional[FieldCaptureCandidate]:
    row = conn.execute(
        """SELECT * FROM field_capture_candidates
           WHERE field_capture_pass_id = ? AND idempotency_key = ?""",
        (field_capture_pass_id, idempotency_key),
    ).fetchone()
    return _field_capture_candidate(row) if row is not None else None


def create_field_capture_candidate(
    conn: sqlite3.Connection, field_information_request_id: str, field_capture_pass_id: str,
    allocation_id: str, actor_person_id: str, signal_template_id: str, signal_template_version: int,
    observed_at: str, values: Any, evidence_artifact_id: Optional[str], idempotency_key: str,
) -> FieldCaptureCandidate:
    if not isinstance(idempotency_key, str) or _FIELD_CAPTURE_IDEMPOTENCY_KEY.fullmatch(idempotency_key) is None:
        raise ValueError("idempotency_key must be 8-128 safe characters")
    if not isinstance(values, dict):
        raise ValueError("field capture values must be an object")
    # Ensure JSON safety before we retain a candidate.  Template-level filtering
    # is performed by the service before reaching this persistence boundary.
    values_json = _json_value(values)
    identifier, created_at = _new_identity()
    try:
        conn.execute(
            """INSERT INTO field_capture_candidates (
                id, field_information_request_id, field_capture_pass_id, allocation_id,
                actor_person_id, signal_template_id, signal_template_version, observed_at,
                values_json, evidence_artifact_id, idempotency_key, status,
                reviewed_by_person_id, reviewed_at, accepted_signal_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'review', NULL, NULL, NULL, ?)""",
            (
                identifier, field_information_request_id, field_capture_pass_id, allocation_id,
                actor_person_id, signal_template_id, signal_template_version, observed_at,
                values_json, evidence_artifact_id, idempotency_key, created_at,
            ),
        )
    except sqlite3.IntegrityError:
        established = get_field_capture_candidate_by_pass_and_idempotency(
            conn, field_capture_pass_id, idempotency_key
        )
        if established is not None:
            return established
        raise
    return get_field_capture_candidate(conn, identifier)  # type: ignore[return-value]


def claim_field_capture_candidate_for_acceptance(
    conn: sqlite3.Connection, candidate_id: str,
) -> Optional[FieldCaptureCandidate]:
    """Claim one review candidate inside the caller's transaction.

    The short-lived ``accepting`` state prevents two reviewers from creating
    two canonical field signals.  A transaction rollback restores ``review``.
    """
    updated = conn.execute(
        "UPDATE field_capture_candidates SET status = 'accepting' WHERE id = ? AND status = 'review'",
        (candidate_id,),
    )
    if updated.rowcount != 1:
        return None
    return get_field_capture_candidate(conn, candidate_id)


def accept_field_capture_candidate(
    conn: sqlite3.Connection, candidate_id: str, reviewer_id: str, accepted_signal_id: str,
    reviewed_at: str,
) -> FieldCaptureCandidate:
    updated = conn.execute(
        """UPDATE field_capture_candidates
           SET status = 'accepted', reviewed_by_person_id = ?, reviewed_at = ?, accepted_signal_id = ?
           WHERE id = ? AND status = 'accepting'""",
        (reviewer_id, reviewed_at, accepted_signal_id, candidate_id),
    )
    if updated.rowcount != 1:
        raise ValueError("field capture candidate cannot be accepted")
    return get_field_capture_candidate(conn, candidate_id)  # type: ignore[return-value]


def reject_field_capture_candidate(
    conn: sqlite3.Connection, candidate_id: str, reviewer_id: str, reviewed_at: str,
) -> FieldCaptureCandidate:
    updated = conn.execute(
        """UPDATE field_capture_candidates
           SET status = 'rejected', reviewed_by_person_id = ?, reviewed_at = ?
           WHERE id = ? AND status = 'review'""",
        (reviewer_id, reviewed_at, candidate_id),
    )
    if updated.rowcount != 1:
        raise ValueError("field capture candidate cannot be rejected")
    conn.commit()
    return get_field_capture_candidate(conn, candidate_id)  # type: ignore[return-value]


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
    supersedes_signal_id: Optional[str] = None, *, commit: bool = True,
) -> FieldSignal:
    _require_published_template(conn, template_id, template_version)
    identifier, created_at = _new_identity()
    received_at = received_at or created_at
    conn.execute(
        "INSERT INTO field_signals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (identifier, allocation_id, template_id, template_version, observed_at, received_at, actor_id,
         evidence_artifact_id, _json_value(values), status, supersedes_signal_id, created_at),
    )
    if commit:
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
    license_notes: Optional[str] = None, enabled: bool = False, commit: bool = True,
) -> SourceRegistry:
    _validate_credentials_reference(credentials_reference)
    identifier, created_at = _new_identity()
    try:
        conn.execute(
            """INSERT INTO source_registry VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (identifier, source_key, display_name, source_type, purpose, authority_level, owner_id,
             credentials_reference, endpoint, _json_value(permitted_data_classes), freshness_target_hours,
             license_notes, schema_version, mapping_version, _json_value(default_coverage), bool(enabled), created_at),
        )
        if commit:
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
    next_retry_at: Optional[str] = None, commit: bool = True,
) -> SourceRun:
    identifier, created_at = _new_identity()
    conn.execute(
        "INSERT INTO source_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (identifier, source_id, cursor, _json_value(coverage), fetched_at, status, rows_received,
         rows_accepted, error_summary, next_retry_at, mapping_version, created_at),
    )
    if commit:
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
    status: str = "available", commit: bool = True,
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
    if commit:
        conn.commit()
    return get_regional_signal(conn, identifier)  # type: ignore[return-value]


def get_regional_signal(conn: sqlite3.Connection, regional_signal_id: str) -> Optional[RegionalSignal]:
    row = conn.execute("SELECT * FROM regional_signals WHERE id = ?", (regional_signal_id,)).fetchone()
    return _regional_signal(row) if row is not None else None


def list_regional_signals(conn: sqlite3.Connection, region: str) -> List[RegionalSignal]:
    return [_regional_signal(row) for row in conn.execute(
        "SELECT * FROM regional_signals WHERE region = ? ORDER BY observed_at, created_at", (region,)
    ).fetchall()]


def list_regional_signals_by_source(conn: sqlite3.Connection, source_id: str) -> List[RegionalSignal]:
    return [_regional_signal(row) for row in conn.execute(
        "SELECT * FROM regional_signals WHERE source_id = ? ORDER BY observed_at, created_at", (source_id,)
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


def create_import_rows(
    conn: sqlite3.Connection, import_batch_id: str, rows: Sequence[Mapping[str, Any]], *, commit: bool = True,
) -> int:
    """Insert prepared import rows in one database operation.

    A historical import can contain hundreds or thousands of already-sanitised
    cohorts.  Fetching each inserted row back inside the enclosing transaction
    is useful for an interactive one-row form but makes a private Postgres
    import needlessly slow and can hold a transaction-pooler lease open.  This
    narrow helper accepts only the mapped row envelope the import services
    already own; callers still perform their own lifecycle transaction.
    """
    values = []
    for row in rows:
        identifier, created_at = _new_identity()
        values.append((
            identifier,
            import_batch_id,
            row["row_number"],
            _json_value(row["raw"]),
            _json_value(row["mapped"]),
            row.get("status", "pending"),
            _json_value(row.get("validation_errors", [])),
            row.get("target_entity_type"),
            row.get("target_entity_id"),
            row.get("published_record_id"),
            created_at,
        ))
    if values:
        conn.executemany(
            "INSERT INTO import_rows VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", values,
        )
    if commit:
        conn.commit()
    return len(values)


def get_import_row(conn: sqlite3.Connection, import_row_id: str) -> Optional[ImportRow]:
    row = conn.execute("SELECT * FROM import_rows WHERE id = ?", (import_row_id,)).fetchone()
    return _import_row(row) if row is not None else None


def list_import_rows(conn: sqlite3.Connection, import_batch_id: str) -> List[ImportRow]:
    return [_import_row(row) for row in conn.execute(
        "SELECT * FROM import_rows WHERE import_batch_id = ? ORDER BY row_number", (import_batch_id,)
    ).fetchall()]


def create_trackolap_record(
    conn: sqlite3.Connection, source_id: str, source_run_id: Optional[str],
    import_batch_id: Optional[str], feed: str, source_identifier: str,
    source_updated_at: str, tenant_id: str, values: Any, status: str = "valid",
    commit: bool = True,
) -> TrackolapStoredRecord:
    """Store an immutable source revision, returning an existing replay safely."""
    identifier, created_at = _new_identity()
    cursor = conn.execute(
        """INSERT OR IGNORE INTO trackolap_records
           (id, source_id, source_run_id, import_batch_id, feed, source_identifier,
            source_updated_at, tenant_id, values_json, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            identifier, source_id, source_run_id, import_batch_id, feed, source_identifier,
            source_updated_at, tenant_id, _json_value(values), status, created_at,
        ),
    )
    if cursor.rowcount == 0:
        existing = get_trackolap_record_by_revision(
            conn, source_id, feed, source_identifier, source_updated_at
        )
        if existing is None:
            raise RuntimeError("immutable TrackWick replay could not be resolved")
        return existing
    if commit:
        conn.commit()
    return get_trackolap_record(conn, identifier)  # type: ignore[return-value]


def create_trackolap_records(
    conn: sqlite3.Connection,
    source_id: str,
    source_run_id: Optional[str],
    import_batch_id: Optional[str],
    records: Sequence[Tuple[str, str, str, str, Any]],
    status: str = "valid",
    commit: bool = True,
) -> int:
    """Append provider revisions in one idempotent batch without rereading them.

    Each tuple is ``feed, source_identifier, source_updated_at, tenant_id,
    values``. Existing immutable revisions are intentionally ignored; a later
    provider revision must have a distinct source update time.
    """
    if not records:
        return 0
    rows = []
    for feed, source_identifier, source_updated_at, tenant_id, values in records:
        identifier, created_at = _new_identity()
        rows.append((
            identifier, source_id, source_run_id, import_batch_id, feed,
            source_identifier, source_updated_at, tenant_id, _json_value(values),
            status, created_at,
        ))
    cursor = conn.executemany(
        """INSERT OR IGNORE INTO trackolap_records
           (id, source_id, source_run_id, import_batch_id, feed, source_identifier,
            source_updated_at, tenant_id, values_json, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    if commit:
        conn.commit()
    return cursor.rowcount


def upsert_trackwick_private_records(
    conn: sqlite3.Connection,
    source_id: str,
    source_run_id: Optional[str],
    records: Sequence[Any],
    mapping_version: str,
    *,
    observed_at: Optional[str] = None,
    commit: bool = True,
) -> int:
    """Upsert allow-listed TrackWick evidence without accepting raw payloads.

    ``records`` must expose a reviewed ``table`` name and a mapping of exactly
    the fields owned by that table.  The fixed table/column registry below is
    deliberately the persistence boundary: arbitrary provider keys cannot turn
    into SQL columns or a JSON blob here.  Replays update the latest source
    values and provenance while preserving the first-seen audit timestamp.
    """
    if not records:
        return 0
    now = observed_at or datetime.now(timezone.utc).isoformat()
    grouped: dict[str, list[tuple[Any, ...]]] = {}
    statements: dict[str, str] = {}
    for record in records:
        table = getattr(record, "table", None)
        values = getattr(record, "values", None)
        if table not in _TRACKWICK_PRIVATE_TABLES or not isinstance(values, Mapping):
            raise ValueError("invalid private TrackWick record")
        columns, conflict_columns = _TRACKWICK_PRIVATE_TABLES[table]
        if set(values) != set(columns):
            raise ValueError("private TrackWick record fields do not match its typed table")
        fingerprint = _trackwick_private_fingerprint(values)
        insert_columns = (
            "source_id", "source_run_id", *columns,
            "source_fingerprint", "mapping_version", "data_quality_status",
            "first_seen_at", "last_seen_at", "created_at",
        )
        update_columns = (
            "source_run_id", *(column for column in columns if column != "id"),
            "source_fingerprint", "mapping_version", "data_quality_status", "last_seen_at",
        )
        if table not in statements:
            placeholders = ", ".join("?" for _ in insert_columns)
            assignments = ", ".join(column + " = excluded." + column for column in update_columns)
            statements[table] = (
                "INSERT INTO {table} ({columns}) VALUES ({placeholders}) "
                "ON CONFLICT ({conflict}) DO UPDATE SET {assignments}"
            ).format(
                table=table,
                columns=", ".join(insert_columns),
                placeholders=placeholders,
                conflict=", ".join(conflict_columns),
                assignments=assignments,
            )
        grouped.setdefault(table, []).append((
            source_id,
            source_run_id,
            *(values[column] for column in columns),
            fingerprint,
            mapping_version,
            "valid",
            now,
            now,
            now,
        ))
    written = 0
    for table, rows in grouped.items():
        written += conn.executemany(statements[table], rows).rowcount
    if commit:
        conn.commit()
    return written


def _trackwick_private_fingerprint(values: Mapping[str, Any]) -> str:
    return hashlib.sha256(_json_value(dict(values)).encode("utf-8")).hexdigest()


def _trackwick_plot_reference_key(value: object) -> Optional[str]:
    if not isinstance(value, str):
        return None
    canonical = " ".join(value.split()).casefold()
    return canonical or None


def reconcile_trackwick_task_plot_links(
    conn,
    source_id: str,
    source_run_id: Optional[str],
    mapping_version: str,
    *,
    references_enabled: bool,
    observed_at: Optional[str] = None,
    commit: bool = True,
) -> int:
    """Resolve configured task references to exactly one source plot.

    The provider does not expose a relational task/plot foreign key.  A
    tenant-configured form field may carry a plot's Gata reference, so this
    reconciler admits only an exact canonical match within the same source and
    farmer.  Missing and ambiguous matches remain non-evidence; any previously
    managed association is quarantined before the current graph is rebuilt.
    """
    source_id = _required_text(source_id, "source_id", 128)
    mapping_version = _required_text(mapping_version, "mapping_version", 128)
    now = observed_at or datetime.now(timezone.utc).isoformat()
    written = conn.execute(
        """UPDATE trackwick_task_plot_links
           SET source_run_id = ?, data_quality_status = 'quarantined',
               last_seen_at = ?
           WHERE source_id = ? AND mapping_version = ?
             AND association_kind = 'source_explicit'
             AND data_quality_status != 'quarantined'""",
        (source_run_id, now, source_id, mapping_version),
    ).rowcount
    if not references_enabled:
        if commit:
            conn.commit()
        return written

    matches_by_farmer_and_reference: dict[
        tuple[str, str], list[tuple[str, str]]
    ] = {}
    plot_rows = conn.execute(
        """SELECT registration.id AS registration_id, plot.id AS plot_id,
                  registration.farmer_party_id, plot.gata_number
           FROM trackwick_registrations AS registration
           JOIN trackwick_tasks AS registration_task
             ON registration_task.id = registration.task_id
            AND registration_task.source_id = registration.source_id
            AND registration_task.task_status = 'completed'
            AND registration_task.data_quality_status = 'valid'
           JOIN trackwick_registration_plots AS plot
             ON plot.registration_id = registration.id
            AND plot.source_id = registration.source_id
            AND plot.data_quality_status = 'valid'
           WHERE registration.source_id = ?
             AND registration.registration_status = 'completed'
             AND registration.data_quality_status = 'valid'
             AND registration.farmer_party_id IS NOT NULL
             AND plot.gata_number IS NOT NULL""",
        (source_id,),
    ).fetchall()
    for row in plot_rows:
        reference = _trackwick_plot_reference_key(row["gata_number"])
        if reference is None:
            continue
        matches_by_farmer_and_reference.setdefault(
            (str(row["farmer_party_id"]), reference), []
        ).append((str(row["registration_id"]), str(row["plot_id"])))

    task_rows = conn.execute(
        """SELECT id, farmer_party_id, provider_plot_reference
           FROM trackwick_tasks
           WHERE source_id = ? AND data_quality_status = 'valid'
             AND farmer_party_id IS NOT NULL
             AND provider_plot_reference IS NOT NULL
           ORDER BY id""",
        (source_id,),
    ).fetchall()
    for task in task_rows:
        reference = _trackwick_plot_reference_key(task["provider_plot_reference"])
        if reference is None:
            continue
        matches = matches_by_farmer_and_reference.get(
            (str(task["farmer_party_id"]), reference), []
        )
        if len(matches) != 1:
            continue
        registration_id, plot_id = matches[0]
        task_id = str(task["id"])
        association_id = "tw:task-plot-link:" + hashlib.sha256(
            (source_id + "\x1f" + task_id).encode("utf-8")
        ).hexdigest()[:32]
        values = {
            "id": association_id,
            "task_id": task_id,
            "registration_id": registration_id,
            "plot_id": plot_id,
            "association_kind": "source_explicit",
        }
        fingerprint = _trackwick_private_fingerprint(values)
        written += conn.execute(
            """INSERT INTO trackwick_task_plot_links (
                   id, source_id, source_run_id, task_id, registration_id, plot_id,
                   association_kind, source_fingerprint, mapping_version,
                   data_quality_status, first_seen_at, last_seen_at, created_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'valid', ?, ?, ?)
               ON CONFLICT (task_id) DO UPDATE SET
                   id = excluded.id,
                   source_id = excluded.source_id,
                   source_run_id = excluded.source_run_id,
                   registration_id = excluded.registration_id,
                   plot_id = excluded.plot_id,
                   association_kind = excluded.association_kind,
                   source_fingerprint = excluded.source_fingerprint,
                   mapping_version = excluded.mapping_version,
                   data_quality_status = excluded.data_quality_status,
                   last_seen_at = excluded.last_seen_at""",
            (
                association_id, source_id, source_run_id, task_id,
                registration_id, plot_id, "source_explicit", fingerprint,
                mapping_version, now, now, now,
            ),
        ).rowcount
    if commit:
        conn.commit()
    return written


def get_farm_truth_case(
    conn: sqlite3.Connection, case_id: str,
) -> Optional[FarmTruthReviewCase]:
    row = conn.execute(
        "SELECT * FROM farm_truth_review_cases WHERE id = ?", (case_id,)
    ).fetchone()
    return _farm_truth_review_case(row) if row is not None else None


def _get_farm_truth_case_by_candidate(
    conn: sqlite3.Connection, plot_id: str, candidate_fingerprint: str,
) -> Optional[FarmTruthReviewCase]:
    row = conn.execute(
        """SELECT * FROM farm_truth_review_cases
           WHERE plot_id = ? AND candidate_fingerprint = ?""",
        (plot_id, candidate_fingerprint),
    ).fetchone()
    return _farm_truth_review_case(row) if row is not None else None


def get_farm_truth_case_by_candidate(
    conn: sqlite3.Connection,
    plot_id: str,
    candidate_fingerprint: str,
) -> Optional[FarmTruthReviewCase]:
    return _get_farm_truth_case_by_candidate(conn, plot_id, candidate_fingerprint)


def create_or_refresh_farm_truth_case(
    conn: sqlite3.Connection,
    source_id: str,
    registration_id: str,
    plot_id: str,
    candidate_fingerprint: str,
    evidence_summary: Mapping[str, Any],
) -> FarmTruthReviewCase:
    """Create one open case or refresh only the same still-open candidate.

    The plot/fingerprint uniqueness constraint is the concurrency authority.
    Terminal decisions are immutable; a changed source fingerprint creates a
    distinct review case without mutating the prior decision.
    """
    source_id = _required_text(source_id, "source_id", 128)
    registration_id = _required_text(registration_id, "registration_id", 128)
    plot_id = _required_text(plot_id, "plot_id", 128)
    if not isinstance(candidate_fingerprint, str) or re.fullmatch(
        r"[0-9a-f]{64}", candidate_fingerprint
    ) is None:
        raise ValueError("candidate_fingerprint must be a lowercase SHA-256 hex digest")
    if not isinstance(evidence_summary, Mapping):
        raise ValueError("evidence_summary must be an object")
    summary_json = _json_value(dict(evidence_summary))
    exact_source_unit = conn.execute(
        """SELECT 1
           FROM trackwick_registration_plots AS plot
           JOIN trackwick_registrations AS registration
             ON registration.id = plot.registration_id
           WHERE plot.id = ? AND registration.id = ?
             AND plot.source_id = ? AND registration.source_id = ?""",
        (plot_id, registration_id, source_id, source_id),
    ).fetchone()
    if exact_source_unit is None:
        raise ValueError("farm truth candidate must be one exact registration and plot")

    identifier, created_at = _new_identity()
    conn.execute(
        """INSERT INTO farm_truth_review_cases (
            id, source_id, registration_id, plot_id, candidate_fingerprint, status,
            evidence_summary_json, review_reason, missing_evidence_kind, owner_person_id,
            reviewed_by_person_id, reviewed_at, accepted_land_parcel_id,
            accepted_operational_block_id, accepted_crop_allocation_id,
            accepted_grower_person_id, accepted_field_worker_person_id, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, 'open', ?, NULL, NULL, NULL, NULL, NULL,
                  NULL, NULL, NULL, NULL, NULL, ?, ?)
        ON CONFLICT (plot_id, candidate_fingerprint) DO UPDATE SET
            evidence_summary_json = excluded.evidence_summary_json,
            updated_at = excluded.updated_at
        WHERE farm_truth_review_cases.status = 'open'""",
        (
            identifier, source_id, registration_id, plot_id, candidate_fingerprint,
            summary_json, created_at, created_at,
        ),
    )
    conn.commit()
    established = _get_farm_truth_case_by_candidate(conn, plot_id, candidate_fingerprint)
    if established is None:  # pragma: no cover - protected by insert/upsert semantics
        raise RuntimeError("farm truth review case could not be resolved")
    return established


def list_farm_truth_cases(
    conn: sqlite3.Connection,
    status: Optional[str] = None,
    owner_person_id: Optional[str] = None,
    limit: int = 50,
) -> List[FarmTruthReviewCase]:
    if status is not None and status not in FARM_TRUTH_CASE_STATUSES:
        raise ValueError("invalid farm truth review case status")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")
    where: List[str] = []
    params: List[object] = []
    if status is not None:
        where.append("status = ?")
        params.append(status)
    if owner_person_id is not None:
        where.append("owner_person_id = ?")
        params.append(_required_text(owner_person_id, "owner_person_id", 128))
    clause = " WHERE " + " AND ".join(where) if where else ""
    rows = conn.execute(
        "SELECT * FROM farm_truth_review_cases" + clause
        + " ORDER BY updated_at DESC, id LIMIT ?",
        (*params, limit),
    ).fetchall()
    return [_farm_truth_review_case(row) for row in rows]


def clear_current_farm_truth_open_cases(
    conn: sqlite3.Connection,
    queue_context_keys: Sequence[str],
) -> None:
    """Clear selected queue contexts without touching other review contexts."""
    context_keys = {
        key for key in queue_context_keys
        if isinstance(key, str) and re.fullmatch(r"[0-9a-f]{64}", key)
    }
    if not context_keys:
        return
    rows = conn.execute(
        """SELECT id, evidence_summary_json
           FROM farm_truth_review_cases
           WHERE status = 'open'"""
    ).fetchall()
    _, updated_at = _new_identity()
    updates = []
    for row in rows:
        summary = json.loads(row["evidence_summary_json"])
        contexts = summary.get("_queue_contexts")
        if not isinstance(contexts, dict):
            continue
        changed = False
        for context_key in context_keys:
            if contexts.get(context_key) is True:
                contexts[context_key] = False
                changed = True
        if not changed:
            continue
        summary["_queue_contexts"] = contexts
        updates.append((_json_value(summary), updated_at, row["id"]))
    if updates:
        conn.executemany(
            """UPDATE farm_truth_review_cases
               SET evidence_summary_json = ?, updated_at = ?
               WHERE id = ? AND status = 'open'""",
            updates,
        )
        conn.commit()


def list_latest_farm_truth_cases(
    conn: sqlite3.Connection,
    status: Optional[str] = None,
    owner_person_id: Optional[str] = None,
    queue_context_keys: Optional[Sequence[str]] = None,
) -> List[FarmTruthReviewCase]:
    """Return only the most recently refreshed receipt for each source plot.

    This intentionally has no queue limit: callers must apply their transparent
    evidence ordering before taking a bounded browser-facing slice.  A supplied
    queue context is filtered before receipt de-duplication so activity in one
    source/unit/season cannot shadow the current receipt in another context.
    """
    if status is not None and status not in FARM_TRUTH_CASE_STATUSES:
        raise ValueError("invalid farm truth review case status")
    where: List[str] = []
    params: List[object] = []
    if status is not None:
        where.append("current.status = ?")
        params.append(status)
    if owner_person_id is not None:
        where.append("current.owner_person_id = ?")
        params.append(_required_text(owner_person_id, "owner_person_id", 128))
    if queue_context_keys is not None:
        context_keys = {
            key for key in queue_context_keys
            if isinstance(key, str) and re.fullmatch(r"[0-9a-f]{64}", key)
        }
        if not context_keys:
            return []
        clause = " WHERE " + " AND ".join(where) if where else ""
        rows = conn.execute(
            "SELECT current.* FROM farm_truth_review_cases AS current"
            + clause
            + " ORDER BY current.updated_at DESC, current.id",
            params,
        ).fetchall()
        latest: List[FarmTruthReviewCase] = []
        seen_plots = set()
        for row in rows:
            case = _farm_truth_review_case(row)
            contexts = case.evidence_summary.get("_queue_contexts")
            if not isinstance(contexts, Mapping) or not any(
                contexts.get(key) is True for key in context_keys
            ):
                continue
            if case.plot_id in seen_plots:
                continue
            seen_plots.add(case.plot_id)
            latest.append(case)
        return latest
    clause = " AND " + " AND ".join(where) if where else ""
    rows = conn.execute(
        """SELECT current.*
           FROM farm_truth_review_cases AS current
           WHERE NOT EXISTS (
               SELECT 1 FROM farm_truth_review_cases AS newer
               WHERE newer.plot_id = current.plot_id
                 AND (newer.updated_at > current.updated_at
                      OR (newer.updated_at = current.updated_at AND newer.id > current.id))
           )"""
        + clause
        + " ORDER BY current.updated_at DESC, current.id",
        params,
    ).fetchall()
    return [_farm_truth_review_case(row) for row in rows]


def claim_farm_truth_case(
    conn: sqlite3.Connection,
    case_id: str,
    expected_updated_at: Optional[str] = None,
) -> Optional[FarmTruthReviewCase]:
    """Claim an open case inside the caller's transaction.

    No commit occurs here.  If the acceptance transaction fails, SQLite or
    PostgreSQL rolls this short-lived state back to ``open`` automatically.
    """
    _, updated_at = _new_identity()
    if expected_updated_at is None:
        updated = conn.execute(
            """UPDATE farm_truth_review_cases SET status = 'accepting', updated_at = ?
               WHERE id = ? AND status = 'open'""",
            (updated_at, case_id),
        )
    else:
        updated = conn.execute(
            """UPDATE farm_truth_review_cases SET status = 'accepting', updated_at = ?
               WHERE id = ? AND status = 'open' AND updated_at = ?""",
            (updated_at, case_id, expected_updated_at),
        )
    if updated.rowcount != 1:
        return None
    return get_farm_truth_case(conn, case_id)


def mark_farm_truth_case_needs_evidence(
    conn: sqlite3.Connection,
    case_id: str,
    reviewer_id: str,
    missing_evidence_kind: str,
    reason: str,
    expected_case_updated_at: Optional[str] = None,
) -> FarmTruthReviewCase:
    if missing_evidence_kind not in FARM_TRUTH_MISSING_EVIDENCE_KINDS:
        raise ValueError("invalid missing evidence kind")
    reviewer_id = _required_text(reviewer_id, "reviewer_id", 128)
    reason = _required_text(reason, "reason", 500)
    _, reviewed_at = _new_identity()
    params = (
        reason, missing_evidence_kind, reviewer_id, reviewer_id, reviewed_at,
        reviewed_at, case_id,
    )
    freshness_clause = ""
    if expected_case_updated_at is not None:
        freshness_clause = " AND updated_at = ?"
        params = (*params, expected_case_updated_at)
    updated = conn.execute(
        """UPDATE farm_truth_review_cases
           SET status = 'needs_evidence', review_reason = ?, missing_evidence_kind = ?,
               owner_person_id = ?, reviewed_by_person_id = ?, reviewed_at = ?, updated_at = ?
           WHERE id = ? AND status = 'open'""" + freshness_clause,
        params,
    )
    if updated.rowcount != 1:
        conn.rollback()
        raise ValueError("farm truth review case cannot be marked needs evidence")
    conn.commit()
    return get_farm_truth_case(conn, case_id)  # type: ignore[return-value]


def mark_farm_truth_case_rejected(
    conn: sqlite3.Connection,
    case_id: str,
    reviewer_id: str,
    reason: str,
    expected_case_updated_at: Optional[str] = None,
) -> FarmTruthReviewCase:
    reviewer_id = _required_text(reviewer_id, "reviewer_id", 128)
    reason = _required_text(reason, "reason", 500)
    _, reviewed_at = _new_identity()
    params = (reason, reviewer_id, reviewed_at, reviewed_at, case_id)
    freshness_clause = ""
    if expected_case_updated_at is not None:
        freshness_clause = " AND updated_at = ?"
        params = (*params, expected_case_updated_at)
    updated = conn.execute(
        """UPDATE farm_truth_review_cases
           SET status = 'rejected', review_reason = ?, reviewed_by_person_id = ?,
               reviewed_at = ?, updated_at = ?
           WHERE id = ? AND status = 'open'""" + freshness_clause,
        params,
    )
    if updated.rowcount != 1:
        conn.rollback()
        raise ValueError("farm truth review case cannot be rejected")
    conn.commit()
    return get_farm_truth_case(conn, case_id)  # type: ignore[return-value]


def _insert_farm_truth_relationship(
    conn: sqlite3.Connection,
    person_id: str,
    crop_allocation_id: str,
    role: str,
    starts_on: str,
    reviewer_id: str,
    case_id: str,
) -> None:
    identifier, created_at = _new_identity()
    conn.execute(
        """INSERT INTO person_operating_relationships (
            id, person_id, scope_type, operating_unit_id, land_parcel_id,
            operational_block_id, crop_allocation_id, role, starts_on, ends_on,
            status, provenance, reviewed_by_person_id, ended_by_person_id, ended_at, created_at
        ) VALUES (?, ?, 'crop_allocation', NULL, NULL, NULL, ?, ?, ?, NULL,
                  'active', ?, ?, NULL, NULL, ?)""",
        (
            identifier, person_id, crop_allocation_id, role, starts_on,
            "farm_truth_review_case:" + case_id, reviewer_id, created_at,
        ),
    )


def farm_truth_acceptance_fingerprint(
    operating_unit_id: str,
    season_id: str,
    field_name: str,
    managed_area_hectares: float,
    crop_name: str,
    cultivar: Optional[str],
    grower_effective_on: str,
    right_type: str,
    right_starts_on: str,
    right_ends_on: Optional[str],
    field_worker_party_id: Optional[str],
) -> str:
    """Fingerprint one normalized private acceptance decision request."""
    material = _farm_truth_acceptance_contract(
        operating_unit_id=operating_unit_id,
        season_id=season_id,
        field_name=field_name,
        managed_area_hectares=managed_area_hectares,
        crop_name=crop_name,
        cultivar=cultivar,
        grower_effective_on=grower_effective_on,
        right_type=right_type,
        right_starts_on=right_starts_on,
        right_ends_on=right_ends_on,
        field_worker_party_id=field_worker_party_id,
    )
    canonical = _json_value(material)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _farm_truth_acceptance_contract(
    operating_unit_id: str,
    season_id: str,
    field_name: str,
    managed_area_hectares: float,
    crop_name: str,
    cultivar: Optional[str],
    grower_effective_on: str,
    right_type: str,
    right_starts_on: str,
    right_ends_on: Optional[str],
    field_worker_party_id: Optional[str],
) -> dict[str, Any]:
    """Normalize the complete replay contract before hashing or persisting it."""
    operating_unit_id = _required_text(operating_unit_id, "operating_unit_id", 128)
    season_id = _required_text(season_id, "season_id", 128)
    field_name = _required_text(field_name, "field_name", 160)
    crop_name = _required_text(crop_name, "crop_name", 160)
    cultivar = _optional_text(cultivar, "cultivar", 160)
    grower_effective_on = _require_iso_date(grower_effective_on, "grower_effective_on")
    right_type = _required_text(right_type, "right_type", 160)
    right_starts_on = _require_iso_date(right_starts_on, "right_starts_on")
    if right_ends_on is not None:
        right_ends_on = _require_iso_date(right_ends_on, "right_ends_on")
    if field_worker_party_id is not None:
        field_worker_party_id = _required_text(
            field_worker_party_id, "field_worker_party_id", 128
        )
    if (
        not isinstance(managed_area_hectares, (int, float))
        or isinstance(managed_area_hectares, bool)
        or not math.isfinite(managed_area_hectares)
        or managed_area_hectares <= 0
    ):
        raise ValueError("managed_area_hectares must be positive and finite")
    return {
        "contract_version": 1,
        "operating_unit_id": operating_unit_id,
        "season_id": season_id,
        "field_name": field_name,
        "managed_area_hectares": float(managed_area_hectares),
        "crop_name": crop_name,
        "cultivar": cultivar,
        "grower_effective_on": grower_effective_on,
        "right_type": right_type,
        "right_starts_on": right_starts_on,
        "right_ends_on": right_ends_on,
        "field_worker_party_id": field_worker_party_id,
    }


def farm_truth_candidate_fingerprint(
    registration_source_fingerprint: str,
    plot_source_fingerprint: str,
    eligible_tasks: Sequence[Mapping[str, Any]],
) -> str:
    """Fingerprint the exact registration, plot, and associated task receipt."""
    material = {
        "registration_source_fingerprint": _required_text(
            registration_source_fingerprint, "registration_source_fingerprint", 64
        ),
        "plot_source_fingerprint": _required_text(
            plot_source_fingerprint, "plot_source_fingerprint", 64
        ),
        "eligible_tasks": [dict(task) for task in eligible_tasks],
    }
    canonical = _json_value(material)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _farm_truth_lock_suffix(conn, aliases: str = "") -> str:
    if getattr(conn, "dialect", "sqlite") != "postgres":
        return ""
    return " FOR UPDATE" + (" OF " + aliases if aliases else "")


def _locked_farm_truth_case(conn, case_id: str) -> Optional[FarmTruthReviewCase]:
    row = conn.execute(
        "SELECT * FROM farm_truth_review_cases WHERE id = ?"
        + _farm_truth_lock_suffix(conn),
        (case_id,),
    ).fetchone()
    return _farm_truth_review_case(row) if row is not None else None


def _farm_truth_observed_in_season(value: object, starts_on: str, ends_on: str) -> bool:
    if not isinstance(value, str):
        return False
    try:
        observed = datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return False
    return date.fromisoformat(starts_on) <= observed <= date.fromisoformat(ends_on)


def _current_farm_truth_receipt(
    conn,
    review_case: FarmTruthReviewCase,
    season: Mapping[str, Any],
) -> tuple[Mapping[str, Any], tuple[Mapping[str, Any], ...], list[dict[str, Any]]]:
    """Lock and recompute the exact source receipt used by acceptance."""
    base = conn.execute(
        """SELECT registration.source_fingerprint AS registration_fingerprint,
                  plot.source_fingerprint AS plot_fingerprint,
                  farmer.id AS farmer_party_id,
                  farmer.display_name AS farmer_display_name,
                  registration_task.id AS registration_task_id,
                  registration_task.source_fingerprint AS registration_task_fingerprint,
                  registration_task.task_status AS registration_task_status
           FROM trackwick_registrations AS registration
           JOIN trackwick_registration_plots AS plot
             ON plot.registration_id = registration.id
            AND plot.source_id = registration.source_id
            AND plot.data_quality_status = 'valid'
           JOIN trackwick_parties AS farmer
             ON farmer.id = registration.farmer_party_id
            AND farmer.source_id = registration.source_id
            AND farmer.party_kind = 'farmer'
            AND farmer.data_quality_status = 'valid'
           JOIN trackwick_tasks AS registration_task
             ON registration_task.id = registration.task_id
            AND registration_task.source_id = registration.source_id
            AND registration_task.task_status = 'completed'
            AND registration_task.data_quality_status = 'valid'
           WHERE registration.id = ? AND plot.id = ?
             AND registration.source_id = ?
             AND registration.registration_status = 'completed'
             AND registration.data_quality_status = 'valid'
             AND (COALESCE(plot.reported_area_bigha, 0) > 0
                  OR COALESCE(registration.reported_total_area_acres, 0) > 0)"""
        + _farm_truth_lock_suffix(
            conn, "registration, plot, farmer, registration_task"
        ),
        (review_case.registration_id, review_case.plot_id, review_case.source_id),
    ).fetchone()
    if base is None:
        raise FarmTruthConflict("farm truth source candidate is no longer eligible")

    task_rows = conn.execute(
        """SELECT task.id, task.task_type, task.task_status,
                  task.field_worker_party_id, task.source_fingerprint,
                  association.source_fingerprint AS association_source_fingerprint
           FROM trackwick_tasks AS task
           JOIN trackwick_task_plot_links AS association
             ON association.task_id = task.id
            AND association.source_id = task.source_id
            AND association.data_quality_status = 'valid'
            AND association.association_kind = 'source_explicit'
           JOIN trackwick_registrations AS registration
             ON registration.id = association.registration_id
            AND registration.source_id = association.source_id
            AND registration.farmer_party_id = task.farmer_party_id
           JOIN trackwick_registration_plots AS plot
             ON plot.id = association.plot_id
            AND plot.registration_id = association.registration_id
            AND plot.source_id = association.source_id
           WHERE task.source_id = ?
             AND association.registration_id = ?
             AND association.plot_id = ?
             AND task.data_quality_status = 'valid'
             AND task.farmer_party_id = ?
             AND (task.task_status IN ('pending', 'in_progress')
                  OR (lower(task.task_type) = 'farmer visit'
                      AND task.task_status = 'completed'))
           ORDER BY task.id"""
        + _farm_truth_lock_suffix(conn, "task, association, registration, plot"),
        (
            review_case.source_id, review_case.registration_id, review_case.plot_id,
            base["farmer_party_id"],
        ),
    ).fetchall()

    eligible_tasks: list[Mapping[str, Any]] = []
    task_receipt: list[dict[str, Any]] = [{
        "id": base["registration_task_id"],
        "source_fingerprint": base["registration_task_fingerprint"],
        "status": base["registration_task_status"],
    }]
    current_visit_count = 0
    for task in task_rows:
        visit = conn.execute(
            """SELECT source_fingerprint, observed_at
               FROM trackwick_visits AS visit
               WHERE task_id = ? AND source_id = ?
                 AND data_quality_status = 'valid'"""
            + _farm_truth_lock_suffix(conn, "visit"),
            (task["id"], review_case.source_id),
        ).fetchone()
        is_visit = (
            str(task["task_type"]).lower() == "farmer visit"
            and task["task_status"] == "completed"
        )
        if is_visit and (
            visit is None
            or not _farm_truth_observed_in_season(
                visit["observed_at"], season["starts_on"], season["ends_on"]
            )
        ):
            continue
        if is_visit:
            current_visit_count += 1
        eligible_tasks.append(task)
        task_receipt.append({
            "id": task["id"],
            "source_fingerprint": task["source_fingerprint"],
            "visit_source_fingerprint": (
                visit["source_fingerprint"] if visit is not None else None
            ),
            "association_source_fingerprint": task["association_source_fingerprint"],
            "status": task["task_status"],
        })
    if current_visit_count == 0:
        raise FarmTruthConflict("farm truth source candidate no longer has a current visit")

    task_receipt.sort(key=lambda item: str(item["id"]))
    current_fingerprint = farm_truth_candidate_fingerprint(
        str(base["registration_fingerprint"]),
        str(base["plot_fingerprint"]),
        task_receipt,
    )
    if current_fingerprint != review_case.candidate_fingerprint:
        raise FarmTruthConflict("farm truth source evidence changed; refresh is required")
    return base, tuple(eligible_tasks), task_receipt


def _require_farm_truth_replay_match(
    review_case: FarmTruthReviewCase,
    contract: Mapping[str, Any],
    fingerprint: str,
) -> None:
    established_contract = review_case.evidence_summary.get("_acceptance_contract")
    established_fingerprint = review_case.evidence_summary.get("_acceptance_fingerprint")
    if (
        established_fingerprint != fingerprint
        or (
            established_contract is not None
            and established_contract != contract
        )
    ):
        raise FarmTruthConflict("accepted farm truth result does not match this request")


def accept_farm_truth_case(
    conn: sqlite3.Connection,
    case_id: str,
    reviewer_id: str,
    operating_unit_id: str,
    season_id: str,
    field_name: str,
    managed_area_hectares: float,
    crop_name: str,
    cultivar: Optional[str],
    grower_effective_on: str,
    right_type: str,
    right_starts_on: str,
    right_ends_on: Optional[str],
    selected_task_ids: Sequence[str] = (),
    field_worker_party_id: Optional[str] = None,
    expected_case_updated_at: Optional[str] = None,
) -> FarmTruthReviewCase:
    """Atomically accept one exact source plot into canonical Farm Truth.

    Every canonical row, reviewed source link, case decision, and audit event
    is inserted directly in this single transaction.  Retrying an accepted
    case returns its established IDs; any other stale state is rejected.
    """
    case_id = _required_text(case_id, "case_id", 128)
    reviewer_id = _required_text(reviewer_id, "reviewer_id", 128)
    operating_unit_id = _required_text(operating_unit_id, "operating_unit_id", 128)
    season_id = _required_text(season_id, "season_id", 128)
    field_name = _required_text(field_name, "field_name", 160)
    crop_name = _required_text(crop_name, "crop_name", 160)
    cultivar = _optional_text(cultivar, "cultivar", 160)
    right_type = _required_text(right_type, "right_type", 160)
    grower_effective_on = _require_iso_date(grower_effective_on, "grower_effective_on")
    right_starts_on = _require_iso_date(right_starts_on, "right_starts_on")
    supplied_right_ends_on = right_ends_on
    if right_ends_on is not None:
        right_ends_on = _require_iso_date(right_ends_on, "right_ends_on")
        if date.fromisoformat(right_ends_on) < date.fromisoformat(right_starts_on):
            raise ValueError("right_ends_on must be on or after right_starts_on")
    if (
        not isinstance(managed_area_hectares, (int, float))
        or isinstance(managed_area_hectares, bool)
        or not math.isfinite(managed_area_hectares)
        or managed_area_hectares <= 0
    ):
        raise ValueError("managed_area_hectares must be positive and finite")
    requested_task_ids = tuple(dict.fromkeys(
        _required_text(task_id, "selected_task_id", 128) for task_id in selected_task_ids
    ))

    with conn:
        # SQLite takes a database write reservation before any source reads;
        # PostgreSQL begins its transaction here and row-locks below.
        conn.execute("BEGIN IMMEDIATE")
        review_case = _locked_farm_truth_case(conn, case_id)
        if review_case is None:
            raise ValueError("farm truth review case does not exist")
        if review_case.status == "accepted":
            replay_right_ends_on = right_ends_on
            stored_contract = review_case.evidence_summary.get("_acceptance_contract")
            if (
                supplied_right_ends_on is None
                and isinstance(stored_contract, Mapping)
                and stored_contract.get("operating_unit_id") == operating_unit_id
                and stored_contract.get("season_id") == season_id
                and isinstance(stored_contract.get("right_ends_on"), str)
            ):
                replay_right_ends_on = str(stored_contract["right_ends_on"])
            if replay_right_ends_on is None:
                raise FarmTruthConflict(
                    "accepted farm truth result is missing its replay contract"
                )
            acceptance_contract = _farm_truth_acceptance_contract(
                operating_unit_id=operating_unit_id,
                season_id=season_id,
                field_name=field_name,
                managed_area_hectares=managed_area_hectares,
                crop_name=crop_name,
                cultivar=cultivar,
                grower_effective_on=grower_effective_on,
                right_type=right_type,
                right_starts_on=right_starts_on,
                right_ends_on=replay_right_ends_on,
                field_worker_party_id=field_worker_party_id,
            )
            acceptance_fingerprint = hashlib.sha256(
                _json_value(acceptance_contract).encode("utf-8")
            ).hexdigest()
            _require_farm_truth_replay_match(
                review_case, acceptance_contract, acceptance_fingerprint
            )
            return review_case

        season = conn.execute(
            "SELECT * FROM seasons WHERE id = ? AND operating_unit_id = ?",
            (season_id, operating_unit_id),
        ).fetchone()
        if season is None:
            raise ValueError("season does not belong to the operating unit")
        season_starts_on = date.fromisoformat(season["starts_on"])
        season_ends_on = date.fromisoformat(season["ends_on"])
        if not season_starts_on <= date.today() <= season_ends_on:
            raise ValueError("selected season is not current")
        if review_case.status != "open":
            raise FarmTruthConflict("farm truth review case is already claimed or resolved")
        if (
            expected_case_updated_at is not None
            and review_case.updated_at != expected_case_updated_at
        ):
            raise FarmTruthConflict("farm truth review case is stale, claimed, or resolved")

        if right_ends_on is None:
            right_ends_on = season["ends_on"]
        grower_date = date.fromisoformat(grower_effective_on)
        right_start_date = date.fromisoformat(right_starts_on)
        right_end_date = date.fromisoformat(right_ends_on)
        if not season_starts_on <= grower_date <= season_ends_on:
            raise ValueError("grower_effective_on must fall within the selected season")
        if not right_start_date <= grower_date <= right_end_date:
            raise ValueError(
                "grower_effective_on must fall within the right-to-operate interval"
            )
        if right_start_date > season_starts_on or right_end_date < season_ends_on:
            raise ValueError("right-to-operate interval must cover the selected season")
        acceptance_contract = _farm_truth_acceptance_contract(
            operating_unit_id=operating_unit_id,
            season_id=season_id,
            field_name=field_name,
            managed_area_hectares=managed_area_hectares,
            crop_name=crop_name,
            cultivar=cultivar,
            grower_effective_on=grower_effective_on,
            right_type=right_type,
            right_starts_on=right_starts_on,
            right_ends_on=right_ends_on,
            field_worker_party_id=field_worker_party_id,
        )
        acceptance_fingerprint = hashlib.sha256(
            _json_value(acceptance_contract).encode("utf-8")
        ).hexdigest()

        if conn.execute(
            """SELECT 1 FROM trackwick_plot_operating_links
               WHERE plot_id = ? AND link_status = 'reviewed' LIMIT 1""",
            (review_case.plot_id,),
        ).fetchone() is not None:
            raise FarmTruthConflict("source plot already has a reviewed operating link")

        reviewer = conn.execute("SELECT 1 FROM people WHERE id = ?", (reviewer_id,)).fetchone()
        if reviewer is None:
            raise ValueError("reviewer does not exist")
        farmer, selected_tasks, _receipt = _current_farm_truth_receipt(
            conn, review_case, season
        )
        task_ids = tuple(sorted(str(task["id"]) for task in selected_tasks))
        if requested_task_ids and tuple(sorted(requested_task_ids)) != task_ids:
            raise FarmTruthConflict("farm truth source evidence selection changed")

        field_worker = None
        if field_worker_party_id is not None:
            field_worker_party_id = _required_text(
                field_worker_party_id, "field_worker_party_id", 128
            )
            if not any(
                task["field_worker_party_id"] == field_worker_party_id for task in selected_tasks
            ):
                raise ValueError(
                    "field worker is not supported by the current source evidence"
                )
            field_worker = conn.execute(
                """SELECT id, display_name FROM trackwick_parties AS worker
                   WHERE id = ? AND source_id = ? AND party_kind = 'field_worker'
                     AND data_quality_status = 'valid'"""
                + _farm_truth_lock_suffix(conn, "worker"),
                (field_worker_party_id, review_case.source_id),
            ).fetchone()
            if field_worker is None:
                raise ValueError("field worker source party does not exist")

        claimed = claim_farm_truth_case(
            conn, case_id, expected_updated_at=expected_case_updated_at
        )
        if claimed is None:
            established = _locked_farm_truth_case(conn, case_id)
            if established is not None and established.status == "accepted":
                _require_farm_truth_replay_match(
                    established, acceptance_contract, acceptance_fingerprint
                )
                return established
            raise FarmTruthConflict("farm truth review case is stale, claimed, or resolved")

        land_parcel_id, land_created_at = _new_identity()
        conn.execute(
            "INSERT INTO land_parcels VALUES (?, ?, ?, ?, ?)",
            (land_parcel_id, operating_unit_id, field_name, managed_area_hectares, land_created_at),
        )
        operational_block_id, block_created_at = _new_identity()
        conn.execute(
            "INSERT INTO operational_blocks VALUES (?, ?, ?, ?, ?)",
            (operational_block_id, operating_unit_id, field_name, managed_area_hectares, block_created_at),
        )
        farm_id = _active_farm_for_reviewed_registration(conn, review_case.registration_id)
        if farm_id is None:
            # The approved field name is the first confirmed canonical name for
            # this source registration. Later accepted plots from the same
            # registration become Fields on this same Farm.
            farm_id, farm_created_at = _new_identity()
            conn.execute(
                """INSERT INTO farms
                   (id, operating_unit_id, name, status, reviewed_by_person_id, created_at)
                   VALUES (?, ?, ?, 'active', ?, ?)""",
                (farm_id, operating_unit_id, field_name, reviewer_id, farm_created_at),
            )
        farm_field_id, farm_field_created_at = _new_identity()
        conn.execute(
            """INSERT INTO farm_fields
               (id, farm_id, operational_block_id, starts_on, ends_on, status,
                reviewed_by_person_id, created_at)
               VALUES (?, ?, ?, ?, NULL, 'active', ?, ?)""",
            (
                farm_field_id, farm_id, operational_block_id, grower_effective_on,
                reviewer_id, farm_field_created_at,
            ),
        )
        _, block_link_created_at = _new_identity()
        conn.execute(
            "INSERT INTO block_parcels VALUES (?, ?, ?)",
            (operational_block_id, land_parcel_id, block_link_created_at),
        )
        right_id, right_created_at = _new_identity()
        conn.execute(
            "INSERT INTO rights_to_operate VALUES (?, ?, ?, ?, ?, ?)",
            (
                right_id, land_parcel_id, right_type, right_starts_on,
                right_ends_on, right_created_at,
            ),
        )
        crop_allocation_id, allocation_created_at = _new_identity()
        conn.execute(
            """INSERT INTO crop_allocations VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?)""",
            (
                crop_allocation_id, operating_unit_id, operational_block_id, season_id,
                crop_name, cultivar, managed_area_hectares, allocation_created_at,
            ),
        )

        grower_person_id, grower_created_at = _new_identity()
        conn.execute(
            "INSERT INTO people VALUES (?, ?, 'grower', ?)",
            (grower_person_id, farmer["farmer_display_name"], grower_created_at),
        )
        _insert_farm_truth_relationship(
            conn, grower_person_id, crop_allocation_id, "grower",
            grower_effective_on, reviewer_id, case_id,
        )
        farmer_link_id, farmer_link_created_at = _new_identity()
        conn.execute(
            """INSERT INTO trackwick_party_person_links
               VALUES (?, ?, ?, 'reviewed', ?, ?, ?)""",
            (
                farmer_link_id, farmer["farmer_party_id"], grower_person_id, reviewer_id,
                allocation_created_at, farmer_link_created_at,
            ),
        )

        field_worker_person_id = None
        if field_worker is not None:
            field_worker_person_id, worker_created_at = _new_identity()
            conn.execute(
                "INSERT INTO people VALUES (?, ?, 'field_operator', ?)",
                (field_worker_person_id, field_worker["display_name"], worker_created_at),
            )
            _insert_farm_truth_relationship(
                conn, field_worker_person_id, crop_allocation_id, "field_operator",
                grower_effective_on, reviewer_id, case_id,
            )
            worker_link_id, worker_link_created_at = _new_identity()
            conn.execute(
                """INSERT INTO trackwick_party_person_links
                   VALUES (?, ?, ?, 'reviewed', ?, ?, ?)""",
                (
                    worker_link_id, field_worker["id"], field_worker_person_id, reviewer_id,
                    allocation_created_at, worker_link_created_at,
                ),
            )

        plot_link_id, plot_link_created_at = _new_identity()
        conn.execute(
            """INSERT INTO trackwick_plot_operating_links
               VALUES (?, ?, ?, ?, 'reviewed', ?, ?, ?)""",
            (
                plot_link_id, claimed.plot_id, land_parcel_id, operational_block_id,
                reviewer_id, allocation_created_at, plot_link_created_at,
            ),
        )
        for task in selected_tasks:
            task_link_id, task_link_created_at = _new_identity()
            conn.execute(
                """INSERT INTO trackwick_task_allocation_links
                   VALUES (?, ?, ?, 'reviewed', ?, ?, ?)""",
                (
                    task_link_id, task["id"], crop_allocation_id, reviewer_id,
                    allocation_created_at, task_link_created_at,
                ),
            )

        audit_id, reviewed_at = _new_identity()
        audit_metadata = _json_value({
            "action": "farm_truth_accepted",
            "case_id": case_id,
            "plot_id": claimed.plot_id,
            "registration_id": claimed.registration_id,
            "source_id": claimed.source_id,
            "task_ids": list(task_ids),
        })
        conn.execute(
            "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                audit_id, "farm_truth_review_case", case_id, "open", "accepted",
                reviewer_id, audit_metadata, reviewed_at,
            ),
        )
        accepted_evidence_summary = dict(claimed.evidence_summary)
        accepted_evidence_summary["_acceptance_fingerprint"] = acceptance_fingerprint
        accepted_evidence_summary["_acceptance_contract"] = acceptance_contract
        updated = conn.execute(
            """UPDATE farm_truth_review_cases
               SET status = 'accepted', review_reason = ?, reviewed_by_person_id = ?,
                   reviewed_at = ?, accepted_land_parcel_id = ?,
                   accepted_operational_block_id = ?, accepted_crop_allocation_id = ?,
                   accepted_grower_person_id = ?, accepted_field_worker_person_id = ?,
                   evidence_summary_json = ?, updated_at = ?
               WHERE id = ? AND status = 'accepting'""",
            (
                "Accepted as reviewed Farm Truth", reviewer_id, reviewed_at,
                land_parcel_id, operational_block_id, crop_allocation_id,
                grower_person_id, field_worker_person_id,
                _json_value(accepted_evidence_summary), reviewed_at, case_id,
            ),
        )
        if updated.rowcount != 1:  # pragma: no cover - guarded by the claim
            raise RuntimeError("claimed farm truth review case could not be accepted")

    return get_farm_truth_case(conn, case_id)  # type: ignore[return-value]


def _active_farm_for_reviewed_registration(conn, registration_id: str) -> Optional[str]:
    """Return the Farm already established by another reviewed plot in a registration."""
    # Lock the source registration before the membership lookup so concurrent
    # acceptance of two plots cannot create two canonical Farms for one farm
    # candidate. SQLite's transaction lock supplies the equivalent guarantee.
    conn.execute(
        "SELECT registration.id FROM trackwick_registrations AS registration WHERE registration.id = ?"
        + _farm_truth_lock_suffix(conn, "registration"),
        (registration_id,),
    ).fetchone()
    row = conn.execute(
        """SELECT farm.id
           FROM trackwick_registration_plots AS plot
           JOIN trackwick_plot_operating_links AS link
             ON link.plot_id = plot.id AND link.link_status = 'reviewed'
           JOIN farm_fields AS membership
             ON membership.operational_block_id = link.operational_block_id
              AND membership.status = 'active'
           JOIN farms AS farm ON farm.id = membership.farm_id AND farm.status = 'active'
           WHERE plot.registration_id = ?
           ORDER BY farm.created_at, farm.id
           LIMIT 1""",
        (registration_id,),
    ).fetchone()
    return None if row is None else str(row["id"])


def get_trackolap_record(conn: sqlite3.Connection, record_id: str) -> Optional[TrackolapStoredRecord]:
    row = conn.execute("SELECT * FROM trackolap_records WHERE id = ?", (record_id,)).fetchone()
    return _trackolap_record(row) if row is not None else None


def get_trackolap_record_by_revision(
    conn: sqlite3.Connection, source_id: str, feed: str, source_identifier: str, source_updated_at: str,
) -> Optional[TrackolapStoredRecord]:
    row = conn.execute(
        """SELECT * FROM trackolap_records
           WHERE source_id = ? AND feed = ? AND source_identifier = ? AND source_updated_at = ?""",
        (source_id, feed, source_identifier, source_updated_at),
    ).fetchone()
    return _trackolap_record(row) if row is not None else None


def list_trackolap_records(
    conn: sqlite3.Connection, source_id: str, statuses: Optional[Tuple[str, ...]] = None,
) -> List[TrackolapStoredRecord]:
    if statuses is None:
        rows = conn.execute(
            """SELECT * FROM trackolap_records
               WHERE source_id = ? ORDER BY feed, source_updated_at, source_identifier""",
            (source_id,),
        ).fetchall()
    else:
        if not statuses:
            return []
        placeholders = ", ".join("?" for _ in statuses)
        rows = conn.execute(
            """SELECT * FROM trackolap_records WHERE source_id = ? AND status IN ("""
            + placeholders
            + ") ORDER BY feed, source_updated_at, source_identifier",
            (source_id, *statuses),
        ).fetchall()
    return [_trackolap_record(row) for row in rows]


def publish_trackolap_records(conn: sqlite3.Connection, import_batch_id: str, commit: bool = True) -> int:
    """Advance normalized records only after their linked batch is published."""
    cursor = conn.execute(
        "UPDATE trackolap_records SET status = 'published' WHERE import_batch_id = ? AND status = 'valid'",
        (import_batch_id,),
    )
    if commit:
        conn.commit()
    return cursor.rowcount


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
    if status == "eligible":
        if enrolled_at is not None:
            raise ValueError("eligible trial allocations cannot have enrolled_at")
        enrolled_at = None
    elif status == "enrolled":
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
