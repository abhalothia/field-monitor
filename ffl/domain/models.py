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
