"""Safe, manager-facing farm and farmer profile DTOs.

Canonical records are deliberately kept separate from TrackWick's reported
candidate context.  These helpers only return small whitelisted dictionaries:
they never expose provenance, contacts, coordinates, provider values, or an
authentication claim.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ffl.services.trackwick_board import manager_board_for_source


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
    }


def farmer_profile(conn, person_id: str) -> dict[str, Any] | None:
    """Return the canonical, reviewed relationships for one person."""
    person = conn.execute(
        "SELECT id, name FROM people WHERE id = ?", (person_id,)
    ).fetchone()
    if person is None:
        return None

    relationships = conn.execute(
        """SELECT scope_type, role, starts_on
           FROM person_operating_relationships
           WHERE person_id = ? AND status = 'active' AND reviewed_by_person_id IS NOT NULL
           ORDER BY starts_on, role, id""",
        (person["id"],),
    ).fetchall()
    return {
        "state": "reviewed",
        "kind": "farmer",
        "id": person["id"],
        "name": person["name"],
        "relationships": [
            {
                "scope_type": row["scope_type"],
                "role": row["role"],
                "starts_on": row["starts_on"],
            }
            for row in relationships
        ],
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
        """SELECT id, title, due_at, status
           FROM work_items
           WHERE allocation_id IN (""" + placeholders + """)
           ORDER BY due_at, id""",
        tuple(allocation_ids),
    ).fetchall()
    return [
        {
            "id": row["id"],
            "title": row["title"],
            "due_at": row["due_at"],
            "status": row["status"],
        }
        for row in rows
    ]


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
