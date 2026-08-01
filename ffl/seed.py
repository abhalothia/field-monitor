import sqlite3

from ffl.persistence import repository
from ffl.services.operations import create_work_item
from ffl.services.templates import publish_signal_template


def _person_by_name(conn: sqlite3.Connection, name: str):
    row = conn.execute("SELECT * FROM people WHERE name = ?", (name,)).fetchone()
    return repository._person(row) if row is not None else None


def seed_pilot(conn: sqlite3.Connection) -> dict:
    """Create the repeatable, minimal dataset used by the FFL pilot."""
    unit_row = conn.execute(
        "SELECT * FROM operating_units WHERE name = ?", ("FFL Pilot Farm",)
    ).fetchone()
    unit = repository._operating_unit(unit_row) if unit_row is not None else repository.create_operating_unit(
        conn, "FFL Pilot Farm"
    )

    block_row = conn.execute(
        "SELECT * FROM operational_blocks WHERE operating_unit_id = ? AND name = ?",
        (unit.id, "North Block"),
    ).fetchone()
    block = repository._operational_block(block_row) if block_row is not None else repository.create_operational_block(
        conn, unit.id, "North Block", 5.0
    )

    season_row = conn.execute(
        "SELECT * FROM seasons WHERE operating_unit_id = ? AND name = ?", (unit.id, "Kharif 2026")
    ).fetchone()
    season = repository._season(season_row) if season_row is not None else repository.create_season(
        conn, unit.id, "Kharif 2026", "2026-06-01", "2026-11-30"
    )

    allocation_row = conn.execute(
        """SELECT * FROM crop_allocations WHERE operating_unit_id = ? AND operational_block_id = ?
           AND season_id = ? AND crop_name = ? AND cultivar = ?""",
        (unit.id, block.id, season.id, "Rice", "Pusa 1121"),
    ).fetchone()
    allocation = repository._crop_allocation(allocation_row) if allocation_row is not None else repository.create_crop_allocation(
        conn, unit.id, block.id, season.id, "Rice", "Pusa 1121", 5.0
    )

    manager = _person_by_name(conn, "Farm Manager") or repository.create_person(
        conn, "Farm Manager", "farm_manager"
    )
    operator = _person_by_name(conn, "Field Operator") or repository.create_person(
        conn, "Field Operator", "field_operator"
    )
    lead = _person_by_name(conn, "Operations Lead") or repository.create_person(
        conn, "Operations Lead", "operations_lead"
    )

    if repository.get_signal_template(conn, "crop_exception", 1) is None:
        publish_signal_template(
            conn,
            "crop_exception",
            1,
            [
                {"key": "severity", "type": "choice", "required": True,
                 "options": ["low", "medium", "high", "critical"]},
                {"key": "photo_url", "type": "photo", "required": True},
            ],
            lead.id,
        )

    existing_work = conn.execute(
        "SELECT id FROM work_items WHERE allocation_id = ? AND title = ?",
        (allocation.id, "Inspect irrigation readiness"),
    ).fetchone()
    if existing_work is None:
        create_work_item(
            conn, allocation.id, "Inspect irrigation readiness", manager.id,
            "2026-07-10T09:00:00+00:00", initial_status="planned",
        )

    return {
        "operating_unit_id": unit.id,
        "allocation_id": allocation.id,
        "manager_id": manager.id,
        "operator_id": operator.id,
        "lead_id": lead.id,
    }
