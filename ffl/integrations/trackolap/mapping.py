"""Explicit mapping and validation for the six approved TrackOlap feeds."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from types import MappingProxyType
from typing import Any, Mapping

from .contracts import COMMON_FIELDS, FEEDS, OPTIONAL_FIELDS, REQUIRED_FIELDS, MappingResult, TrackolapRecord


_OPAQUE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_VALUE_LENGTH = 512
_FORBIDDEN_SOURCE_COLUMN_TERMS = frozenset(
    {
        "phone",
        "mobile",
        "aadhaar",
        "bank",
        "account",
        "payment",
        "latitude",
        "longitude",
        "gps",
        "geometry",
        "boundary",
    }
)


class MappingManifestError(ValueError):
    """The operator-supplied mapping is incomplete or admits unsupported data."""


@dataclass(frozen=True)
class MappingManifest:
    """A reviewed mapping from normalized fields to exact provider columns.

    A partial manifest is useful for profiling a single CSV file.  The import
    service, rather than this pure mapper, requires all six feeds before it
    creates an import batch.
    """

    version: str
    feeds: Mapping[str, Mapping[str, str]]

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "MappingManifest":
        if not isinstance(value, Mapping):
            raise MappingManifestError("mapping manifest must be an object")
        version = value.get("version")
        feed_maps = value.get("feeds")
        if not isinstance(version, str) or not version.strip():
            raise MappingManifestError("mapping manifest version is required")
        if not isinstance(feed_maps, Mapping) or not feed_maps:
            raise MappingManifestError("mapping manifest feeds are required")

        normalized: dict[str, Mapping[str, str]] = {}
        for feed, field_map in feed_maps.items():
            if feed not in FEEDS:
                raise MappingManifestError(f"unsupported TrackOlap feed: {feed}")
            if not isinstance(field_map, Mapping):
                raise MappingManifestError(f"mapping for {feed} must be an object")
            allowed_fields = set(COMMON_FIELDS) | set(REQUIRED_FIELDS[feed]) | set(OPTIONAL_FIELDS)
            clean_map: dict[str, str] = {}
            for normalized_field, source_column in field_map.items():
                if normalized_field not in allowed_fields:
                    raise MappingManifestError(
                        f"field {normalized_field} is not admitted for {feed}"
                    )
                if not isinstance(source_column, str) or not source_column.strip():
                    raise MappingManifestError(
                        f"mapping for {feed}.{normalized_field} must name a source column"
                    )
                source_column = source_column.strip()
                if _forbidden_source_column(source_column):
                    raise MappingManifestError(
                        f"forbidden source column for {feed}.{normalized_field}"
                    )
                clean_map[normalized_field] = source_column
            normalized[feed] = MappingProxyType(clean_map)

        return cls(version=version.strip(), feeds=MappingProxyType(normalized))

    def fields_for(self, feed: str) -> Mapping[str, str]:
        return self.feeds.get(feed, MappingProxyType({}))

    def requires_all_feeds(self) -> None:
        missing = sorted(FEEDS - set(self.feeds))
        if missing:
            raise MappingManifestError("mapping manifest is missing feeds: " + ", ".join(missing))


def normalise_row(
    feed: str, raw: Mapping[str, Any], manifest: MappingManifest
) -> MappingResult:
    """Map one raw source row without inventing a field, identifier, or date."""

    if feed not in FEEDS:
        return MappingResult(None, (_error("unsupported_feed", "feed", "feed is not approved"),))
    field_map = manifest.fields_for(feed)
    if not field_map:
        return MappingResult(None, (_error("feed_not_mapped", "feed", "feed has no reviewed mapping"),))

    required = (*COMMON_FIELDS, *REQUIRED_FIELDS[feed])
    mapped: dict[str, str] = {}
    errors: list[Mapping[str, str]] = []
    for field in required:
        source_column = field_map.get(field)
        if source_column is None or source_column not in raw:
            errors.append(
                _error("missing_mapped_column", field, f"required mapped column missing for {field}")
            )
            continue
        raw_value = raw[source_column]
        value = "" if raw_value is None else str(raw_value).strip()
        if not value:
            errors.append(_error("missing_value", field, f"{field} is required"))
            continue
        mapped[field] = value

    for field, source_column in field_map.items():
        if field in mapped or source_column not in raw:
            continue
        raw_value = raw[source_column]
        value = "" if raw_value is None else str(raw_value).strip()
        if value:
            mapped[field] = value

    if errors:
        return MappingResult(None, tuple(errors))

    errors.extend(_validate_values(feed, mapped))
    if errors:
        return MappingResult(None, tuple(errors))

    values = {
        field: value
        for field, value in mapped.items()
        if field not in COMMON_FIELDS
    }
    return MappingResult(
        TrackolapRecord(
            feed=feed,
            source_id=mapped["source_id"],
            source_updated_at=mapped["source_updated_at"],
            tenant_id=mapped["tenant_id"],
            values=MappingProxyType(values),
        ),
        (),
    )


def _validate_values(feed: str, values: Mapping[str, str]) -> list[Mapping[str, str]]:
    errors: list[Mapping[str, str]] = []
    for field, value in values.items():
        if len(value) > _MAX_VALUE_LENGTH or any(character in value for character in "\r\n\x00"):
            errors.append(_error("invalid_value", field, "value contains unsupported characters or is too long"))
        if field == "source_id" or field == "tenant_id" or field.endswith("_id"):
            if not _OPAQUE_ID.fullmatch(value):
                errors.append(_error("invalid_identifier", field, "identifier must be a stable opaque value"))
        if field == "source_updated_at" or field.endswith("_at"):
            if not _is_timezone_aware_timestamp(value):
                errors.append(
                    _error("invalid_timestamp", field, "timestamp must include a timezone offset")
                )
    return errors


def _is_timezone_aware_timestamp(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _error(code: str, field: str, message: str) -> Mapping[str, str]:
    return MappingProxyType({"code": code, "field": field, "message": message})


def _forbidden_source_column(column: str) -> bool:
    words = set(re.findall(r"[a-z0-9]+", column.lower()))
    return bool(words & _FORBIDDEN_SOURCE_COLUMN_TERMS) or {"farmer", "name"}.issubset(words)
