import sqlite3
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from ffl.domain.models import (
    AuditEvent,
    CropAllocation,
    Decision,
    ExceptionRecord,
    LandParcel,
    OperatingUnit,
    OperationalBlock,
    Person,
    RightToOperate,
    Season,
    WorkItem,
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


def create_work_item(
    conn: sqlite3.Connection, allocation_id: str, title: str, owner_id: str, due_at: str
) -> WorkItem:
    identifier, created_at = _new_identity()
    status = "in_progress"
    conn.execute(
        "INSERT INTO work_items VALUES (?, ?, ?, ?, ?, ?, ?)",
        (identifier, allocation_id, title, owner_id, due_at, status, created_at),
    )
    conn.commit()
    return WorkItem(identifier, allocation_id, title, owner_id, due_at, status, created_at)


def get_work_item(conn: sqlite3.Connection, work_item_id: str) -> Optional[WorkItem]:
    row = conn.execute("SELECT * FROM work_items WHERE id = ?", (work_item_id,)).fetchone()
    return _work_item(row) if row is not None else None


def update_work_item_status(conn: sqlite3.Connection, work_item_id: str, status: str) -> WorkItem:
    conn.execute("UPDATE work_items SET status = ? WHERE id = ?", (status, work_item_id))
    conn.commit()
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
    conn.execute(
        "INSERT INTO exception_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (identifier, allocation_id, title, severity, owner_id, fallback_owner_id, observed_at,
         idempotency_key, status, created_at),
    )
    conn.commit()
    return ExceptionRecord(identifier, allocation_id, title, severity, owner_id, fallback_owner_id,
                           observed_at, idempotency_key, status, created_at)


def get_exception_record(conn: sqlite3.Connection, exception_id: str) -> Optional[ExceptionRecord]:
    row = conn.execute("SELECT * FROM exception_records WHERE id = ?", (exception_id,)).fetchone()
    return _exception_record(row) if row is not None else None


def update_exception_status(conn: sqlite3.Connection, exception_id: str, status: str) -> ExceptionRecord:
    conn.execute("UPDATE exception_records SET status = ? WHERE id = ?", (status, exception_id))
    conn.commit()
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
