"""Safe, manager-facing farm and farmer profile DTOs.

Canonical records are deliberately kept separate from TrackWick's reported
candidate context.  These helpers only return small whitelisted dictionaries:
they never expose provenance, contacts, coordinates, provider values, or an
authentication claim.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Mapping, Sequence

from ffl.services.trackwick_board import command_centre_board_for_source, source_relation_exists


_FIELD_RECORD_LIMITATION = "Latest activity reflects canonical non-draft field signals only."
_PROFILE_UPDATE_LIMIT = 30
_PROFILE_DIRECTORY_LIMIT = 100
_PROFILE_DATE_WINDOW_DAYS = 366
_NOT_ATTRIBUTED_CONTEXT = {
    "state": "not_attributed",
    "message": "Historical purchase cohorts are not attributed to this farm.",
}
_REPORTED_LIMITATION = "Reported source events remain reported until reviewed as Fortune truth."


def farm_record(
    conn, farm_id: str, date_from: str | None = None, date_to: str | None = None,
) -> dict[str, Any] | None:
    """Return one bounded Farm Record without joining raw source evidence."""
    bounds = _record_date_bounds(date_from, date_to)
    farm = conn.execute(
        """SELECT id, name FROM farms
           WHERE id = ? AND status = 'active'""",
        (farm_id,),
    ).fetchone()
    if farm is None:
        return None
    updates = _farm_updates(conn, farm["id"], bounds)
    return {
        "state": "reviewed",
        "kind": "farm",
        "id": farm["id"],
        "name": farm["name"],
        "now": _farm_now(conn, farm["id"], updates),
        "people": _farm_people(conn, farm["id"]),
        "updates": updates,
        "context": dict(_NOT_ATTRIBUTED_CONTEXT),
        "limitations": [_REPORTED_LIMITATION],
    }


def field_record(
    conn, block_id: str, date_from: str | None = None, date_to: str | None = None,
) -> dict[str, Any] | None:
    """Return reviewed Field context and safe, reviewed-linked activity."""
    bounds = _record_date_bounds(date_from, date_to)
    field = conn.execute(
        "SELECT id, name, area_hectares FROM operational_blocks WHERE id = ?",
        (block_id,),
    ).fetchone()
    if field is None:
        return None
    farm = conn.execute(
        """SELECT farms.id, farms.name
           FROM farm_fields
           JOIN farms ON farms.id = farm_fields.farm_id
           WHERE farm_fields.operational_block_id = ?
             AND farm_fields.status = 'active' AND farms.status = 'active'""",
        (block_id,),
    ).fetchone()
    farm_context = {"id": farm["id"], "name": farm["name"]} if farm is not None else None
    return {
        "state": "reviewed",
        "kind": "field",
        "id": field["id"],
        "name": field["name"],
        "area_hectares": field["area_hectares"],
        "farm": farm_context,
        "geometry": _published_geometry_state(conn, field["id"]),
        "allocations": _field_allocations(conn, field["id"]),
        "people": _field_people(conn, field["id"]),
        "updates": _updates_for_fields(
            conn, [field["id"]], farm["id"] if farm is not None else None, bounds,
        ),
        "limitations": [_REPORTED_LIMITATION],
    }


def person_context(
    conn, person_id: str, kind: str, date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any] | None:
    """Return active reviewed Farm/Field assignments for a farmer or worker."""
    _record_date_bounds(date_from, date_to)
    role = _person_kind_role(kind)
    person = conn.execute("SELECT id, name FROM people WHERE id = ?", (person_id,)).fetchone()
    if person is None:
        return None
    assignments = _person_assignments(conn, person["id"], role)
    if not assignments:
        return None
    return {
        "state": "reviewed",
        "kind": kind,
        "id": person["id"],
        "name": person["name"],
        "assignments": assignments,
        "context": {
            "state": "not_attributed",
            "message": "Historical purchase cohorts are not attributed to this person.",
        },
        "limitations": ["Only active reviewed operating relationships are shown."],
    }


def list_entity_directory(
    conn, kind: str, query: str | None = None, crop: str | None = None,
    date_from: str | None = None, date_to: str | None = None, limit: int = 50,
    state: str | None = None,
) -> list[dict[str, Any]]:
    """Return a small allowlisted directory for one canonical entity kind."""
    if kind not in {"farm", "field", "farmer", "field_worker"}:
        raise ValueError("kind must be farm, field, farmer, or field_worker")
    query = _directory_text(query, "query")
    crop = _directory_text(crop, "crop")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= _PROFILE_DIRECTORY_LIMIT:
        raise ValueError("limit must be between 1 and 100")
    bounds = _record_date_bounds(date_from, date_to)
    if state not in {None, "reviewed"}:
        if state == "reported" and kind == "farm":
            return _reported_farm_directory(conn, query, crop, bounds, limit)
        if state == "reported":
            return []
        raise ValueError("state must be reviewed or reported")

    if kind == "farm":
        predicates = ["farm.status = 'active'"]
        params: list[Any] = []
        if query is not None:
            predicates.append("lower(farm.name) LIKE ?")
            params.append("%" + query.lower() + "%")
        if crop is not None:
            predicates.append(
                """EXISTS (
                       SELECT 1 FROM farm_fields AS membership
                       JOIN crop_allocations AS allocation
                         ON allocation.operational_block_id = membership.operational_block_id
                       WHERE membership.farm_id = farm.id AND membership.status = 'active'
                         AND allocation.status = 'active'
                         AND lower(allocation.crop_name) LIKE ?
                   )"""
            )
            params.append("%" + crop.lower() + "%")
        params.append(limit)
        rows = conn.execute(
            """SELECT farm.id, farm.name FROM farms AS farm
               WHERE """ + " AND ".join(predicates) + " ORDER BY farm.name, farm.id LIMIT ?",
            tuple(params),
        ).fetchall()
        items = [_farm_directory_item(conn, row, bounds) for row in rows]
    elif kind == "field":
        predicates = ["farm_fields.status = 'active'", "farms.status = 'active'"]
        params = []
        if query is not None:
            predicates.append("lower(block.name) LIKE ?")
            params.append("%" + query.lower() + "%")
        if crop is not None:
            predicates.append(
                """EXISTS (
                       SELECT 1 FROM crop_allocations AS allocation
                       WHERE allocation.operational_block_id = block.id
                         AND allocation.status = 'active'
                         AND lower(allocation.crop_name) LIKE ?
                   )"""
            )
            params.append("%" + crop.lower() + "%")
        params.append(limit)
        rows = conn.execute(
            """SELECT block.id, block.name
               FROM operational_blocks AS block
               JOIN farm_fields ON farm_fields.operational_block_id = block.id
               JOIN farms ON farms.id = farm_fields.farm_id
               WHERE """ + " AND ".join(predicates) + " ORDER BY block.name, block.id LIMIT ?",
            tuple(params),
        ).fetchall()
        items = [_field_directory_item(conn, row, bounds) for row in rows]
    else:
        role = _person_kind_role(kind)
        predicates = [
            "relationship.role = ?", "relationship.status = 'active'",
            "relationship.reviewed_by_person_id IS NOT NULL",
        ]
        params = [role]
        if query is not None:
            predicates.append("lower(people.name) LIKE ?")
            params.append("%" + query.lower() + "%")
        if crop is not None:
            predicates.append(
                """EXISTS (
                       SELECT 1 FROM crop_allocations AS filter_allocation
                       WHERE filter_allocation.operational_block_id = block.id
                         AND filter_allocation.status = 'active'
                         AND lower(filter_allocation.crop_name) LIKE ?
                   )"""
            )
            params.append("%" + crop.lower() + "%")
        params.append(limit)
        rows = conn.execute(
            """SELECT DISTINCT people.id, people.name
               FROM people
               JOIN person_operating_relationships AS relationship
                 ON relationship.person_id = people.id
               JOIN operational_blocks AS block ON (
                    relationship.operational_block_id = block.id
                    OR relationship.crop_allocation_id IN (
                        SELECT id FROM crop_allocations WHERE operational_block_id = block.id
                    )
               )
               JOIN farm_fields
                 ON farm_fields.operational_block_id = block.id AND farm_fields.status = 'active'
               JOIN farms ON farms.id = farm_fields.farm_id AND farms.status = 'active'
               WHERE """ + " AND ".join(predicates) + " ORDER BY people.name, people.id LIMIT ?",
            tuple(params),
        ).fetchall()
        items = [
            {
                "state": "reviewed", "kind": kind, "id": row["id"], "name": row["name"],
                "assignment_count": len(_person_assignments(conn, row["id"], role)),
            }
            for row in rows
        ]
        items = [item for item in items if item["assignment_count"]]

    return items


def _record_date_bounds(
    date_from: str | None, date_to: str | None,
) -> tuple[date | None, date | None]:
    start = _profile_date(date_from, "date_from")
    end = _profile_date(date_to, "date_to")
    if start is not None and end is not None:
        if start > end:
            raise ValueError("date_from must be on or before date_to")
        if (end - start).days > _PROFILE_DATE_WINDOW_DAYS:
            raise ValueError("date window must not exceed 366 days")
    return start, end


def _profile_date(value: str | None, name: str) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("{0} must be an ISO date".format(name))
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("{0} must be an ISO date".format(name)) from error
    if value != parsed.isoformat():
        raise ValueError("{0} must be an ISO date".format(name))
    return parsed


def _directory_text(value: str | None, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 80:
        raise ValueError("{0} must be at most 80 characters".format(name))
    normalized = value.strip()
    return normalized or None


def _farm_now(
    conn, farm_id: str, updates: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    fields = conn.execute(
        """SELECT block.id, block.name
           FROM farm_fields
           JOIN operational_blocks AS block ON block.id = farm_fields.operational_block_id
           WHERE farm_fields.farm_id = ? AND farm_fields.status = 'active'
           ORDER BY block.name, block.id""",
        (farm_id,),
    ).fetchall()
    allocations = conn.execute(
        """SELECT allocation.id, allocation.crop_name, allocation.cultivar,
                  season.id AS season_id, season.name AS season_name
           FROM farm_fields
           JOIN crop_allocations AS allocation
             ON allocation.operational_block_id = farm_fields.operational_block_id
           JOIN seasons AS season ON season.id = allocation.season_id
           WHERE farm_fields.farm_id = ? AND farm_fields.status = 'active'
             AND allocation.status = 'active'
           ORDER BY season.starts_on DESC, allocation.created_at DESC, allocation.id""",
        (farm_id,),
    ).fetchall()
    open_work = conn.execute(
        """SELECT count(work.id) AS count
           FROM farm_fields
           JOIN crop_allocations AS allocation
             ON allocation.operational_block_id = farm_fields.operational_block_id
           JOIN work_items AS work ON work.allocation_id = allocation.id
           WHERE farm_fields.farm_id = ? AND farm_fields.status = 'active'
             AND work.status IN ('planned', 'in_progress', 'blocked', 'submitted', 'rejected')""",
        (farm_id,),
    ).fetchone()
    return {
        "fields": [{"id": row["id"], "name": row["name"]} for row in fields],
        "active_allocations": [
            {
                "id": row["id"], "crop_name": row["crop_name"], "cultivar": row["cultivar"],
                "season_id": row["season_id"], "season_name": row["season_name"],
            }
            for row in allocations
        ],
        "open_work_count": open_work["count"],
        "latest_update_at": updates[0]["occurred_at"] if updates else None,
    }


def _farm_people(conn, farm_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT person.id, person.name, relationship.role, relationship.starts_on,
                  block.id AS field_id, block.name AS field_name
           FROM farm_fields
           JOIN operational_blocks AS block ON block.id = farm_fields.operational_block_id
           JOIN person_operating_relationships AS relationship
             ON relationship.status = 'active'
            AND relationship.reviewed_by_person_id IS NOT NULL
            AND relationship.role IN ('grower', 'field_operator')
            AND (
                relationship.operational_block_id = block.id
                OR relationship.crop_allocation_id IN (
                    SELECT id FROM crop_allocations WHERE operational_block_id = block.id
                )
            )
           JOIN people AS person ON person.id = relationship.person_id
           WHERE farm_fields.farm_id = ? AND farm_fields.status = 'active'
           ORDER BY person.name, relationship.role, relationship.starts_on, block.name,
                    relationship.id, block.id""",
        (farm_id,),
    ).fetchall()
    return _deduplicated_people(rows)


def _field_people(conn, block_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT person.id, person.name, relationship.role, relationship.starts_on,
                  block.id AS field_id, block.name AS field_name
           FROM operational_blocks AS block
           JOIN person_operating_relationships AS relationship
             ON relationship.status = 'active'
            AND relationship.reviewed_by_person_id IS NOT NULL
            AND relationship.role IN ('grower', 'field_operator')
            AND (
                relationship.operational_block_id = block.id
                OR relationship.crop_allocation_id IN (
                    SELECT id FROM crop_allocations WHERE operational_block_id = block.id
                )
            )
           JOIN people AS person ON person.id = relationship.person_id
           WHERE block.id = ?
           ORDER BY person.name, relationship.role, relationship.starts_on, relationship.id""",
        (block_id,),
    ).fetchall()
    return _deduplicated_people(rows)


def _deduplicated_people(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    people: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row["id"], row["role"], row["field_id"])
        people.setdefault(key, {
            "id": row["id"],
            "name": row["name"],
            "kind": "farmer" if row["role"] == "grower" else "field_worker",
            "role": row["role"],
            "starts_on": row["starts_on"],
            "field_id": row["field_id"],
            "field_name": row["field_name"],
        })
    return list(people.values())


def _field_allocations(conn, block_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT allocation.id, allocation.season_id, season.name AS season_name,
                  allocation.crop_name, allocation.cultivar, allocation.area_hectares,
                  allocation.status, season.starts_on, season.ends_on
           FROM crop_allocations AS allocation
           JOIN seasons AS season ON season.id = allocation.season_id
           WHERE allocation.operational_block_id = ?
           ORDER BY season.starts_on DESC, allocation.created_at DESC, allocation.id""",
        (block_id,),
    ).fetchall()
    return [
        {
            "id": row["id"], "season_id": row["season_id"], "season_name": row["season_name"],
            "crop_name": row["crop_name"], "cultivar": row["cultivar"],
            "area_hectares": row["area_hectares"], "status": row["status"],
            "starts_on": row["starts_on"], "ends_on": row["ends_on"],
        }
        for row in rows
    ]


def _person_kind_role(kind: str) -> str:
    if kind == "farmer":
        return "grower"
    if kind == "field_worker":
        return "field_operator"
    raise ValueError("kind must be farmer or field_worker")


def _person_assignments(conn, person_id: str, role: str) -> list[dict[str, str]]:
    rows = conn.execute(
        """SELECT farm.id AS farm_id, farm.name AS farm_name,
                  block.id AS field_id, block.name AS field_name,
                  relationship.role, relationship.starts_on
           FROM person_operating_relationships AS relationship
           JOIN operational_blocks AS block ON (
                relationship.operational_block_id = block.id
                OR relationship.crop_allocation_id IN (
                    SELECT id FROM crop_allocations WHERE operational_block_id = block.id
                )
           )
           JOIN farm_fields
             ON farm_fields.operational_block_id = block.id AND farm_fields.status = 'active'
           JOIN farms AS farm ON farm.id = farm_fields.farm_id AND farm.status = 'active'
           WHERE relationship.person_id = ? AND relationship.role = ?
             AND relationship.status = 'active'
             AND relationship.reviewed_by_person_id IS NOT NULL
           ORDER BY farm.name, block.name, relationship.starts_on, relationship.id""",
        (person_id, role),
    ).fetchall()
    assignments: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in rows:
        key = (row["farm_id"], row["field_id"], row["role"])
        assignments.setdefault(key, {
            "farm_id": row["farm_id"], "farm_name": row["farm_name"],
            "field_id": row["field_id"], "field_name": row["field_name"],
            "role": row["role"], "starts_on": row["starts_on"],
        })
    return list(assignments.values())


def _farm_updates(
    conn, farm_id: str, bounds: tuple[date | None, date | None],
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT operational_block_id
           FROM farm_fields WHERE farm_id = ? AND status = 'active'
           ORDER BY operational_block_id""",
        (farm_id,),
    ).fetchall()
    return _updates_for_fields(conn, [row["operational_block_id"] for row in rows], farm_id, bounds)


def _updates_for_fields(
    conn, block_ids: Sequence[str], farm_id: str | None,
    bounds: tuple[date | None, date | None],
) -> list[dict[str, Any]]:
    if not block_ids:
        return []
    placeholders = ", ".join("?" for _ in block_ids)
    updates: list[dict[str, Any]] = []
    signal_rows = conn.execute(
        """SELECT signal.id, signal.observed_at, signal.status,
                  template.name AS template_name, person.name AS actor_name,
                  block.id AS field_id, block.name AS field_name
           FROM field_signals AS signal
           JOIN signal_templates AS template ON template.id = signal.template_id
           JOIN people AS person ON person.id = signal.actor_id
           JOIN crop_allocations AS allocation ON allocation.id = signal.allocation_id
           JOIN operational_blocks AS block ON block.id = allocation.operational_block_id
           WHERE signal.status != 'draft' AND block.id IN (""" + placeholders + ")",
        tuple(block_ids),
    ).fetchall()
    for row in signal_rows:
        updates.append({
            "id": row["id"], "occurred_at": row["observed_at"], "kind": "field_signal",
            "state": "reviewed", "farm_id": farm_id, "field_id": row["field_id"],
            "field_name": row["field_name"], "summary": row["template_name"],
            "status": row["status"], "actor": row["actor_name"],
            "action": {"kind": "open_field", "id": row["field_id"]},
        })
    work_rows = conn.execute(
        """SELECT work.id, work.created_at, work.title, work.status,
                  person.name AS actor_name, block.id AS field_id, block.name AS field_name
           FROM work_items AS work
           JOIN people AS person ON person.id = work.owner_id
           JOIN crop_allocations AS allocation ON allocation.id = work.allocation_id
           JOIN operational_blocks AS block ON block.id = allocation.operational_block_id
           WHERE block.id IN (""" + placeholders + ")",
        tuple(block_ids),
    ).fetchall()
    for row in work_rows:
        updates.append({
            "id": row["id"], "occurred_at": row["created_at"], "kind": "work_item",
            "state": "reviewed", "farm_id": farm_id, "field_id": row["field_id"],
            "field_name": row["field_name"], "summary": row["title"],
            "status": row["status"], "actor": row["actor_name"],
            "action": {"kind": "open_action", "id": row["id"]},
        })
    updates.extend(_reported_updates_for_fields(conn, block_ids, farm_id))
    filtered = [item for item in updates if _update_within_bounds(item["occurred_at"], bounds)]
    return sorted(
        filtered,
        key=lambda item: (_timestamp_instant(item["occurred_at"]), item["kind"], item["id"]),
        reverse=True,
    )[:_PROFILE_UPDATE_LIMIT]


def _reported_updates_for_fields(
    conn, block_ids: Sequence[str], farm_id: str | None,
) -> list[dict[str, Any]]:
    placeholders = ", ".join("?" for _ in block_ids)
    linked_tasks = """SELECT DISTINCT link.task_id, allocation.operational_block_id
                      FROM trackwick_task_allocation_links AS link
                      JOIN crop_allocations AS allocation ON allocation.id = link.crop_allocation_id
                      WHERE link.link_status = 'reviewed'
                        AND link.reviewed_by_person_id IS NOT NULL
                        AND allocation.operational_block_id IN (""" + placeholders + ")"
    if source_relation_exists(conn, "trackwick_tasks"):
        task_rows = conn.execute(
            """WITH linked AS (""" + linked_tasks + """)
               SELECT task.id,
                      COALESCE(task.provider_completed_at, task.provider_started_at,
                               task.provider_created_at, task.created_at) AS occurred_at,
                      block.id AS field_id, block.name AS field_name
               FROM linked
               JOIN trackwick_tasks AS task ON task.id = linked.task_id
               JOIN operational_blocks AS block ON block.id = linked.operational_block_id
               WHERE task.data_quality_status = 'valid'""",
            tuple(block_ids),
        ).fetchall()
    else:
        task_rows = conn.execute(
            """WITH linked AS (""" + linked_tasks + """),
               task_times AS (
                   SELECT visit.task_id, visit.observed_at
                   FROM trackwick_visits AS visit
                   WHERE visit.data_quality_status = 'valid'
                   UNION ALL
                   SELECT finding.visit_task_id, finding.observed_at
                   FROM trackwick_visit_findings AS finding
                   WHERE finding.data_quality_status = 'valid'
               )
               SELECT linked.task_id AS id, max(task_times.observed_at) AS occurred_at,
                      block.id AS field_id, block.name AS field_name
               FROM linked
               JOIN task_times ON task_times.task_id = linked.task_id
               JOIN operational_blocks AS block ON block.id = linked.operational_block_id
               GROUP BY linked.task_id, block.id, block.name""",
            tuple(block_ids),
        ).fetchall()
    updates = [
        {
            "id": row["id"], "occurred_at": row["occurred_at"], "kind": "trackwick_task",
            "state": "reported", "farm_id": farm_id, "field_id": row["field_id"],
            "field_name": row["field_name"],
            "summary": "TrackWick task reported",
            "actor": None, "action": {"kind": "review_in_farm_truth", "id": row["id"]},
        }
        for row in task_rows
    ]
    visit_rows = conn.execute(
        """WITH linked AS (""" + linked_tasks + """)
           SELECT visit.task_id, visit.observed_at,
                  block.id AS field_id, block.name AS field_name
           FROM linked
           JOIN trackwick_visits AS visit ON visit.task_id = linked.task_id
           JOIN operational_blocks AS block ON block.id = linked.operational_block_id
           WHERE visit.data_quality_status = 'valid'""",
        tuple(block_ids),
    ).fetchall()
    updates.extend({
        "id": "visit-" + row["task_id"], "occurred_at": row["observed_at"],
        "kind": "trackwick_visit", "state": "reported", "farm_id": farm_id,
        "field_id": row["field_id"], "field_name": row["field_name"],
        "summary": "Field visit reported", "actor": None,
        "action": {"kind": "review_in_farm_truth", "id": row["task_id"]},
    } for row in visit_rows)
    finding_rows = conn.execute(
        """WITH linked AS (""" + linked_tasks + """)
           SELECT finding.id, finding.visit_task_id, finding.finding_kind,
                  finding.declared_severity, finding.observed_at,
                  block.id AS field_id, block.name AS field_name
           FROM linked
           JOIN trackwick_visit_findings AS finding
             ON finding.visit_task_id = linked.task_id
           JOIN operational_blocks AS block ON block.id = linked.operational_block_id
           WHERE finding.data_quality_status = 'valid'""",
        tuple(block_ids),
    ).fetchall()
    for row in finding_rows:
        updates.append({
            "id": row["id"], "occurred_at": row["observed_at"],
            "kind": row["finding_kind"] + "_finding", "state": "reported",
            "farm_id": farm_id, "field_id": row["field_id"], "field_name": row["field_name"],
            "summary": "{0} {1} finding reported".format(
                row["declared_severity"].capitalize(), row["finding_kind"],
            ),
            "finding_kind": row["finding_kind"],
            "declared_severity": row["declared_severity"],
            "actor": None,
            "action": {"kind": "review_in_farm_truth", "id": row["visit_task_id"]},
        })
    return updates


def _update_within_bounds(
    occurred_at: str, bounds: tuple[date | None, date | None],
) -> bool:
    instant_date = _timestamp_instant(occurred_at).date()
    start, end = bounds
    return (start is None or instant_date >= start) and (end is None or instant_date <= end)


def _farm_directory_item(
    conn, farm: Mapping[str, Any], bounds: tuple[date | None, date | None],
) -> dict[str, Any]:
    updates = _farm_updates(conn, farm["id"], bounds)
    now = _farm_now(conn, farm["id"], updates)
    return {
        "state": "reviewed", "kind": "farm", "id": farm["id"], "name": farm["name"],
        "field_count": len(now["fields"]),
        "crops": sorted({row["crop_name"] for row in now["active_allocations"]}),
        "open_work_count": now["open_work_count"], "latest_update_at": now["latest_update_at"],
    }


def _reported_farm_directory(
    conn, query: str | None, crop: str | None,
    bounds: tuple[date | None, date | None], limit: int,
) -> list[dict[str, Any]]:
    """Adapt source registrations into a distinct, non-canonical directory."""
    if crop is not None:
        # A registration does not establish a reviewed crop allocation.
        return []
    rows = command_centre_board_for_source(conn)["farms"]
    items: list[dict[str, Any]] = []
    for row in rows:
        haystack = " ".join((str(row.get("farmer_name") or ""), str(row.get("place") or ""))).lower()
        if query is not None and query.lower() not in haystack:
            continue
        occurred_at = row.get("latest_activity_at")
        if occurred_at is not None and not _update_within_bounds(occurred_at, bounds):
            continue
        if occurred_at is None and any(bounds):
            continue
        items.append({
            "state": "reported",
            "kind": "reported_farm_candidate",
            "id": row["id"],
            "name": row["place"],
            "reported_farmer_name": row["farmer_name"],
            "reported_area_acres": row["reported_area_acres"],
            "reported_plot_count": row["reported_plot_count"],
            "open_work_count": row["open_work"],
            "latest_update_at": occurred_at,
            "destination": {"kind": "review_reported_farm", "id": row["id"]},
        })
        if len(items) >= limit:
            break
    return items


def _field_directory_item(
    conn, field: Mapping[str, Any], bounds: tuple[date | None, date | None],
) -> dict[str, Any]:
    record = field_record(
        conn, field["id"],
        bounds[0].isoformat() if bounds[0] else None,
        bounds[1].isoformat() if bounds[1] else None,
    )
    assert record is not None
    return {
        "state": "reviewed", "kind": "field", "id": field["id"], "name": field["name"],
        "farm": record["farm"],
        "crops": sorted({row["crop_name"] for row in record["allocations"] if row["status"] == "active"}),
        "latest_update_at": record["updates"][0]["occurred_at"] if record["updates"] else None,
    }


def farm_profile(conn, block_id: str) -> dict[str, Any] | None:
    """Return reviewed operational context for one canonical farm block."""
    block = conn.execute(
        "SELECT id, name, area_hectares, operating_unit_id FROM operational_blocks WHERE id = ?", (block_id,)
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
        "people": _reviewed_people_for_block(conn, block["id"], block["operating_unit_id"], allocations),
        "work": _reviewed_work_for_allocations(conn, [row["id"] for row in allocations]),
        "open_work_count": _open_work_count_for_allocations(conn, [row["id"] for row in allocations]),
        "location": _published_geometry_state(conn, block["id"]),
        "record": _reviewed_field_record(conn, block["id"]),
    }


def farmer_profile(conn, person_id: str) -> dict[str, Any] | None:
    """Return the canonical, reviewed relationships for one person."""
    person = conn.execute(
        "SELECT id, name FROM people WHERE id = ?", (person_id,)
    ).fetchone()
    if person is None or not _has_reviewed_grower_relationship(conn, person_id):
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
        (item for item in command_centre_board_for_source(conn)["farms"] if item["id"] == candidate_id),
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
        (item for item in command_centre_board_for_source(conn)["farmers"] if item["id"] == party_id),
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
    conn, block_id: str, operating_unit_id: str, allocations: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    allocation_ids = [row["id"] for row in allocations]
    allocation_predicate = "0 = 1"
    params: list[Any] = [block_id, block_id, operating_unit_id]
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
             AND relationship.role IN ('grower', 'field_operator')
             AND (
                 relationship.operational_block_id = ?
                 OR relationship.land_parcel_id IN (
                     SELECT land_parcel_id FROM block_parcels
                     WHERE operational_block_id = ?
                 )
                 OR relationship.operating_unit_id = ?
                 OR """ + allocation_predicate + """
             )
           ORDER BY relationship.starts_on, person.name, relationship.role, relationship.id""",
        tuple(params),
    ).fetchall()
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        unique.setdefault((row["id"], row["role"]), {
            "id": row["id"],
            "name": row["name"],
            "role": row["role"],
            "starts_on": row["starts_on"],
        })
    return list(unique.values())


def _reviewed_work_for_allocations(conn, allocation_ids: Sequence[str]) -> list[dict[str, Any]]:
    if not allocation_ids:
        return []
    placeholders = ", ".join("?" for _ in allocation_ids)
    rows = conn.execute(
        """SELECT id, title, status
           FROM work_items
           WHERE allocation_id IN (""" + placeholders + """)
             AND status IN ('planned', 'in_progress', 'blocked', 'submitted', 'rejected')
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
             AND relationship.role = 'grower'
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
                 AND role = 'grower'
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


def _has_reviewed_grower_relationship(conn, person_id: str) -> bool:
    return conn.execute(
        """SELECT 1 FROM person_operating_relationships
           WHERE person_id = ? AND status = 'active' AND reviewed_by_person_id IS NOT NULL
             AND role = 'grower' LIMIT 1""", (person_id,),
    ).fetchone() is not None


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
            "reported_area_acres",
            "reported_plot_count",
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
