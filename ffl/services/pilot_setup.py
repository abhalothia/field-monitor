"""Validate the first Uttar Pradesh farm pack without creating any records.

The route using this service is deliberately a rehearsal.  It gives a manager
one precise place to check the real farm's facts before a separate, reviewed
acceptance flow writes the operating record.  A proposal never creates people,
rights, land, work, or a location by implication.
"""

from datetime import date, datetime, timezone
import math
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


_PINCODE = re.compile(r"[0-9]{6}")
_UP_CONTEXT_KEY = re.compile(r"up:[a-z0-9][a-z0-9-]{1,118}")
_UP_ALIASES = {"up", "u.p", "u.p.", "uttar pradesh"}
_ROLES = {"farm_manager", "operations_lead", "agronomist", "field_operator"}


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
    allocations = _items(value, "allocations")
    totals: Dict[str, float] = {reference: 0.0 for reference in blocks}
    result: List[Dict[str, Any]] = []
    for item in allocations:
        block_reference = _text(item.get("block_reference"), "allocation.block_reference", 80)
        if block_reference not in blocks:
            raise PilotSetupValidationError("allocation.block_reference must identify a proposed block")
        area = _finite_area(item.get("area_hectares"), "allocation.area_hectares")
        totals[block_reference] += area
        result.append({
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
    }


def _normalise_first_work(value: Any, people: Sequence[Mapping[str, str]]) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise PilotSetupValidationError("first_work must be an object")
    owner_reference = _text(value.get("owner_reference"), "first_work.owner_reference", 80)
    if owner_reference not in {person["reference"] for person in people}:
        raise PilotSetupValidationError("first_work.owner_reference must identify a proposed person")
    evidence = value.get("required_evidence")
    if not isinstance(evidence, list) or not evidence or not all(isinstance(item, str) and item.strip() for item in evidence):
        raise PilotSetupValidationError("first_work.required_evidence must name at least one evidence requirement")
    return {
        "title": _text(value.get("title"), "first_work.title"),
        "owner_reference": owner_reference,
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
    first_work = _normalise_first_work(draft.get("first_work"), people)
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
            "verified_location", "soil_evidence_then_baseline", "first_work_and_signal_template",
        ],
        "persistence": "not_written_by_validation",
    }
