"""Immutable, provider-neutral contracts for TrackOlap source rows.

This module deliberately has no database, HTTP, or FastAPI dependency.  Both
an approved CSV export and a reviewed API configuration must produce these
same records before the source data can enter the application.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional


FEEDS = frozenset(
    {
        "officers",
        "attendance",
        "farmer_tasks",
        "visits",
        "issue_observations",
        "pesticide_events",
    }
)

COMMON_FIELDS = ("source_id", "source_updated_at", "tenant_id")

REQUIRED_FIELDS: Mapping[str, tuple[str, ...]] = {
    "officers": (
        "officer_id",
        "display_name",
        "role",
        "active_status",
        "territory_owner_id",
        "effective_from",
    ),
    "attendance": ("attendance_id", "officer_id", "punch_status", "observed_at"),
    "farmer_tasks": (
        "task_id",
        "farmer_code",
        "territory_owner_id",
        "village_key",
        "task_status",
        "kit_status",
    ),
    "visits": (
        "visit_id",
        "task_id",
        "filing_officer_id",
        "performed_at",
        "submitted_at",
        "visit_status",
    ),
    "issue_observations": (
        "observation_id",
        "visit_id",
        "task_id",
        "issue_code",
        "severity",
        "observed_at",
    ),
    "pesticide_events": (
        "event_id",
        "task_id",
        "product_code",
        "event_kind",
        "occurred_at",
        "kit_version",
    ),
}

OPTIONAL_FIELDS = frozenset(
    {
        "transplanted_at",
        "crop_name",
        "cultivar",
        "approved_dat_start",
        "approved_dat_end",
        "effective_against",
    }
)


@dataclass(frozen=True)
class TrackolapRecord:
    """One approved-feed source revision, stripped of unsupported fields."""

    feed: str
    source_id: str
    source_updated_at: str
    tenant_id: str
    values: Mapping[str, str]


@dataclass(frozen=True)
class MappingResult:
    record: Optional[TrackolapRecord]
    errors: tuple[Mapping[str, str], ...]


@dataclass(frozen=True)
class ParsedRow:
    feed: str
    row_number: int
    result: MappingResult

    @property
    def record(self) -> Optional[TrackolapRecord]:
        return self.result.record

    @property
    def errors(self) -> tuple[Mapping[str, str], ...]:
        return self.result.errors


@dataclass(frozen=True)
class ParsedBundle:
    rows: tuple[ParsedRow, ...]
    errors: tuple[Mapping[str, str], ...] = ()
