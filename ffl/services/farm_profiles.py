"""Safe, manager-facing farm and farmer profile DTOs.

Canonical records are deliberately kept separate from TrackWick's reported
candidate context.  These helpers only return small whitelisted dictionaries:
they never expose provenance, contacts, coordinates, provider values, or an
authentication claim.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from ffl.services.trackwick_board import manager_board_for_source


_FIELD_RECORD_LIMITATION = "Latest activity reflects canonical non-draft field signals only."


def farm_profile(conn, block_id: str) -> dict[str, Any] | None:
    """Return reviewed operational context for one canonical farm block."""
    block = conn.execute(
        "SELECT id, name, area_hectares FROM operational_blocks WHERE id = ?", (block_id,)
    ).fetchone()
    if block is None:
        return None

    allocations = _active_allocations(conn, block["id"])
    return {
        "state": "reviewed",
        "kind": "farm",
        "id": block["id"],
        "name": block["name"],
        "current": _current_crop(allocations),
        "people": _reviewed_people_for_block(conn, block["id"], allocations),
        "work": _reviewed_work_for_allocations(conn, [row["id"] for row in allocations]),
        "location": _published_geometry_state(conn, block["id"]),
        "record": _reviewed_field_record(conn, block["id"]),
    }


def farmer_profile(conn, person_id: str) -> dict[str, Any] | None:
    """Return the canonical, reviewed relationships for one person."""
    person = conn.execute(
        "SELECT id, name FROM people WHERE id = ?", (person_id,)
    ).fetchone()
    if person is None:
        return None

    relationships = _reviewed_relationships_for_person(conn, person["id"])
    return {
        "state": "reviewed",
        "kind": "farmer",
        "id": person["id"],
        "name": person["name"],
        "relationships": relationships,
        "farms": _linked_farms_for_reviewed_relationships(conn, person["id"]),
    }


def reported_farm_profile(conn, candidate_id: str) -> dict[str, Any] | None:
    """Return safe reported candidate context without a source location."""
    row = next(
        (item for item in manager_board_for_source(conn)["farms"] if item["id"] == candidate_id),
        None,
    )
    if row is None:
        return None
    return {
        "state": "reported",
        "kind": "farm",
        "id": row["id"],
        "name": row["place"],
        "reported": _reported_farm_summary(row),
        "limitations": [
            "Reported candidate context is not a reviewed Fortune farm or field boundary."
        ],
    }


def reported_farmer_profile(conn, party_id: str) -> dict[str, Any] | None:
    """Return safe reported farmer context without creating a login claim."""
    row = next(
        (item for item in manager_board_for_source(conn)["farmers"] if item["id"] == party_id),
        None,
    )
    if row is None:
        return None
    return {
        "state": "reported",
        "kind": "farmer",
        "id": row["id"],
        "name": row["name"],
        "reported": _reported_farmer_summary(row),
        "account": {"state": "not_created"},
        "limitations": [
            "Reported source context is not a reviewed Fortune relationship or sign-in."
        ],
    }


def _active_allocations(conn, block_id: str) -> list[Mapping[str, Any]]:
    return list(conn.execute(
        """SELECT id, crop_name, cultivar
           FROM crop_allocations
           WHERE operational_block_id = ? AND status = 'active'
           ORDER BY created_at DESC, id DESC""",
        (block_id,),
    ).fetchall())


def _current_crop(allocations: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    if not allocations:
        return None
    allocation = allocations[0]
    return {"crop_name": allocation["crop_name"], "cultivar": allocation["cultivar"]}


def _reviewed_people_for_block(
    conn, block_id: str, allocations: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    allocation_ids = [row["id"] for row in allocations]
    allocation_predicate = "0 = 1"
    params: list[Any] = [block_id, block_id]
    if allocation_ids:
        placeholders = ", ".join("?" for _ in allocation_ids)
        allocation_predicate = "relationship.crop_allocation_id IN (" + placeholders + ")"
        params.extend(allocation_ids)
    rows = conn.execute(
        """SELECT person.id, person.name, relationship.role, relationship.starts_on
           FROM person_operating_relationships AS relationship
           JOIN people AS person ON person.id = relationship.person_id
           WHERE relationship.status = 'active'
             AND relationship.reviewed_by_person_id IS NOT NULL
             AND (
                 relationship.operational_block_id = ?
                 OR relationship.land_parcel_id IN (
                     SELECT land_parcel_id FROM block_parcels
                     WHERE operational_block_id = ?
                 )
                 OR """ + allocation_predicate + """
             )
           ORDER BY relationship.starts_on, person.name, relationship.role, relationship.id""",
        tuple(params),
    ).fetchall()
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "role": row["role"],
            "starts_on": row["starts_on"],
        }
        for row in rows
    ]


def _reviewed_work_for_allocations(conn, allocation_ids: Sequence[str]) -> list[dict[str, Any]]:
    if not allocation_ids:
        return []
    placeholders = ", ".join("?" for _ in allocation_ids)
    rows = conn.execute(
        """SELECT id, title, status
           FROM work_items
           WHERE allocation_id IN (""" + placeholders + """)
           ORDER BY id""",
        tuple(allocation_ids),
    ).fetchall()
    return [
        {
            "id": row["id"],
            "title": row["title"],
            "status": row["status"],
        }
        for row in rows
    ]


def _reviewed_field_record(conn, block_id: str) -> dict[str, Any]:
    rows = conn.execute(
        """SELECT signal.observed_at
           FROM field_signals AS signal
           JOIN crop_allocations AS allocation ON allocation.id = signal.allocation_id
           WHERE allocation.operational_block_id = ? AND signal.status != 'draft'""",
        (block_id,),
    ).fetchall()
    latest_observed_at = max(
        (row["observed_at"] for row in rows), key=_timestamp_instant, default=None
    )
    return {
        "latest_observed_at": latest_observed_at,
        "limitation": _FIELD_RECORD_LIMITATION,
    }


def _timestamp_instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("field observation timestamps must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def _reviewed_relationships_for_person(conn, person_id: str) -> list[dict[str, str]]:
    rows = conn.execute(
        """SELECT relationship.scope_type, relationship.role, relationship.starts_on,
                  CASE relationship.scope_type
                    WHEN 'operating_unit' THEN operating_unit.name
                    WHEN 'land_parcel' THEN land_parcel.name
                    WHEN 'operational_block' THEN operational_block.name
                    WHEN 'crop_allocation' THEN allocation_block.name
                  END AS scope_name
           FROM person_operating_relationships AS relationship
           LEFT JOIN operating_units AS operating_unit
             ON operating_unit.id = relationship.operating_unit_id
           LEFT JOIN land_parcels AS land_parcel
             ON land_parcel.id = relationship.land_parcel_id
           LEFT JOIN operational_blocks AS operational_block
             ON operational_block.id = relationship.operational_block_id
           LEFT JOIN crop_allocations AS allocation
             ON allocation.id = relationship.crop_allocation_id
           LEFT JOIN operational_blocks AS allocation_block
             ON allocation_block.id = allocation.operational_block_id
           WHERE relationship.person_id = ? AND relationship.status = 'active'
             AND relationship.reviewed_by_person_id IS NOT NULL
           ORDER BY relationship.starts_on, relationship.role, relationship.id""",
        (person_id,),
    ).fetchall()
    return [
        {
            "scope_type": row["scope_type"],
            "scope_name": row["scope_name"],
            "role": row["role"],
            "starts_on": row["starts_on"],
        }
        for row in rows
    ]


def _linked_farms_for_reviewed_relationships(conn, person_id: str) -> list[dict[str, Any]]:
    blocks = conn.execute(
        """WITH reviewed_relationships AS (
               SELECT scope_type, operating_unit_id, land_parcel_id,
                      operational_block_id, crop_allocation_id
               FROM person_operating_relationships
               WHERE person_id = ? AND status = 'active' AND reviewed_by_person_id IS NOT NULL
           ), linked_blocks(block_id) AS (
               SELECT operational_block_id FROM reviewed_relationships
               WHERE scope_type = 'operational_block'
               UNION
               SELECT allocation.operational_block_id
               FROM reviewed_relationships AS relationship
               JOIN crop_allocations AS allocation ON allocation.id = relationship.crop_allocation_id
               WHERE relationship.scope_type = 'crop_allocation'
               UNION
               SELECT link.operational_block_id
               FROM reviewed_relationships AS relationship
               JOIN block_parcels AS link ON link.land_parcel_id = relationship.land_parcel_id
               WHERE relationship.scope_type = 'land_parcel'
               UNION
               SELECT block.id
               FROM reviewed_relationships AS relationship
               JOIN operational_blocks AS block ON block.operating_unit_id = relationship.operating_unit_id
               WHERE relationship.scope_type = 'operating_unit'
           )
           SELECT block.id, block.name
           FROM linked_blocks
           JOIN operational_blocks AS block ON block.id = linked_blocks.block_id
           ORDER BY block.name, block.id""",
        (person_id,),
    ).fetchall()
    farms = []
    for block in blocks:
        allocations = _active_allocations(conn, block["id"])
        farms.append({
            "id": block["id"],
            "name": block["name"],
            "current": _current_crop(allocations),
            "open_work_count": _open_work_count_for_allocations(
                conn, [allocation["id"] for allocation in allocations]
            ),
        })
    return farms


def _open_work_count_for_allocations(conn, allocation_ids: Sequence[str]) -> int:
    if not allocation_ids:
        return 0
    placeholders = ", ".join("?" for _ in allocation_ids)
    row = conn.execute(
        """SELECT count(id) AS count FROM work_items
           WHERE allocation_id IN (""" + placeholders + """)
             AND status IN ('planned', 'in_progress', 'blocked', 'submitted', 'rejected')""",
        tuple(allocation_ids),
    ).fetchone()
    return row["count"]


def _published_geometry_state(conn, block_id: str) -> dict[str, str]:
    # Canonical blocks have no published geometry DTO yet.  Do not infer one
    # from a parcel, administrative place, or TrackWick source point.
    del conn, block_id
    return {"state": "not_published"}


def _reported_farm_summary(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: row[key]
        for key in (
            "farmer_name",
            "place",
            "registration_status",
            "reported_area_acres",
            "reported_plot_count",
            "pb1_area_acres",
            "var1718_area_acres",
            "open_work",
            "latest_activity_at",
            "plot_photo_references",
            "crop_photo_references",
        )
    }


def _reported_farmer_summary(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: row[key]
        for key in (
            "farm_candidates",
            "reported_area_acres",
            "open_work",
            "latest_activity_at",
            "crop_photo_references",
        )
    }
