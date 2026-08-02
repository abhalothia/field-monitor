"""Validate and atomically accept the first Uttar Pradesh farm pack.

The route using this service is deliberately a rehearsal.  It gives a manager
one precise place to check the real farm's facts before a separately authorised
acceptance writes the operating record.  Validation never creates people,
rights, land, work, or a location by implication.  Acceptance is a single,
idempotent transaction guarded by a durable singleton record, so an HTTP retry
or a competing request cannot create a second "first farm".
"""

from datetime import date, datetime, timezone
import hashlib
import json
import math
import re
import sqlite3
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence
import uuid


_PINCODE = re.compile(r"[0-9]{6}")
_UP_CONTEXT_KEY = re.compile(r"up:[a-z0-9][a-z0-9-]{1,118}")
_UP_ALIASES = {"up", "u.p", "u.p.", "uttar pradesh"}
_ROLES = {"farm_manager", "operations_lead", "agronomist", "field_operator"}
_IDEMPOTENCY_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}")


class PilotSetupValidationError(ValueError):
    """An input gap that a manager can correct before accepting a setup."""


def _text(value: Any, label: str, maximum: int = 200) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise PilotSetupValidationError("{0} must be non-empty text up to {1} characters".format(label, maximum))
    return value.strip()


def _finite_area(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise PilotSetupValidationError("{0} must be a finite positive number".format(label))
    area = float(value)
    if area <= 0:
        raise PilotSetupValidationError("{0} must be a finite positive number".format(label))
    return area


def _iso_date(value: Any, label: str) -> str:
    parsed = _text(value, label, 32)
    try:
        date.fromisoformat(parsed)
    except ValueError as error:
        raise PilotSetupValidationError("{0} must be an ISO-8601 date".format(label)) from error
    return parsed


def _iso_timestamp(value: Any, label: str) -> str:
    parsed = _text(value, label, 64)
    try:
        timestamp = datetime.fromisoformat(parsed.replace("Z", "+00:00"))
    except ValueError as error:
        raise PilotSetupValidationError("{0} must be an ISO-8601 timestamp".format(label)) from error
    if timestamp.tzinfo is None:
        raise PilotSetupValidationError("{0} must include a timezone".format(label))
    return timestamp.astimezone(timezone.utc).isoformat()


def _items(value: Any, label: str) -> List[Mapping[str, Any]]:
    if not isinstance(value, list) or not value:
        raise PilotSetupValidationError("{0} must contain at least one item".format(label))
    if len(value) > 200:
        raise PilotSetupValidationError("{0} may contain at most 200 items".format(label))
    if not all(isinstance(item, Mapping) for item in value):
        raise PilotSetupValidationError("{0} entries must be objects".format(label))
    return list(value)


def _unique_references(items: Iterable[Mapping[str, Any]], label: str) -> Dict[str, Mapping[str, Any]]:
    result: Dict[str, Mapping[str, Any]] = {}
    for item in items:
        reference = _text(item.get("reference"), label + " reference", 80)
        if reference in result:
            raise PilotSetupValidationError("{0} references must be unique".format(label))
        result[reference] = item
    return result


def _normalise_up_state(value: Any) -> str:
    supplied = _text(value, "location.state_name", 80)
    compact = " ".join(supplied.lower().replace("-", " ").split())
    if compact not in _UP_ALIASES:
        raise PilotSetupValidationError("this pilot setup currently accepts Uttar Pradesh only")
    return "Uttar Pradesh"


def _normalise_people(value: Any) -> List[Dict[str, str]]:
    people = _unique_references(_items(value, "people"), "person")
    result: List[Dict[str, str]] = []
    roles = set()
    for reference, item in people.items():
        role = _text(item.get("role"), "person.role", 80)
        if role not in _ROLES:
            raise PilotSetupValidationError("person.role must be one of {0}".format(", ".join(sorted(_ROLES))))
        roles.add(role)
        result.append({"reference": reference, "name": _text(item.get("name"), "person.name"), "role": role})
    if not roles.intersection({"farm_manager", "operations_lead"}):
        raise PilotSetupValidationError("people must include a farm_manager or operations_lead")
    if "field_operator" not in roles:
        raise PilotSetupValidationError("people must include a field_operator")
    return result


def _normalise_parcels(value: Any, season_start: str, season_end: str) -> Dict[str, Dict[str, Any]]:
    parcels = _unique_references(_items(value, "parcels"), "parcel")
    result: Dict[str, Dict[str, Any]] = {}
    for reference, item in parcels.items():
        right_start = _iso_date(item.get("right_starts_on"), "parcel.right_starts_on")
        right_end = _iso_date(item.get("right_ends_on"), "parcel.right_ends_on")
        if right_end < right_start:
            raise PilotSetupValidationError("parcel.right_ends_on must not precede parcel.right_starts_on")
        if right_start > season_start or right_end < season_end:
            raise PilotSetupValidationError("each parcel right must cover the proposed active season")
        result[reference] = {
            "reference": reference,
            "name": _text(item.get("name"), "parcel.name"),
            "area_hectares": _finite_area(item.get("area_hectares"), "parcel.area_hectares"),
            "right_type": _text(item.get("right_type"), "parcel.right_type", 80),
            "right_starts_on": right_start,
            "right_ends_on": right_end,
        }
    return result


def _normalise_blocks(value: Any, parcels: Mapping[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    blocks = _unique_references(_items(value, "blocks"), "block")
    result: Dict[str, Dict[str, Any]] = {}
    for reference, item in blocks.items():
        parcel_references = item.get("parcel_references")
        if not isinstance(parcel_references, list) or not parcel_references:
            raise PilotSetupValidationError("block.parcel_references must contain at least one parcel reference")
        if len(parcel_references) != len(set(parcel_references)):
            raise PilotSetupValidationError("block.parcel_references must not repeat a parcel")
        if not all(isinstance(parcel_reference, str) and parcel_reference in parcels for parcel_reference in parcel_references):
            raise PilotSetupValidationError("each block parcel reference must identify a proposed parcel")
        area = _finite_area(item.get("area_hectares"), "block.area_hectares")
        parcel_capacity = sum(parcels[parcel_reference]["area_hectares"] for parcel_reference in parcel_references)
        if area > parcel_capacity:
            raise PilotSetupValidationError("block.area_hectares cannot exceed its linked parcel area")
        result[reference] = {
            "reference": reference,
            "name": _text(item.get("name"), "block.name"),
            "area_hectares": area,
            "parcel_references": list(parcel_references),
        }
    return result


def _normalise_allocations(value: Any, blocks: Mapping[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    allocations = _unique_references(_items(value, "allocations"), "allocation")
    totals: Dict[str, float] = {reference: 0.0 for reference in blocks}
    result: List[Dict[str, Any]] = []
    for reference, item in allocations.items():
        block_reference = _text(item.get("block_reference"), "allocation.block_reference", 80)
        if block_reference not in blocks:
            raise PilotSetupValidationError("allocation.block_reference must identify a proposed block")
        area = _finite_area(item.get("area_hectares"), "allocation.area_hectares")
        totals[block_reference] += area
        result.append({
            "reference": reference,
            "block_reference": block_reference,
            "crop_name": _text(item.get("crop_name"), "allocation.crop_name"),
            "cultivar": _text(item.get("cultivar"), "allocation.cultivar", 120) if item.get("cultivar") else None,
            "area_hectares": area,
        })
    for block_reference, total in totals.items():
        if total > blocks[block_reference]["area_hectares"]:
            raise PilotSetupValidationError("proposed allocations exceed the area of block {0}".format(block_reference))
    return result


def _normalise_location(value: Any) -> Dict[str, Optional[str]]:
    if not isinstance(value, Mapping):
        raise PilotSetupValidationError("location must be an object")
    key = _text(value.get("district_context_key"), "location.district_context_key", 120).lower()
    if _UP_CONTEXT_KEY.fullmatch(key) is None:
        raise PilotSetupValidationError("location.district_context_key must use the stable form up:<district-slug>")
    pincode = value.get("pincode")
    if pincode is not None and (not isinstance(pincode, str) or _PINCODE.fullmatch(pincode) is None):
        raise PilotSetupValidationError("location.pincode must be a six-digit Indian PIN when supplied")
    return {
        "state_name": _normalise_up_state(value.get("state_name")),
        "district_name": _text(value.get("district_name"), "location.district_name"),
        "district_context_key": key,
        "subdistrict_name": _text(value.get("subdistrict_name"), "location.subdistrict_name") if value.get("subdistrict_name") else None,
        "village_name": _text(value.get("village_name"), "location.village_name") if value.get("village_name") else None,
        "pincode": pincode,
        "verification_method": "field_verified",
        # Field observation time is retained separately from the later
        # acceptance timestamp.  A manager's click must never rewrite when a
        # location was actually verified.
        "verified_at": _iso_timestamp(value.get("verified_at"), "location.verified_at"),
    }


def validate_quick_start(value: Any) -> Dict[str, Any]:
    """Check the six facts needed to begin a first-field conversation.

    This intentionally is not a shortcut around canonical first-farm
    acceptance. It writes nothing and does not invent rights, dates, field
    boundaries, owners, or work. It gives a non-technical operator a small,
    honest first step before a manager supplies the remaining governed facts.
    """
    if not isinstance(value, Mapping):
        raise PilotSetupValidationError("quick start must be an object")
    pincode = value.get("pincode")
    village = _text(value.get("village_name"), "village_name") if value.get("village_name") else None
    if pincode is not None and pincode != "" and (not isinstance(pincode, str) or _PINCODE.fullmatch(pincode) is None):
        raise PilotSetupValidationError("pincode must be a six-digit Indian PIN when supplied")
    if not village and not pincode:
        raise PilotSetupValidationError("add a village or PIN so the field has useful location context")
    return {
        "farm": {"name": _text(value.get("farm_name"), "farm_name")},
        "field": {
            "name": _text(value.get("field_name"), "field_name"),
            "area_hectares": _finite_area(value.get("area_hectares"), "area_hectares"),
            "crop_name": _text(value.get("crop_name"), "crop_name"),
        },
        "manager_name": _text(value.get("manager_name"), "manager_name"),
        "location": {
            "state_name": _normalise_up_state(value.get("state_name")),
            "district_name": _text(value.get("district_name"), "district_name"),
            "village_name": village,
            "pincode": pincode or None,
        },
        "writes": False,
        "still_needed_before_acceptance": [
            "Confirm the land or operating right and its dates.",
            "Confirm the active season and its dates.",
            "Name the field reporter and the first piece of work.",
            "Retain location and field evidence before a map pin or decision.",
        ],
    }


def _normalise_first_work(
    value: Any, people: Sequence[Mapping[str, str]], allocations: Sequence[Mapping[str, Any]]
) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise PilotSetupValidationError("first_work must be an object")
    owner_reference = _text(value.get("owner_reference"), "first_work.owner_reference", 80)
    if owner_reference not in {person["reference"] for person in people}:
        raise PilotSetupValidationError("first_work.owner_reference must identify a proposed person")
    allocation_reference = _text(value.get("allocation_reference"), "first_work.allocation_reference", 80)
    if allocation_reference not in {allocation["reference"] for allocation in allocations}:
        raise PilotSetupValidationError("first_work.allocation_reference must identify a proposed allocation")
    evidence = value.get("required_evidence")
    if not isinstance(evidence, list) or not evidence or not all(isinstance(item, str) and item.strip() for item in evidence):
        raise PilotSetupValidationError("first_work.required_evidence must name at least one evidence requirement")
    return {
        "title": _text(value.get("title"), "first_work.title"),
        "owner_reference": owner_reference,
        "allocation_reference": allocation_reference,
        "due_at": _iso_timestamp(value.get("due_at"), "first_work.due_at"),
        "required_evidence": [item.strip() for item in evidence],
    }


def validate_up_pilot_setup(draft: Mapping[str, Any]) -> Dict[str, Any]:
    """Normalise a complete UP first-farm proposal with no database side effect."""

    if not isinstance(draft, Mapping):
        raise PilotSetupValidationError("pilot setup must be an object")
    season = draft.get("season")
    if not isinstance(season, Mapping):
        raise PilotSetupValidationError("season must be an object")
    season_start = _iso_date(season.get("starts_on"), "season.starts_on")
    season_end = _iso_date(season.get("ends_on"), "season.ends_on")
    if season_end < season_start:
        raise PilotSetupValidationError("season.ends_on must not precede season.starts_on")
    people = _normalise_people(draft.get("people"))
    parcels = _normalise_parcels(draft.get("parcels"), season_start, season_end)
    blocks = _normalise_blocks(draft.get("blocks"), parcels)
    allocations = _normalise_allocations(draft.get("allocations"), blocks)
    location = _normalise_location(draft.get("location"))
    first_work = _normalise_first_work(draft.get("first_work"), people, allocations)
    return {
        "status": "ready_for_human_acceptance",
        "scope": {"state_name": "Uttar Pradesh", "mode": "first_farm_pilot"},
        "farm": {"name": _text(draft.get("farm_name"), "farm_name")},
        "people": people,
        "parcels": list(parcels.values()),
        "blocks": list(blocks.values()),
        "season": {"name": _text(season.get("name"), "season.name"), "starts_on": season_start, "ends_on": season_end},
        "allocations": allocations,
        "location": location,
        "first_work": first_work,
        "required_before_acceptance": [
            "named manager confirms each operating right",
            "location remains administrative context, not parcel geometry",
            "soil report is retained as evidence before a soil baseline is recorded",
            "the first work result is reviewed against its required evidence",
        ],
        "write_order": [
            "operating_unit", "people", "parcels_and_rights", "blocks_and_links", "season_and_allocations",
            "verified_location", "soil_evidence_then_baseline", "first_work",
        ],
        "persistence": "not_written_by_validation",
    }


def _acceptance_row(connection: Any, idempotency_key: str):
    return connection.execute(
        """SELECT id, content_hash, result_json FROM pilot_setup_acceptances
           WHERE idempotency_key = ?""",
        (idempotency_key,),
    ).fetchone()


def _canonical_json(value: Any) -> str:
    """Create the exact content form used for durable idempotency checks."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _replay_result(row: Any, content_hash: str) -> Dict[str, Any]:
    if row["content_hash"] != content_hash:
        raise PilotSetupValidationError("idempotency key was already used for a different pilot setup")
    result = json.loads(row["result_json"])
    result["idempotent"] = True
    return result


def _new_id() -> str:
    return str(uuid.uuid4())


def _acceptance_result(
    acceptance_id: str, operating_unit_id: str, manager_person_id: str, location_id: str,
    season_id: str, allocation_ids: Sequence[str], first_work_item_id: str,
) -> Dict[str, Any]:
    """Return only durable identifiers; proposal details stay in private tables."""

    return {
        "status": "accepted",
        "idempotent": False,
        "acceptance_id": acceptance_id,
        "operating_unit_id": operating_unit_id,
        "manager_person_id": manager_person_id,
        "location_id": location_id,
        "season_id": season_id,
        "allocation_ids": list(allocation_ids),
        "first_work_item_id": first_work_item_id,
    }


def _initial_setup_already_accepted(connection: Any) -> bool:
    return connection.execute(
        "SELECT id FROM pilot_setup_bootstrap_guard WHERE id = ?", ("initial_setup",)
    ).fetchone() is not None


def _assert_bootstrap_is_available(connection: Any) -> None:
    if _initial_setup_already_accepted(connection):
        raise PilotSetupValidationError("the first-farm setup has already been accepted")
    count = connection.execute("SELECT COUNT(*) FROM operating_units").fetchone()[0]
    if count:
        raise PilotSetupValidationError("the first-farm setup cannot be accepted after operating data exists")


def accept_up_pilot_setup(
    connection: Any,
    draft: Mapping[str, Any],
    *,
    idempotency_key: str,
    approving_manager_reference: str,
) -> Dict[str, Any]:
    """Persist one reviewed UP pilot pack in a single, durable transaction.

    The caller needs the independently configured bootstrap approval boundary;
    this service additionally binds the audit actor to a proposed farm manager
    or operations lead.  The proposal itself contains no database identifiers,
    and no individual repository helper is used because those helpers commit
    independently.
    """

    if not isinstance(idempotency_key, str) or _IDEMPOTENCY_KEY.fullmatch(idempotency_key) is None:
        raise PilotSetupValidationError("idempotency_key must be 8-128 safe characters")
    normalized = validate_up_pilot_setup(draft)
    approving_manager_reference = _text(
        approving_manager_reference, "approving_manager_reference", 80
    )
    manager = next(
        (person for person in normalized["people"] if person["reference"] == approving_manager_reference),
        None,
    )
    if manager is None or manager["role"] not in {"farm_manager", "operations_lead"}:
        raise PilotSetupValidationError(
            "approving_manager_reference must identify the proposed farm_manager or operations_lead"
        )
    content_hash = hashlib.sha256(_canonical_json({
        "proposal": normalized,
        "approving_manager_reference": approving_manager_reference,
    }).encode("utf-8")).hexdigest()
    existing = _acceptance_row(connection, idempotency_key)
    if existing is not None:
        return _replay_result(existing, content_hash)

    try:
        with connection:
            # Recheck inside the transaction because a previous request can
            # finish between the optimistic lookup and this transaction.
            existing = _acceptance_row(connection, idempotency_key)
            if existing is not None:
                return _replay_result(existing, content_hash)
            _assert_bootstrap_is_available(connection)

            accepted_at = datetime.now(timezone.utc).isoformat()
            operating_unit_id = _new_id()
            connection.execute(
                "INSERT INTO operating_units (id, name, created_at) VALUES (?, ?, ?)",
                (operating_unit_id, normalized["farm"]["name"], accepted_at),
            )

            people = {}
            for person in normalized["people"]:
                person_id = _new_id()
                people[person["reference"]] = person_id
                connection.execute(
                    "INSERT INTO people (id, name, role, created_at) VALUES (?, ?, ?, ?)",
                    (person_id, person["name"], person["role"], accepted_at),
                )
            manager_person_id = people[approving_manager_reference]

            parcels = {}
            for parcel in normalized["parcels"]:
                parcel_id = _new_id()
                parcels[parcel["reference"]] = parcel_id
                connection.execute(
                    """INSERT INTO land_parcels
                       (id, operating_unit_id, name, area_hectares, created_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (parcel_id, operating_unit_id, parcel["name"], parcel["area_hectares"], accepted_at),
                )
                connection.execute(
                    """INSERT INTO rights_to_operate
                       (id, land_parcel_id, right_type, starts_on, ends_on, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    ("right-" + _new_id(), parcel_id, parcel["right_type"], parcel["right_starts_on"],
                     parcel["right_ends_on"], accepted_at),
                )

            blocks = {}
            for block in normalized["blocks"]:
                block_id = _new_id()
                blocks[block["reference"]] = block_id
                connection.execute(
                    """INSERT INTO operational_blocks
                       (id, operating_unit_id, name, area_hectares, created_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (block_id, operating_unit_id, block["name"], block["area_hectares"], accepted_at),
                )
                for parcel_reference in block["parcel_references"]:
                    connection.execute(
                        """INSERT INTO block_parcels
                           (operational_block_id, land_parcel_id, created_at) VALUES (?, ?, ?)""",
                        (block_id, parcels[parcel_reference], accepted_at),
                    )

            season_id = _new_id()
            connection.execute(
                """INSERT INTO seasons (id, operating_unit_id, name, starts_on, ends_on, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (season_id, operating_unit_id, normalized["season"]["name"], normalized["season"]["starts_on"],
                 normalized["season"]["ends_on"], accepted_at),
            )
            allocations = {}
            for allocation in normalized["allocations"]:
                allocation_id = _new_id()
                allocations[allocation["reference"]] = allocation_id
                connection.execute(
                    """INSERT INTO crop_allocations
                       (id, operating_unit_id, operational_block_id, season_id, crop_name, cultivar,
                        area_hectares, status, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (allocation_id, operating_unit_id, blocks[allocation["block_reference"]], season_id,
                     allocation["crop_name"], allocation["cultivar"], allocation["area_hectares"], "active", accepted_at),
                )

            location = normalized["location"]
            location_id = _new_id()
            connection.execute(
                """INSERT INTO operating_unit_locations
                   (id, operating_unit_id, country_code, state_name, district_name, district_context_key,
                    subdistrict_name, village_name, pincode, verification_method, verified_by_person_id,
                    verified_at, status, supersedes_location_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (location_id, operating_unit_id, "IN", location["state_name"], location["district_name"],
                 location["district_context_key"], location["subdistrict_name"], location["village_name"],
                 location["pincode"], location["verification_method"], manager_person_id,
                 location["verified_at"], "active", None, accepted_at),
            )

            first_work = normalized["first_work"]
            first_work_item_id = _new_id()
            connection.execute(
                """INSERT INTO work_items (id, allocation_id, title, owner_id, due_at, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (first_work_item_id, allocations[first_work["allocation_reference"]], first_work["title"],
                 people[first_work["owner_reference"]], first_work["due_at"], "planned", accepted_at),
            )

            acceptance_id = _new_id()
            result = _acceptance_result(
                acceptance_id, operating_unit_id, manager_person_id, location_id, season_id,
                list(allocations.values()), first_work_item_id,
            )
            connection.execute(
                """INSERT INTO pilot_setup_acceptances
                   (id, idempotency_key, content_hash, operating_unit_id, manager_person_id,
                    first_work_item_id, first_work_required_evidence_json, result_json, status, accepted_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (acceptance_id, idempotency_key, content_hash, operating_unit_id, manager_person_id,
                 first_work_item_id, _canonical_json(first_work["required_evidence"]), _canonical_json(result),
                 "accepted", accepted_at, accepted_at),
            )
            # A unique singleton is the cross-process gate.  A loser rolls
            # back every prior insert in this transaction rather than leaving
            # a partly-created farm behind.
            connection.execute(
                """INSERT INTO pilot_setup_bootstrap_guard (id, acceptance_id, created_at)
                   VALUES (?, ?, ?)""",
                ("initial_setup", acceptance_id, accepted_at),
            )
            connection.execute(
                """INSERT INTO audit_events
                   (id, entity_type, entity_id, from_status, to_status, actor_id, reason, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (_new_id(), "pilot_setup", acceptance_id, "none", "accepted", manager_person_id,
                 "bootstrap_setup_accepted", accepted_at),
            )
            return result
    except sqlite3.IntegrityError:
        # PostgreSQL's compatibility facade maps unique-constraint races to
        # sqlite3.IntegrityError.  Re-read only after the transaction has been
        # rolled back, then distinguish a retry from another accepted setup.
        existing = _acceptance_row(connection, idempotency_key)
        if existing is not None:
            return _replay_result(existing, content_hash)
        if _initial_setup_already_accepted(connection):
            raise PilotSetupValidationError("the first-farm setup has already been accepted")
        raise
