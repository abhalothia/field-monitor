"""Fail-closed, read-only coverage of a person over a crop allocation.

This service resolves an allocation's explicit operating hierarchy and asks
only whether a person has a current, scoped relationship which covers it.  It
does not infer coverage from a person's generic role, a village, a purchase
record, or a name match.  It is deliberately transport-agnostic so a future
communications or field-capture workflow can use the same narrow gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional, Tuple, Union


@dataclass(frozen=True)
class MatchingOperatingScope:
    """The minimal relationship fact that covers the requested allocation."""

    scope_type: str
    scope_id: str
    role: str


@dataclass(frozen=True)
class AllocationRelationshipCoverage:
    """Safe result for an internal eligibility decision.

    ``eligible`` is true only when at least one active, effective relationship
    covers an active allocation.  Context is intentionally allocation-level:
    it never includes the person's name, contact details, provenance, or a
    relationship/audit record identifier.
    """

    eligible: bool
    allocation_id: Optional[str]
    allocation_name: Optional[str]
    block_id: Optional[str]
    block_name: Optional[str]
    operating_unit_id: Optional[str]
    operating_unit_name: Optional[str]
    matching_scopes: Tuple[MatchingOperatingScope, ...]


_NO_COVERAGE = AllocationRelationshipCoverage(
    eligible=False,
    allocation_id=None,
    allocation_name=None,
    block_id=None,
    block_name=None,
    operating_unit_id=None,
    operating_unit_name=None,
    matching_scopes=(),
)


def active_person_allocation_coverage(
    conn,
    person_id: str,
    allocation_id: str,
    *,
    on_date: Optional[Union[date, str]] = None,
) -> AllocationRelationshipCoverage:
    """Return whether ``person_id`` currently covers an active allocation.

    Coverage can be direct to the allocation, or inherited only through the
    allocation's explicit operational block, a parcel explicitly linked to
    that block, or its operating unit.  The date is injectable for deterministic
    callers and tests; omitted means the server's current UTC calendar date.

    The result fails closed for an unknown allocation, absent relationships,
    an unconfigured relationship migration, malformed input, or database
    failure.  This is intentionally a read-only safety boundary, not a people
    directory or authorization system.
    """
    normalized_person_id = _identifier(person_id)
    normalized_allocation_id = _identifier(allocation_id)
    effective_on = _effective_date(on_date)
    if normalized_person_id is None or normalized_allocation_id is None or effective_on is None:
        return _NO_COVERAGE

    try:
        allocation = conn.execute(
            """SELECT
                   allocation.id AS allocation_id,
                   allocation.crop_name AS crop_name,
                   allocation.cultivar AS cultivar,
                   season.name AS season_name,
                   block.id AS block_id,
                   block.name AS block_name,
                   unit.id AS operating_unit_id,
                   unit.name AS operating_unit_name
               FROM crop_allocations AS allocation
               JOIN operational_blocks AS block ON block.id = allocation.operational_block_id
               JOIN operating_units AS unit ON unit.id = allocation.operating_unit_id
               JOIN seasons AS season ON season.id = allocation.season_id
               WHERE allocation.id = ?
                 AND allocation.status = 'active'
                 AND block.operating_unit_id = allocation.operating_unit_id
                 AND season.operating_unit_id = allocation.operating_unit_id""",
            (normalized_allocation_id,),
        ).fetchone()
        if allocation is None:
            return _NO_COVERAGE

        parcel_rows = conn.execute(
            """SELECT parcel.id AS parcel_id
               FROM block_parcels AS linked
               JOIN land_parcels AS parcel ON parcel.id = linked.land_parcel_id
               WHERE linked.operational_block_id = ?
                 AND parcel.operating_unit_id = ?""",
            (allocation["block_id"], allocation["operating_unit_id"]),
        ).fetchall()
        parcel_ids = tuple(row["parcel_id"] for row in parcel_rows)

        scope_clause = """(
               (scope_type = 'crop_allocation' AND crop_allocation_id = ?)
            OR (scope_type = 'operational_block' AND operational_block_id = ?)
            OR (scope_type = 'operating_unit' AND operating_unit_id = ?)
        )"""
        scope_params = [
            allocation["allocation_id"],
            allocation["block_id"],
            allocation["operating_unit_id"],
        ]
        if parcel_ids:
            placeholders = ", ".join("?" for _ in parcel_ids)
            scope_clause = "({0} OR (scope_type = 'land_parcel' AND land_parcel_id IN ({1})))".format(
                scope_clause, placeholders
            )
            scope_params.extend(parcel_ids)

        relationship_rows = conn.execute(
            """SELECT scope_type, operating_unit_id, land_parcel_id, operational_block_id,
                      crop_allocation_id, role
               FROM person_operating_relationships
               WHERE person_id = ?
                 AND status = 'active'
                 AND starts_on <= ?
                 AND (ends_on IS NULL OR ends_on >= ?)
                 AND {0}
               ORDER BY CASE scope_type
                   WHEN 'crop_allocation' THEN 1
                   WHEN 'operational_block' THEN 2
                   WHEN 'land_parcel' THEN 3
                   WHEN 'operating_unit' THEN 4
                   ELSE 5
               END, role""".format(scope_clause),
            tuple([normalized_person_id, effective_on, effective_on] + scope_params),
        ).fetchall()
    except Exception:
        # This includes a missing relationship table before its migration has
        # landed.  Any inability to prove a scoped relationship must deny the
        # downstream action rather than silently broadening eligibility.
        return _NO_COVERAGE

    matching_scopes = tuple(
        MatchingOperatingScope(
            scope_type=row["scope_type"],
            scope_id=_scope_id_from_row(row),
            role=row["role"],
        )
        for row in relationship_rows
    )
    allocation_name = _allocation_name(
        crop_name=allocation["crop_name"],
        cultivar=allocation["cultivar"],
        season_name=allocation["season_name"],
    )
    return AllocationRelationshipCoverage(
        eligible=bool(matching_scopes),
        allocation_id=allocation["allocation_id"],
        allocation_name=allocation_name,
        block_id=allocation["block_id"],
        block_name=allocation["block_name"],
        operating_unit_id=allocation["operating_unit_id"],
        operating_unit_name=allocation["operating_unit_name"],
        matching_scopes=matching_scopes,
    )


def _identifier(value: object) -> Optional[str]:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized if normalized and len(normalized) <= 128 else None


def _effective_date(value: Optional[Union[date, str]]) -> Optional[str]:
    if value is None:
        return date.today().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError:
            return None
    return None


def _scope_id_from_row(row) -> str:
    values = {
        "operating_unit": row["operating_unit_id"],
        "land_parcel": row["land_parcel_id"],
        "operational_block": row["operational_block_id"],
        "crop_allocation": row["crop_allocation_id"],
    }
    # The relationship table CHECK makes this unreachable for valid rows.  A
    # bad legacy row is not allowed to grant access, so returning an empty ID
    # leaves the caller with a non-useful match rather than guessing a scope.
    return values.get(row["scope_type"]) or ""


def _allocation_name(*, crop_name: str, cultivar: Optional[str], season_name: str) -> str:
    crop_label = crop_name if not cultivar else "{0} · {1}".format(crop_name, cultivar)
    return "{0} · {1}".format(crop_label, season_name)
