from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class OperatingUnit:
    id: str
    name: str
    created_at: str


@dataclass(frozen=True)
class LandParcel:
    id: str
    operating_unit_id: str
    name: str
    area_hectares: float
    created_at: str


@dataclass(frozen=True)
class OperationalBlock:
    id: str
    operating_unit_id: str
    name: str
    area_hectares: float
    created_at: str


@dataclass(frozen=True)
class RightToOperate:
    id: str
    land_parcel_id: str
    right_type: str
    starts_on: str
    ends_on: str
    created_at: str


@dataclass(frozen=True)
class Season:
    id: str
    operating_unit_id: str
    name: str
    starts_on: str
    ends_on: str
    created_at: str


@dataclass(frozen=True)
class CropAllocation:
    id: str
    operating_unit_id: str
    operational_block_id: str
    season_id: str
    crop_name: str
    cultivar: Optional[str]
    area_hectares: float
    status: str
    created_at: str


@dataclass(frozen=True)
class Person:
    id: str
    name: str
    role: str
    created_at: str


@dataclass(frozen=True)
class SignalTemplate:
    id: str
    name: str
    version: int
    status: str
    fields: List[Dict[str, Any]]
    owner_id: str
    published_at: str


@dataclass(frozen=True)
class WorkItem:
    id: str
    allocation_id: str
    title: str
    owner_id: str
    due_at: str
    status: str
    created_at: str


@dataclass(frozen=True)
class ExceptionRecord:
    id: str
    allocation_id: str
    title: str
    severity: str
    owner_id: str
    fallback_owner_id: str
    observed_at: str
    idempotency_key: str
    status: str
    created_at: str


@dataclass(frozen=True)
class Decision:
    id: str
    allocation_id: str
    title: str
    owner_id: str
    review_due_at: str
    status: str
    created_at: str


@dataclass(frozen=True)
class AuditEvent:
    id: str
    entity_type: str
    entity_id: str
    from_status: str
    to_status: str
    actor_id: str
    reason: str
    created_at: str


@dataclass(frozen=True)
class EvidenceArtifact:
    id: str
    content_hash: str
    media_type: str
    storage_reference: str
    original_filename: Optional[str]
    size_bytes: Optional[int]
    source_uri: Optional[str]
    created_by_person_id: Optional[str]
    created_at: str


@dataclass(frozen=True)
class FieldSignal:
    id: str
    allocation_id: str
    template_id: str
    template_version: int
    observed_at: str
    received_at: str
    actor_id: str
    evidence_artifact_id: Optional[str]
    values: Any
    status: str
    supersedes_signal_id: Optional[str]
    created_at: str


@dataclass(frozen=True)
class CropStageCheckpoint:
    id: str
    allocation_id: str
    stage_name: str
    planned_for: str
    status: str
    expected_evidence: Any
    template_id: Optional[str]
    template_version: Optional[int]
    completed_at: Optional[str]
    supersedes_checkpoint_id: Optional[str]
    created_at: str


@dataclass(frozen=True)
class HarvestRecord:
    id: str
    allocation_id: str
    harvest_starts_on: str
    harvest_ends_on: Optional[str]
    quantity: float
    canonical_unit: str
    measurement_method: str
    quality_metrics: Any
    evidence_artifact_id: Optional[str]
    status: str
    correction_of_id: Optional[str]
    corrected_by_person_id: Optional[str]
    correction_reason: Optional[str]
    created_at: str


@dataclass(frozen=True)
class SeasonReview:
    id: str
    allocation_id: str
    owner_id: str
    confirmed_practices: Any
    invalidated_assumptions: Any
    unresolved_questions: Any
    proposed_playbook_changes: Any
    status: str
    reviewed_at: Optional[str]
    created_at: str


@dataclass(frozen=True)
class SourceRegistry:
    id: str
    source_key: str
    display_name: str
    source_type: str
    purpose: str
    authority_level: str
    owner_id: str
    credentials_reference: Optional[str]
    endpoint: Optional[str]
    permitted_data_classes: Any
    freshness_target_hours: Optional[float]
    license_notes: Optional[str]
    schema_version: str
    mapping_version: str
    default_coverage: Any
    enabled: bool
    created_at: str


@dataclass(frozen=True)
class SourceRun:
    id: str
    source_id: str
    cursor: Optional[str]
    coverage: Any
    fetched_at: Optional[str]
    status: str
    rows_received: int
    rows_accepted: int
    error_summary: Optional[str]
    next_retry_at: Optional[str]
    mapping_version: str
    created_at: str


@dataclass(frozen=True)
class RegionalSignal:
    id: str
    source_id: str
    source_run_id: Optional[str]
    source_identifier: str
    source_url: Optional[str]
    region: str
    signal_type: str
    observed_at: str
    received_at: str
    valid_from: Optional[str]
    valid_to: Optional[str]
    coverage: Any
    resolution: Optional[str]
    freshness_target_hours: Optional[float]
    signal_kind: str
    value: Any
    status: str
    created_at: str


@dataclass(frozen=True)
class ImportBatch:
    id: str
    purpose: str
    status: str
    content_hash: str
    evidence_artifact_id: str
    mapping_version: str
    source_id: Optional[str]
    owner_id: str
    received_at: str
    reviewed_at: Optional[str]
    reviewed_by_id: Optional[str]
    published_at: Optional[str]
    profile: Any
    created_at: str


@dataclass(frozen=True)
class ImportRow:
    id: str
    import_batch_id: str
    row_number: int
    raw: Any
    mapped: Any
    status: str
    validation_errors: Any
    target_entity_type: Optional[str]
    target_entity_id: Optional[str]
    published_record_id: Optional[str]
    created_at: str


@dataclass(frozen=True)
class Playbook:
    id: str
    name: str
    version: int
    status: str
    owner_id: str
    protocol: Any
    effective_from: Optional[str]
    approved_by_person_id: Optional[str]
    approved_at: Optional[str]
    created_at: str


@dataclass(frozen=True)
class Trial:
    id: str
    name: str
    hypothesis: str
    owner_id: str
    protocol_version: str
    decision_question: str
    treatment: Any
    comparator: Any
    eligibility_rule: Any
    measurements: Any
    guardrails: Any
    status: str
    starts_on: Optional[str]
    ends_on: Optional[str]
    status_reason: Optional[str]
    created_at: str


@dataclass(frozen=True)
class TrialAllocation:
    id: str
    trial_id: str
    allocation_id: str
    arm: str
    status: str
    enrolled_at: str
    withdrawn_at: Optional[str]
    reason: Optional[str]
    created_at: str


@dataclass(frozen=True)
class TrialConfounder:
    id: str
    trial_id: str
    allocation_id: Optional[str]
    category: str
    description: str
    observed_at: str
    evidence_artifact_id: Optional[str]
    actor_id: str
    created_at: str


@dataclass(frozen=True)
class TrialConclusion:
    id: str
    trial_id: str
    reviewer_id: str
    status: str
    result: Any
    confidence_level: str
    limitations: Any
    evidence_artifact_id: Optional[str]
    playbook_id: Optional[str]
    playbook_decision: str
    approved_at: Optional[str]
    created_at: str
