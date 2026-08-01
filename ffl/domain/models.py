from dataclasses import dataclass
from typing import Optional


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
