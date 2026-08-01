import sqlite3
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from ffl.domain.models import (
    CropAllocation,
    LandParcel,
    OperatingUnit,
    OperationalBlock,
    Person,
    RightToOperate,
    Season,
)


def _new_identity() -> Tuple[str, str]:
    return str(uuid.uuid4()), datetime.now(timezone.utc).isoformat()


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


def list_active_crop_allocations(conn: sqlite3.Connection, operating_unit_id: str) -> List[CropAllocation]:
    rows = conn.execute(
        "SELECT * FROM crop_allocations WHERE operating_unit_id = ? AND status = 'active' ORDER BY created_at",
        (operating_unit_id,),
    ).fetchall()
    return [_crop_allocation(row) for row in rows]
