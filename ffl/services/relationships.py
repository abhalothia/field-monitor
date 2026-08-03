"""Governed person-to-operating-scope relationship workflow.

The service keeps the relationship model intentionally small: it records what
scope a person is accountable to, in which role, and over what period.  It
does not infer farm ownership, current crop condition, or a person's identity
from imported supply data.
"""

from dataclasses import asdict
from typing import List, Optional

from ffl.domain.models import PersonOperatingRelationship
from ffl.persistence import repository


def relationship_scope_id(relationship: PersonOperatingRelationship) -> str:
    values = {
        "operating_unit": relationship.operating_unit_id,
        "land_parcel": relationship.land_parcel_id,
        "operational_block": relationship.operational_block_id,
        "crop_allocation": relationship.crop_allocation_id,
    }
    scope_id = values.get(relationship.scope_type)
    if scope_id is None:  # defensive: the database CHECK is the durable guard.
        raise ValueError("person operating relationship has an invalid scope")
    return scope_id


def relationship_summary(relationship: PersonOperatingRelationship) -> dict:
    """Return a manager-safe record with one normalised scope ID."""
    return {**asdict(relationship), "scope_id": relationship_scope_id(relationship)}


def establish_person_operating_relationship(
    conn, person_id: str, scope_type: str, scope_id: str, role: str, starts_on: str,
    manager_id: str, ends_on: Optional[str] = None, provenance: Optional[str] = None,
) -> PersonOperatingRelationship:
    """Append a manager-reviewed link; caller identity is never trusted here."""
    return repository.create_person_operating_relationship(
        conn,
        person_id=person_id,
        scope_type=scope_type,
        scope_id=scope_id,
        role=role,
        starts_on=starts_on,
        ends_on=ends_on,
        provenance=provenance,
        reviewed_by_person_id=manager_id,
    )


def relationship_detail(conn, relationship_id: str) -> dict:
    relationship = repository.get_person_operating_relationship(conn, relationship_id)
    if relationship is None:
        raise LookupError("person operating relationship not found")
    return {
        **relationship_summary(relationship),
        "audit_events": [
            asdict(event)
            for event in repository.list_audit_events(conn, "person_operating_relationship", relationship.id)
        ],
    }


def list_relationship_summaries(
    conn, person_id: Optional[str] = None, scope_type: Optional[str] = None,
    scope_id: Optional[str] = None, status: Optional[str] = None,
) -> List[dict]:
    return [
        relationship_summary(relationship)
        for relationship in repository.list_person_operating_relationships(
            conn, person_id=person_id, scope_type=scope_type, scope_id=scope_id, status=status
        )
    ]


def end_person_operating_relationship(
    conn, relationship_id: str, ends_on: str, manager_id: str, reason: str,
) -> PersonOperatingRelationship:
    """End the active link under the server-derived manager identity."""
    return repository.end_person_operating_relationship(
        conn, relationship_id, ends_on, manager_id, reason
    )
