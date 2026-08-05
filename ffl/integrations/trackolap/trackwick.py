"""Read-only TrackWick task and attendance adapter.

TrackWick is a TrackOlap tenant whose field operation is exposed as a Farmer
Visit task stream plus a daily productivity endpoint.  This adapter keeps that
provider shape explicit instead of pretending it has six provider endpoints.
Raw tasks exist only in memory: normalisation admits the small set of
aggregate-operating fields that AGRO CEO can use and deliberately excludes
names, mobile numbers, photos, GPS and raw form payloads.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
import hashlib
import os
import re
import time as clock
from types import MappingProxyType
from typing import Any, Callable, Mapping, Optional, Sequence
from urllib.parse import urlparse, urlunparse
from zoneinfo import ZoneInfo

import httpx

from .contracts import TrackolapRecord


BASE_URL = "https://app.trackolap.com"
TASK_LIST_PATH = "/cust/1/api/task/list"
CUSTOMER_LIST_PATH = "/cust/1/api/customer/list"
PRODUCTIVITY_PATH = "/cust/1/api/asset/productivity"
DEFAULT_FORM_TITLE = "Farmer Visit"
DEFAULT_TIMEZONE = "Asia/Kolkata"
MAPPING_VERSION = "trackwick-task-v3"
PRIVATE_EVIDENCE_MAPPING_VERSION = "trackwick-private-v1"

_OPAQUE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_CUSTOMER_NAME_CODE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._:-]{0,127})(?=\s*\()")
_CREDENTIAL_REFERENCE = re.compile(r"(?:env|secret)://[A-Za-z0-9][A-Za-z0-9._/-]{0,127}")
_EMPTY_ANSWER = frozenset({"", "-", "na", "n/a", "nil", "none", "no", "not applicable", "नहीं", "कोई नहीं"})

_FORM_KEYS = {
    "kit_taken": "क्या किसान ने किट ले ली है?",
    "location": "स्थान",
    "disease": "क्या फसल में कोई रोग है ?",
    "other_disease": "फसल में कोई अन्य रोग ?",
    "pest": "क्या फसल में कोई कीट है ?",
    "other_pest": "कोई अन्य कीट?",
    "pesticide_used": "जिस कीटनाशक (Pesticide) का छिड़काव किया गया है , सूची में उसका चयन करें ?",
    "other_pesticide": "कोई अन्य कीटनाशक (Pesticide) का छिड़काव किया गया है तो उसकी जानकारी दें",
    "pesticide_recommended": "कृपया उस कीटनाशक (Pesticide) का चयन करें, जिसका सुझाव आपने किसानों को दिया है।",
    "fertilizer_used": "उर्वरक (Fertilizer) का उपयोग",
    "fertilizer_recommended": "कृपया उस उर्वरक (Fertilizer) का चयन करें, जिसका सुझाव आपने किसानों को दिया है।",
    "crop_photo": "फसल की फोटो",
}

_REGISTRATION_FORM_KEYS = {
    "village": "Village",
    "block": "Block",
    "district": "District",
    "area_acres": "Total Acre",
    "plot_count": "Number of Plots",
    "pb1_area_acres": "P.B-1 Acre",
    "var1718_area_acres": "1718 Acre",
}

_VISIT_BASIC_FORM_KEYS = {
    "transplanted_at": "रोपाई की तारीख (Date of transplanting)",
    "crop_stage": "फसल की अवस्था",
    "water_condition": "खेत में पानी की स्थिति",
    "crop_condition": "फसल की स्थिति (1 = बहुत खराब | 10 = बहुत अच्छी )",
}

_SOIL_TASK_TYPES = frozenset({"new farmer soil testing", "registered farmer soil testing"})
_TRACKWICK_MEDIA_HOST = "trackolap-images-prod.s3.amazonaws.com"
_PRIVATE_TABLE_ORDER = (
    "trackwick_parties",
    "trackwick_contact_points",
    "trackwick_tasks",
    "trackwick_visits",
    "trackwick_visit_findings",
    "trackwick_crop_inputs",
    "trackwick_registrations",
    "trackwick_registration_plots",
    "trackwick_media_references",
    "trackwick_location_observations",
    "trackwick_worker_days",
)


class TrackwickConfigurationError(ValueError):
    """TrackWick configuration is missing or unsafe."""


class TrackwickSourceFailure(RuntimeError):
    """A provider response could not be safely used."""


@dataclass(frozen=True)
class TrackwickApiConfig:
    """Server-only TrackWick connection settings.

    The customer id is a tenant selector, not an API secret.  The API key is
    resolved only at request time from a server-side reference and never forms
    part of a response, source run, or stored source record.
    """

    customer_id: str
    tenant_id: str
    api_key_reference: str
    reporting_timezone: str = DEFAULT_TIMEZONE
    form_title: str = DEFAULT_FORM_TITLE
    page_size: int = 100
    max_pages: int = 500
    delta_lookback_days: int = 2
    severity_form_key: Optional[str] = None
    plot_photo_form_key: Optional[str] = None
    task_plot_reference_form_key: Optional[str] = None

    @classmethod
    def from_environment(
        cls, environment: Optional[Mapping[str, str]] = None
    ) -> Optional["TrackwickApiConfig"]:
        values = environment or os.environ
        if values.get("FFL_TRACKWICK_ENABLED", "").strip().lower() != "true":
            return None
        customer_id = _required_opaque(values.get("FFL_TRACKWICK_CUSTOMER_ID"), "FFL_TRACKWICK_CUSTOMER_ID")
        tenant_id = _required_opaque(values.get("FFL_TRACKWICK_TENANT_ID", customer_id), "FFL_TRACKWICK_TENANT_ID")
        reference = values.get("FFL_TRACKWICK_API_KEY_REFERENCE", "env://FFL_TRACKWICK_API_KEY")
        if _CREDENTIAL_REFERENCE.fullmatch(reference or "") is None:
            raise TrackwickConfigurationError("FFL_TRACKWICK_API_KEY_REFERENCE is invalid")
        form_title = str(values.get("FFL_TRACKWICK_FORM_TITLE", DEFAULT_FORM_TITLE)).strip()
        if not form_title or len(form_title) > 120 or any(character in form_title for character in "\r\n\x00"):
            raise TrackwickConfigurationError("FFL_TRACKWICK_FORM_TITLE is invalid")
        reporting_timezone = str(values.get("FFL_TRACKWICK_REPORTING_TIMEZONE", DEFAULT_TIMEZONE)).strip()
        try:
            ZoneInfo(reporting_timezone)
        except Exception as error:
            raise TrackwickConfigurationError("FFL_TRACKWICK_REPORTING_TIMEZONE must be an IANA timezone") from error
        severity_form_key = _optional_form_key(
            values.get("FFL_TRACKWICK_SEVERITY_FORM_KEY"),
            "FFL_TRACKWICK_SEVERITY_FORM_KEY",
        )
        plot_photo_form_key = _optional_form_key(
            values.get("FFL_TRACKWICK_PLOT_PHOTO_FORM_KEY"),
            "FFL_TRACKWICK_PLOT_PHOTO_FORM_KEY",
        )
        task_plot_reference_form_key = _optional_form_key(
            values.get("FFL_TRACKWICK_TASK_PLOT_REFERENCE_FORM_KEY"),
            "FFL_TRACKWICK_TASK_PLOT_REFERENCE_FORM_KEY",
        )
        return cls(
            customer_id=customer_id,
            tenant_id=tenant_id,
            api_key_reference=reference,
            reporting_timezone=reporting_timezone,
            form_title=form_title,
            page_size=_bounded_int(values.get("FFL_TRACKWICK_TASK_PAGE_SIZE"), 100, 1, 250),
            max_pages=_bounded_int(values.get("FFL_TRACKWICK_TASK_MAX_PAGES"), 500, 1, 1000),
            delta_lookback_days=_bounded_int(
                values.get("FFL_TRACKWICK_DELTA_LOOKBACK_DAYS"), 2, 1, 31
            ),
            severity_form_key=severity_form_key,
            plot_photo_form_key=plot_photo_form_key,
            task_plot_reference_form_key=task_plot_reference_form_key,
        )


@dataclass(frozen=True)
class TrackwickFetchResult:
    tasks: tuple[Mapping[str, Any], ...]
    attendance: tuple[Mapping[str, Any], ...]
    task_pages: int
    customers: tuple[Mapping[str, Any], ...] = ()
    customer_pages: int = 0

    @property
    def rows_received(self) -> int:
        return len(self.tasks) + len(self.customers) + len(self.attendance)


@dataclass(frozen=True)
class TrackwickNormalisationResult:
    records: tuple[TrackolapRecord, ...]
    quarantined_rows: int


@dataclass(frozen=True)
class TrackwickPrivateRecord:
    """One allow-listed row for the private TrackWick evidence graph.

    The source adapter returns typed values, never the raw provider task or
    form payload.  Repository code appends source-run provenance and performs
    the reviewed upsert into the private database tables.
    """

    table: str
    values: Mapping[str, Any]


@dataclass(frozen=True)
class TrackwickPrivateEvidenceResult:
    records: tuple[TrackwickPrivateRecord, ...]
    quarantined_rows: int

    def records_by_table(self) -> dict[str, tuple[TrackwickPrivateRecord, ...]]:
        grouped: dict[str, list[TrackwickPrivateRecord]] = {}
        for record in self.records:
            grouped.setdefault(record.table, []).append(record)
        return {table: tuple(rows) for table, rows in grouped.items()}


class TrackwickApiAdapter:
    """Bounded GET-only reader for the two verified TrackWick endpoints."""

    def fetch(
        self,
        config: TrackwickApiConfig,
        api_key: str,
        as_of: Optional[datetime] = None,
        created_since: Optional[datetime] = None,
        created_until: Optional[datetime] = None,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> TrackwickFetchResult:
        if not api_key:
            raise TrackwickSourceFailure("credentials_unavailable")
        now = (as_of or datetime.now(timezone.utc)).astimezone(ZoneInfo(config.reporting_timezone))
        params = {
            "pt": config.page_size,
            "showForm": "true",
        }
        if created_since is not None:
            params["createDateBegin"] = _epoch_milliseconds(created_since, config.reporting_timezone)
        if created_until is not None:
            params["createDateEnd"] = _epoch_milliseconds(created_until, config.reporting_timezone)
        headers = _headers(config.customer_id, api_key)
        tasks: list[Mapping[str, Any]] = []
        with httpx.Client(transport=transport, follow_redirects=False, timeout=30.0) as client:
            for page in range(config.max_pages):
                response = _get(
                    client,
                    TASK_LIST_PATH,
                    headers,
                    {**params, "pn": page},
                )
                rows, has_more = _rows(response, "task_list_response_invalid")
                tasks.extend(rows)
                if not has_more:
                    break
            else:
                raise TrackwickSourceFailure("task_page_limit_reached")

            customers: list[Mapping[str, Any]] = []
            for customer_page in range(config.max_pages):
                response = _get(
                    client,
                    CUSTOMER_LIST_PATH,
                    headers,
                    {"pt": config.page_size, "pn": customer_page},
                )
                rows, has_more = _rows(response, "customer_list_response_invalid")
                customers.extend(rows)
                if not has_more:
                    break
            else:
                raise TrackwickSourceFailure("customer_page_limit_reached")

            attendance_response = _get(
                client,
                PRODUCTIVITY_PATH,
                headers,
                {"date": now.date().isoformat()},
            )
            attendance, _unused_has_more = _rows(attendance_response, "attendance_response_invalid")
        return TrackwickFetchResult(
            tasks=tuple(tasks),
            customers=tuple(customers),
            attendance=tuple(attendance),
            task_pages=page + 1,
            customer_pages=customer_page + 1,
        )


def refresh_trackwick(
    config: Optional[TrackwickApiConfig],
    credential_resolver: Callable[[str], Optional[str]],
    as_of: Optional[datetime] = None,
    created_since: Optional[datetime] = None,
    created_until: Optional[datetime] = None,
    transport: Optional[httpx.BaseTransport] = None,
    adapter: Optional[TrackwickApiAdapter] = None,
) -> TrackwickFetchResult:
    """Resolve the server credential before any provider request is attempted."""
    if config is None:
        raise TrackwickSourceFailure("configuration_unavailable")
    api_key = credential_resolver(config.api_key_reference)
    if not api_key:
        raise TrackwickSourceFailure("credentials_unavailable")
    return (adapter or TrackwickApiAdapter()).fetch(
        config,
        api_key,
        as_of=as_of,
        created_since=created_since,
        created_until=created_until,
        transport=transport,
    )


def normalise_trackwick(
    fetched: TrackwickFetchResult,
    config: TrackwickApiConfig,
    as_of: Optional[datetime] = None,
) -> TrackwickNormalisationResult:
    """Create only safe, aggregate-operating source records from provider rows."""
    timezone_value = ZoneInfo(config.reporting_timezone)
    fallback_time = (as_of or datetime.now(timezone.utc)).astimezone(timezone_value)
    records: list[TrackolapRecord] = []
    quarantined = 0
    for task in fetched.tasks:
        task_records = _normalise_task(task, config, fallback_time)
        if task_records is None:
            quarantined += 1
            continue
        records.extend(task_records)
    for attendance in fetched.attendance:
        attendance_records = _normalise_attendance(attendance, config, fallback_time)
        if attendance_records is None:
            quarantined += 1
            continue
        records.extend(attendance_records)
    return TrackwickNormalisationResult(tuple(records), quarantined)


def normalise_trackwick_basics(
    fetched: TrackwickFetchResult,
    config: TrackwickApiConfig,
    as_of: Optional[datetime] = None,
) -> TrackwickNormalisationResult:
    """Create an allow-listed CRM staging view from the live tenant.

    This is deliberately separate from the aggregate COO metrics lane.  It
    admits only names, stable identifiers, work ownership, coarse operating
    location, acreage, crop timing, and task state.  Aadhaar, mobile numbers,
    signatures, photos, comments, raw form payloads, and exact GPS are not
    read into a normalized record under any condition.
    """
    timezone_value = ZoneInfo(config.reporting_timezone)
    fallback_time = (as_of or datetime.now(timezone.utc)).astimezone(timezone_value)
    records: list[TrackolapRecord] = []
    quarantined = 0

    for customer in fetched.customers:
        record = _normalise_customer(customer, config, fallback_time)
        if record is None:
            quarantined += 1
            continue
        records.append(record)

    for task in fetched.tasks:
        task_records = _normalise_task_basics(task, config, fallback_time)
        if task_records is None:
            quarantined += 1
            continue
        records.extend(task_records)
    return TrackwickNormalisationResult(tuple(records), quarantined)


def normalise_trackwick_private_evidence(
    fetched: TrackwickFetchResult,
    config: TrackwickApiConfig,
    as_of: Optional[datetime] = None,
) -> TrackwickPrivateEvidenceResult:
    """Map the reviewed private TrackWick evidence contract.

    This is intentionally separate from the public-safe aggregate and basics
    lanes.  It reads exact location, remote crop/plot-photo references and
    contact data only into the server-only private graph.  It never creates a
    canonical Fortune entity and never serialises raw task/form payloads.
    """
    timezone_value = ZoneInfo(config.reporting_timezone)
    fallback_time = (as_of or datetime.now(timezone.utc)).astimezone(timezone_value)
    collector = _PrivateEvidenceCollector()
    quarantined = 0

    for customer in fetched.customers:
        if not _normalise_private_customer(customer, config, fallback_time, collector):
            quarantined += 1
    for task in fetched.tasks:
        if not _normalise_private_task(task, config, fallback_time, collector):
            quarantined += 1
    for attendance in fetched.attendance:
        if not _normalise_private_attendance(attendance, config, fallback_time, collector):
            quarantined += 1

    return TrackwickPrivateEvidenceResult(collector.records(), quarantined)


class _PrivateEvidenceCollector:
    """Deduplicate provider identities before persistence without raw payloads."""

    def __init__(self) -> None:
        self._rows: dict[str, dict[str, dict[str, Any]]] = {
            table: {} for table in _PRIVATE_TABLE_ORDER
        }

    def add(self, table: str, values: Mapping[str, Any]) -> None:
        if table not in self._rows:
            raise ValueError("unknown private TrackWick table")
        identifier = values.get("id") or values.get("task_id")
        if not isinstance(identifier, str) or not identifier:
            raise ValueError("private TrackWick record requires an id")
        current = self._rows[table].get(identifier)
        if current is None:
            self._rows[table][identifier] = dict(values)
            return
        for key, value in values.items():
            if value is None:
                continue
            if current.get(key) in (None, "", "Farmer", "Field worker"):
                current[key] = value

    def records(self) -> tuple[TrackwickPrivateRecord, ...]:
        return tuple(
            TrackwickPrivateRecord(table, MappingProxyType(dict(values)))
            for table in _PRIVATE_TABLE_ORDER
            for values in self._rows[table].values()
        )


def _normalise_private_customer(
    customer: Mapping[str, Any], config: TrackwickApiConfig, fallback_time: datetime,
    collector: _PrivateEvidenceCollector,
) -> bool:
    provider_identifier = _opaque(customer.get("iden")) or _opaque(customer.get("id"))
    if provider_identifier is None:
        return False
    created_at = _timestamp(customer.get("createdOn"), fallback_time.tzinfo) or fallback_time
    party_id = _add_private_party(
        collector,
        config.tenant_id,
        "farmer",
        provider_identifier,
        _safe_text(customer.get("name"), maximum=160) or "Farmer",
        crm_status=_private_status(customer.get("status")),
        provider_owner_identifier=_opaque(customer.get("owner")),
        provider_tag=_safe_text(customer.get("tag"), maximum=120),
        provider_created_at=created_at.isoformat(),
    )
    _add_private_contact(collector, config.tenant_id, party_id, customer.get("mobile"))
    _add_private_location(
        collector,
        config.tenant_id,
        provider_location_key="crm:" + provider_identifier,
        location_kind="crm",
        location=customer.get("geo"),
        observed_at=created_at.isoformat(),
        party_id=party_id,
    )
    return True


def _normalise_private_task(
    task: Mapping[str, Any], config: TrackwickApiConfig, fallback_time: datetime,
    collector: _PrivateEvidenceCollector,
) -> bool:
    provider_task_id = _opaque(task.get("id"))
    task_type = _safe_text(task.get("type"), maximum=120)
    observed_at = _task_time(task, fallback_time)
    if provider_task_id is None or task_type is None or observed_at is None:
        return False
    task_id = _private_id("task", config.tenant_id, provider_task_id)
    farmer_identifier = _farmer_code(task)
    farmer_party_id = None
    if farmer_identifier is not None:
        farmer_party_id = _add_private_party(
            collector,
            config.tenant_id,
            "farmer",
            farmer_identifier,
            _task_customer_display_name(task) or "Farmer",
        )
        _add_private_contact(collector, config.tenant_id, farmer_party_id, task.get("customerMobile"))
    worker_identifier = _opaque(task.get("employeeIden"))
    field_worker_party_id = None
    if worker_identifier is not None:
        field_worker_party_id = _add_private_party(
            collector,
            config.tenant_id,
            "field_worker",
            worker_identifier,
            _safe_text(task.get("assignedTo"), maximum=160) or "Field worker",
        )
    status = _private_status(task.get("status"))
    form = task.get("formDetails")
    form_details = form if isinstance(form, Mapping) else {}
    provider_plot_reference = (
        _safe_text(
            form_details.get(config.task_plot_reference_form_key), maximum=120
        )
        if config.task_plot_reference_form_key
        else None
    )
    collector.add("trackwick_tasks", {
        "id": task_id,
        "provider_task_id": provider_task_id,
        "farmer_party_id": farmer_party_id,
        "field_worker_party_id": field_worker_party_id,
        "provider_customer_identifier": farmer_identifier,
        "task_type": task_type,
        "task_status": status,
        "provider_created_at": _timestamp_iso(task.get("created"), fallback_time),
        "provider_started_at": _timestamp_iso(task.get("started"), fallback_time),
        "provider_completed_at": _timestamp_iso(task.get("completed"), fallback_time),
        "provider_follow_up_at": _timestamp_iso(task.get("followUpDate"), fallback_time),
        "provider_plot_reference": provider_plot_reference,
    })
    _add_private_location(
        collector,
        config.tenant_id,
        provider_location_key="task-completion:" + provider_task_id,
        location_kind="task_completion",
        location=task.get("completeGeo"),
        observed_at=observed_at,
        task_id=task_id,
        accuracy=_safe_nonnegative_number(task.get("accuracy")),
    )

    type_key = task_type.casefold()
    if type_key == config.form_title.casefold() and status == "completed":
        _normalise_private_visit(
            task_id, provider_task_id, form_details, observed_at, config, collector,
        )
    if type_key == "new farmer registration":
        _normalise_private_registration(
            task_id, farmer_party_id, form_details, status, observed_at, config, collector,
        )
    if type_key in _SOIL_TASK_TYPES:
        _add_private_location(
            collector,
            config.tenant_id,
            provider_location_key="soil:" + provider_task_id,
            location_kind="soil",
            location=form_details.get("Field GPS Location"),
            observed_at=observed_at,
            task_id=task_id,
        )
    if config.plot_photo_form_key:
        _add_private_media(
            collector,
            config,
            task_id,
            provider_task_id,
            "plot_photo",
            form_details.get(config.plot_photo_form_key),
            observed_at,
        )
    return True


def _normalise_private_visit(
    task_id: str,
    provider_task_id: str,
    form: Mapping[str, Any],
    observed_at: str,
    config: TrackwickApiConfig,
    collector: _PrivateEvidenceCollector,
) -> None:
    collector.add("trackwick_visits", {
        "task_id": task_id,
        "observed_at": observed_at,
        "transplanted_on": _safe_date(form.get(_VISIT_BASIC_FORM_KEYS["transplanted_at"])),
        "crop_stage": _safe_text(form.get(_VISIT_BASIC_FORM_KEYS["crop_stage"]), maximum=120),
        "water_condition": _safe_text(form.get(_VISIT_BASIC_FORM_KEYS["water_condition"]), maximum=120),
        "crop_condition_score": _safe_score(form.get(_VISIT_BASIC_FORM_KEYS["crop_condition"])),
        "kit_status": _kit_status(form.get(_FORM_KEYS["kit_taken"])),
    })
    severity = _severity(form.get(config.severity_form_key)) if config.severity_form_key else "unknown"
    for field, kind in (
        ("disease", "disease"),
        ("other_disease", "disease"),
        ("pest", "pest"),
        ("other_pest", "pest"),
    ):
        source_field = _FORM_KEYS[field]
        for answer in _answers(form.get(source_field)):
            collector.add("trackwick_visit_findings", {
                "id": _private_id("finding", config.tenant_id, task_id, kind, source_field, answer),
                "visit_task_id": task_id,
                "finding_kind": kind,
                "reported_value": answer,
                "source_field": source_field,
                "declared_severity": severity,
                "observed_at": observed_at,
            })
    for field, input_kind, event_kind in (
        ("pesticide_used", "pesticide", "applied"),
        ("other_pesticide", "pesticide", "applied"),
        ("pesticide_recommended", "pesticide", "recommended"),
        ("fertilizer_used", "fertilizer", "applied"),
        ("fertilizer_recommended", "fertilizer", "recommended"),
    ):
        source_field = _FORM_KEYS[field]
        for answer in _answers(form.get(source_field)):
            collector.add("trackwick_crop_inputs", {
                "id": _private_id("input", config.tenant_id, task_id, input_kind, event_kind, source_field, answer),
                "visit_task_id": task_id,
                "input_kind": input_kind,
                "event_kind": event_kind,
                "reported_product": answer,
                "source_field": source_field,
                "occurred_at": observed_at,
            })
    _add_private_location(
        collector,
        config.tenant_id,
        provider_location_key="visit-location:" + provider_task_id,
        location_kind="visit_location",
        location=form.get(_FORM_KEYS["location"]),
        observed_at=observed_at,
        task_id=task_id,
    )
    _add_private_media(
        collector, config, task_id, provider_task_id, "crop_photo",
        form.get(_FORM_KEYS["crop_photo"]), observed_at,
    )


def _normalise_private_registration(
    task_id: str,
    farmer_party_id: Optional[str],
    form: Mapping[str, Any],
    status: str,
    observed_at: str,
    config: TrackwickApiConfig,
    collector: _PrivateEvidenceCollector,
) -> None:
    registration_id = _private_id("registration", config.tenant_id, task_id)
    collector.add("trackwick_registrations", {
        "id": registration_id,
        "task_id": task_id,
        "farmer_party_id": farmer_party_id,
        "registration_status": status,
        "village_name": _safe_text(form.get(_REGISTRATION_FORM_KEYS["village"]), maximum=120),
        "block_name": _safe_text(form.get(_REGISTRATION_FORM_KEYS["block"]), maximum=120),
        "district_name": _safe_text(form.get(_REGISTRATION_FORM_KEYS["district"]), maximum=120),
        "reported_total_area_acres": _safe_number(form.get(_REGISTRATION_FORM_KEYS["area_acres"])),
        "reported_plot_count": _safe_integer(form.get(_REGISTRATION_FORM_KEYS["plot_count"])),
        "reported_pb1_area_acres": _safe_number(form.get(_REGISTRATION_FORM_KEYS["pb1_area_acres"])),
        "reported_1718_area_acres": _safe_number(form.get(_REGISTRATION_FORM_KEYS["var1718_area_acres"])),
    })
    if farmer_party_id is not None:
        _add_private_contact(collector, config.tenant_id, farmer_party_id, form.get("Mobile No"))
    _add_private_location(
        collector,
        config.tenant_id,
        provider_location_key="registration:" + task_id,
        location_kind="registration",
        location=form.get("Geo"),
        observed_at=observed_at,
        registration_id=registration_id,
    )
    plots = form.get("Plot Details")
    if not isinstance(plots, list):
        return
    for ordinal, plot in enumerate(plots, start=1):
        if not isinstance(plot, Mapping):
            continue
        collector.add("trackwick_registration_plots", {
            "id": _private_id("plot", config.tenant_id, registration_id, ordinal),
            "registration_id": registration_id,
            "ordinal": ordinal,
            "gata_number": _safe_text(plot.get("Gata No."), maximum=120),
            "reported_area_bigha": _safe_number(plot.get("Plot Size (Bigha)")),
            "plot_type": _safe_text(plot.get("Plot Type"), maximum=120),
            "village_name": _safe_text(plot.get("Village"), maximum=120),
        })


def _normalise_private_attendance(
    attendance: Mapping[str, Any], config: TrackwickApiConfig, fallback_time: datetime,
    collector: _PrivateEvidenceCollector,
) -> bool:
    provider_identifier = _opaque(attendance.get("empId"))
    observed_at = _date_time(attendance.get("date"), fallback_time, config.reporting_timezone)
    if provider_identifier is None or observed_at is None:
        return False
    party_id = _add_private_party(
        collector,
        config.tenant_id,
        "field_worker",
        provider_identifier,
        _safe_text(attendance.get("name"), maximum=160) or "Field worker",
    )
    start_time = _safe_text(attendance.get("startTime"), maximum=32)
    collector.add("trackwick_worker_days", {
        "id": _private_id("worker-day", config.tenant_id, provider_identifier, observed_at[:10]),
        "field_worker_party_id": party_id,
        "observed_on": observed_at[:10],
        "attendance_status": "present" if start_time else "not_punched",
        "reported_start_time": start_time,
        "reported_total_time": _safe_text(attendance.get("totalTime"), maximum=32),
    })
    return True


def _normalise_customer(
    customer: Mapping[str, Any], config: TrackwickApiConfig, fallback_time: datetime
) -> Optional[TrackolapRecord]:
    """Admit the minimum identity needed to recognise a Fortune farmer.

    A TrackWick customer can carry mobile and exact geo.  Neither is accessed
    here; this function is the privacy boundary for the farmer CRM feed.
    """
    farmer_id = _opaque(customer.get("iden")) or _opaque(customer.get("id"))
    display_name = _safe_text(customer.get("name"), maximum=160)
    source_time = _timestamp(customer.get("createdOn"), fallback_time.tzinfo)
    if farmer_id is None or display_name is None or source_time is None:
        return None
    owner_id = _opaque(customer.get("owner")) or "unassigned"
    return _record(
        "farmer_profiles",
        "farmer:" + farmer_id,
        source_time.isoformat(),
        config.tenant_id,
        {
            "farmer_id": farmer_id,
            "display_name": display_name,
            "crm_status": _safe_status(customer.get("status"), "unknown"),
            "territory_owner_id": owner_id,
            "registered_at": source_time.isoformat(),
        },
    )


def _normalise_task_basics(
    task: Mapping[str, Any], config: TrackwickApiConfig, fallback_time: datetime
) -> Optional[tuple[TrackolapRecord, ...]]:
    task_id = _opaque(task.get("id"))
    source_time = _task_time(task, fallback_time)
    if task_id is None or source_time is None:
        return None
    task_type = _safe_text(task.get("type"), maximum=120)
    if task_type is None:
        return tuple()
    status = _safe_status(task.get("status"), "unknown")
    form = task.get("formDetails")
    form_details = form if isinstance(form, Mapping) else {}
    records: list[TrackolapRecord] = []

    worker = _normalise_field_worker(task, source_time, config.tenant_id, status)
    if worker is not None:
        records.append(worker)

    type_key = task_type.casefold()
    if type_key == "new farmer registration":
        farm = _normalise_farm_candidate(
            task_id, task, form_details, source_time, config.tenant_id, status
        )
        if farm is not None:
            records.append(farm)
    if type_key == config.form_title.casefold():
        crop = _normalise_crop_context(
            task_id, task, form_details, source_time, config.tenant_id, status
        )
        if crop is not None:
            records.append(crop)
    if type_key in _SOIL_TASK_TYPES:
        soil = _normalise_soil_context(task_id, task, source_time, config.tenant_id, status)
        if soil is not None:
            records.append(soil)
    if status != "completed":
        follow_up = _normalise_follow_up(
            task_id, task, task_type, source_time, config.tenant_id, status
        )
        if follow_up is not None:
            records.append(follow_up)
    return tuple(records)


def _normalise_field_worker(
    task: Mapping[str, Any], source_time: str, tenant_id: str, status: str
) -> Optional[TrackolapRecord]:
    worker_id = _opaque(task.get("employeeIden"))
    if worker_id is None:
        return None
    display_name = _safe_text(task.get("assignedTo"), maximum=160) or "Field worker"
    return _record(
        "field_workers",
        "field-worker:" + worker_id + ":" + source_time,
        source_time,
        tenant_id,
        {
            "worker_id": worker_id,
            "display_name": display_name,
            "last_activity_at": source_time,
            "activity_status": status,
        },
    )


def _normalise_farm_candidate(
    task_id: str,
    task: Mapping[str, Any],
    form: Mapping[str, Any],
    source_time: str,
    tenant_id: str,
    status: str,
) -> Optional[TrackolapRecord]:
    farmer_id = _farmer_code(task)
    if farmer_id is None:
        return None
    values = {
        "farm_candidate_id": task_id,
        "farmer_id": farmer_id,
        "village": _safe_text(form.get(_REGISTRATION_FORM_KEYS["village"]), maximum=120) or "not_reported",
        "block": _safe_text(form.get(_REGISTRATION_FORM_KEYS["block"]), maximum=120) or "not_reported",
        "district": _safe_text(form.get(_REGISTRATION_FORM_KEYS["district"]), maximum=120) or "not_reported",
        "reported_area_acres": _safe_decimal(form.get(_REGISTRATION_FORM_KEYS["area_acres"])) or "not_reported",
        "reported_plot_count": _safe_whole_number(form.get(_REGISTRATION_FORM_KEYS["plot_count"])) or "not_reported",
        "pb1_area_acres": _safe_decimal(form.get(_REGISTRATION_FORM_KEYS["pb1_area_acres"])) or "not_reported",
        "var1718_area_acres": _safe_decimal(form.get(_REGISTRATION_FORM_KEYS["var1718_area_acres"])) or "not_reported",
        "registration_status": status,
    }
    return _record("farm_candidates", "farm-candidate:" + task_id, source_time, tenant_id, values)


def _normalise_crop_context(
    task_id: str,
    task: Mapping[str, Any],
    form: Mapping[str, Any],
    source_time: str,
    tenant_id: str,
    status: str,
) -> Optional[TrackolapRecord]:
    farmer_id = _farmer_code(task)
    if farmer_id is None:
        return None
    values = {
        "crop_context_id": task_id,
        "farmer_id": farmer_id,
        "visit_status": status,
        "transplanted_on": _safe_date(form.get(_VISIT_BASIC_FORM_KEYS["transplanted_at"])) or "not_reported",
        "crop_stage": _safe_text(form.get(_VISIT_BASIC_FORM_KEYS["crop_stage"]), maximum=120) or "not_reported",
        "water_condition": _safe_text(form.get(_VISIT_BASIC_FORM_KEYS["water_condition"]), maximum=120) or "not_reported",
        "crop_condition_score": _safe_decimal(form.get(_VISIT_BASIC_FORM_KEYS["crop_condition"])) or "not_reported",
        "kit_status": _kit_status(form.get(_FORM_KEYS["kit_taken"])),
    }
    return _record("crop_context", "crop-context:" + task_id, source_time, tenant_id, values)


def _normalise_soil_context(
    task_id: str,
    task: Mapping[str, Any],
    source_time: str,
    tenant_id: str,
    status: str,
) -> Optional[TrackolapRecord]:
    farmer_id = _farmer_code(task)
    if farmer_id is None:
        return None
    return _record(
        "soil_context",
        "soil-context:" + task_id,
        source_time,
        tenant_id,
        {"soil_context_id": task_id, "farmer_id": farmer_id, "task_status": status},
    )


def _normalise_follow_up(
    task_id: str,
    task: Mapping[str, Any],
    task_type: str,
    source_time: str,
    tenant_id: str,
    status: str,
) -> Optional[TrackolapRecord]:
    worker_id = _opaque(task.get("employeeIden")) or "unassigned"
    farmer_id = _farmer_code(task) or "unassigned"
    return _record(
        "follow_ups",
        "follow-up:" + task_id,
        source_time,
        tenant_id,
        {
            "follow_up_id": task_id,
            "farmer_id": farmer_id,
            "worker_id": worker_id,
            "task_type": _safe_status(task_type, "other"),
            "task_status": status,
            "reported_at": source_time,
        },
    )


def _headers(customer_id: str, api_key: str) -> dict[str, str]:
    return {
        "platform": "API",
        "tlp-cid": customer_id,
        "tlp-t": str(int(clock.time() * 1000)),
        "api-key": api_key,
    }


def _epoch_milliseconds(value: datetime, timezone_name: str) -> int:
    """Format the provider's verified creation-window parameter precisely."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo(timezone_name))
    return int(value.astimezone(timezone.utc).timestamp() * 1000)


def _get(client: httpx.Client, path: str, headers: Mapping[str, str], params: Mapping[str, Any]) -> httpx.Response:
    try:
        response = client.get(BASE_URL + path, headers=dict(headers), params=dict(params))
    except httpx.RequestError as error:
        raise TrackwickSourceFailure("network_error") from error
    if response.status_code < 200 or response.status_code >= 300:
        raise TrackwickSourceFailure("http_status")
    return response


def _rows(response: httpx.Response, error_code: str) -> tuple[list[Mapping[str, Any]], bool]:
    try:
        payload = response.json()
    except ValueError as error:
        raise TrackwickSourceFailure("invalid_json") from error
    if not isinstance(payload, Mapping) or payload.get("s") is not True:
        raise TrackwickSourceFailure(error_code)
    rows = payload.get("data")
    if not isinstance(rows, list) or not all(isinstance(row, Mapping) for row in rows):
        raise TrackwickSourceFailure(error_code)
    has_more = payload.get("hm", False)
    if not isinstance(has_more, bool):
        raise TrackwickSourceFailure(error_code)
    return [dict(row) for row in rows], has_more


def _normalise_task(
    task: Mapping[str, Any], config: TrackwickApiConfig, fallback_time: datetime
) -> Optional[tuple[TrackolapRecord, ...]]:
    if str(task.get("type", "")).strip().casefold() != config.form_title.casefold():
        return tuple()
    task_id = _opaque(task.get("id"))
    farmer_code = _farmer_code(task)
    source_time = _task_time(task, fallback_time)
    if task_id is None or farmer_code is None or source_time is None:
        return None
    form = task.get("formDetails")
    form_details = form if isinstance(form, Mapping) else {}
    status = _safe_status(task.get("status"), "unknown")
    values = {
        "task_id": task_id,
        "farmer_code": farmer_code,
        "territory_owner_id": "unassigned",
        "village_key": _village_key(form_details.get(_FORM_KEYS["location"])),
        "task_status": status,
        "kit_status": _kit_status(form_details.get(_FORM_KEYS["kit_taken"])),
    }
    records = [_record("farmer_tasks", "task:" + task_id, source_time, config.tenant_id, values)]
    if status != "completed":
        return tuple(records)

    filing_officer = _opaque(task.get("employeeIden")) or "unassigned"
    visit_values = {
        "visit_id": task_id,
        "task_id": task_id,
        "filing_officer_id": filing_officer,
        "performed_at": source_time,
        "submitted_at": source_time,
        "visit_status": "completed",
    }
    records.append(_record("visits", "visit:" + task_id, source_time, config.tenant_id, visit_values))
    severity = _severity(form_details.get(config.severity_form_key)) if config.severity_form_key else "unknown"
    records.extend(_issue_records(task_id, source_time, config.tenant_id, form_details, severity))
    records.extend(_pesticide_records(task_id, source_time, config.tenant_id, form_details))
    return tuple(records)


def _normalise_attendance(
    attendance: Mapping[str, Any], config: TrackwickApiConfig, fallback_time: datetime
) -> Optional[tuple[TrackolapRecord, ...]]:
    officer_id = _opaque(attendance.get("empId"))
    observed_at = _date_time(attendance.get("date"), fallback_time, config.reporting_timezone)
    if officer_id is None or observed_at is None:
        return None
    present = bool(str(attendance.get("startTime", "")).strip())
    attendance_id = "attendance:" + officer_id + ":" + observed_at[:10]
    status = "present" if present else "not_punched"
    officer = _record(
        "officers",
        "officer:" + officer_id + ":" + observed_at[:10],
        observed_at,
        config.tenant_id,
        {
            "officer_id": officer_id,
            "display_name": "Field worker",
            "role": "field_worker",
            "active_status": "active" if present else "inactive",
            "territory_owner_id": "unassigned",
            "effective_from": observed_at,
        },
    )
    attendance_record = _record(
        "attendance",
        attendance_id,
        observed_at,
        config.tenant_id,
        {"attendance_id": attendance_id, "officer_id": officer_id, "punch_status": status, "observed_at": observed_at},
    )
    return officer, attendance_record


def _issue_records(
    task_id: str, observed_at: str, tenant_id: str, form: Mapping[str, Any], severity: str = "unknown"
) -> list[TrackolapRecord]:
    records: list[TrackolapRecord] = []
    for issue_type in ("disease", "other_disease", "pest", "other_pest"):
        for answer in _answers(form.get(_FORM_KEYS[issue_type])):
            issue_code = _value_code(answer)
            if issue_code is None:
                continue
            source_id = "issue:" + task_id + ":" + issue_type + ":" + issue_code
            records.append(_record(
                "issue_observations",
                source_id,
                observed_at,
                tenant_id,
                {
                    "observation_id": source_id,
                    "visit_id": task_id,
                    "task_id": task_id,
                    "issue_code": issue_code,
                    "severity": severity,
                    "observed_at": observed_at,
                },
            ))
    return records


def _pesticide_records(
    task_id: str, observed_at: str, tenant_id: str, form: Mapping[str, Any]
) -> list[TrackolapRecord]:
    records: list[TrackolapRecord] = []
    for field, kind in (
        ("pesticide_used", "applied"),
        ("other_pesticide", "applied"),
        ("pesticide_recommended", "recommended"),
    ):
        for answer in _answers(form.get(_FORM_KEYS[field])):
            product_code = _value_code(answer)
            if product_code is None:
                continue
            source_id = "pesticide:" + task_id + ":" + kind + ":" + product_code
            records.append(_record(
                "pesticide_events",
                source_id,
                observed_at,
                tenant_id,
                {
                    "event_id": source_id,
                    "task_id": task_id,
                    "product_code": product_code,
                    "event_kind": kind,
                    "occurred_at": observed_at,
                    "kit_version": "unknown",
                },
            ))
    return records


def _add_private_party(
    collector: _PrivateEvidenceCollector,
    tenant_id: str,
    party_kind: str,
    provider_identifier: str,
    display_name: str,
    *,
    crm_status: Optional[str] = None,
    provider_owner_identifier: Optional[str] = None,
    provider_tag: Optional[str] = None,
    provider_created_at: Optional[str] = None,
) -> str:
    party_id = _private_id("party", tenant_id, party_kind, provider_identifier)
    collector.add("trackwick_parties", {
        "id": party_id,
        "party_kind": party_kind,
        "provider_identifier": provider_identifier,
        "display_name": display_name,
        "crm_status": crm_status,
        "provider_owner_identifier": provider_owner_identifier,
        "provider_tag": provider_tag,
        "provider_created_at": provider_created_at,
    })
    return party_id


def _add_private_contact(
    collector: _PrivateEvidenceCollector, tenant_id: str, party_id: str, value: Any,
) -> None:
    mobile = _private_mobile(value)
    if mobile is None:
        return
    fingerprint = hashlib.sha256(mobile.encode("utf-8")).hexdigest()
    collector.add("trackwick_contact_points", {
        "id": _private_id("contact", tenant_id, party_id, fingerprint),
        "party_id": party_id,
        "contact_kind": "mobile",
        "contact_value": mobile,
        "value_fingerprint": fingerprint,
        "consent_status": "unknown",
    })


def _add_private_location(
    collector: _PrivateEvidenceCollector,
    tenant_id: str,
    *,
    provider_location_key: str,
    location_kind: str,
    location: Any,
    observed_at: str,
    party_id: Optional[str] = None,
    task_id: Optional[str] = None,
    registration_id: Optional[str] = None,
    media_reference_id: Optional[str] = None,
    accuracy: Optional[float] = None,
) -> None:
    parsed = _private_location(location)
    if parsed is None:
        return
    latitude, longitude, provider_address, provider_geo_address, provider_accuracy = parsed
    collector.add("trackwick_location_observations", {
        "id": _private_id("location", tenant_id, provider_location_key),
        "party_id": party_id,
        "task_id": task_id,
        "registration_id": registration_id,
        "media_reference_id": media_reference_id,
        "provider_location_key": provider_location_key,
        "location_kind": location_kind,
        "location_confidence": "observed" if location_kind in {"task_completion", "visit_location", "media_capture"} else "declared",
        "latitude": latitude,
        "longitude": longitude,
        "provider_address": provider_address,
        "provider_geo_address": provider_geo_address,
        "provider_accuracy_m": accuracy if accuracy is not None else provider_accuracy,
        "observed_at": observed_at,
    })


def _add_private_media(
    collector: _PrivateEvidenceCollector,
    config: TrackwickApiConfig,
    task_id: str,
    provider_task_id: str,
    media_kind: str,
    raw_value: Any,
    observed_at: str,
) -> None:
    for item in _private_media_items(raw_value):
        url = _safe_remote_trackwick_url(item.get("url"))
        if url is None:
            continue
        provider_media_key = ":".join((provider_task_id, media_kind, hashlib.sha256(url.encode("utf-8")).hexdigest()))
        media_id = _private_id("media", config.tenant_id, provider_media_key)
        created_at = _timestamp_iso(item.get("createdOn"), _timestamp_from_iso(observed_at)) or observed_at
        collector.add("trackwick_media_references", {
            "id": media_id,
            "task_id": task_id,
            "provider_media_key": provider_media_key,
            "media_kind": media_kind,
            "remote_url": url,
            "provider_created_at": created_at,
            "source_access_state": "available",
            "content_state": "remote_only",
            "exif_state": "not_checked",
            "content_hash": None,
            "content_type": None,
            "size_bytes": None,
        })
        _add_private_location(
            collector,
            config.tenant_id,
            provider_location_key="media:" + provider_media_key,
            location_kind="media_capture",
            location=item.get("geo"),
            observed_at=created_at,
            task_id=task_id,
            media_reference_id=media_id,
        )


def _private_media_items(value: Any) -> tuple[Mapping[str, Any], ...]:
    if isinstance(value, Mapping):
        return (value,)
    if isinstance(value, list):
        return tuple(item for item in value if isinstance(item, Mapping))
    return ()


def _safe_remote_trackwick_url(value: Any) -> Optional[str]:
    url = _safe_text(value, maximum=2000)
    if url is None:
        return None
    parsed = urlparse(url)
    try:
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or parsed.hostname != _TRACKWICK_MEDIA_HOST
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
        or not parsed.path.startswith("/")
    ):
        return None
    # The private database constraint permits exactly this origin.  TrackWick
    # occasionally spells the same HTTPS authority with an explicit default
    # port or different host casing; canonicalising only those equivalent
    # forms keeps the signed S3 path/query usable without broadening the
    # remote-media allow-list.
    return urlunparse(("https", _TRACKWICK_MEDIA_HOST, parsed.path, parsed.params, parsed.query, ""))


def _private_location(value: Any) -> Optional[tuple[float, float, Optional[str], Optional[str], Optional[float]]]:
    if not isinstance(value, Mapping):
        return None
    latitude = _safe_coordinate(value.get("lat"), lower=-90, upper=90)
    longitude = _safe_coordinate(value.get("lng"), lower=-180, upper=180)
    if latitude is None or longitude is None:
        return None
    # TrackWick's inGeoDetail can contain a more detailed provider payload.  It
    # is deliberately not part of the private contract; the two explicit
    # address labels are enough for reviewed manager use.
    return (
        latitude,
        longitude,
        _safe_text(value.get("address"), maximum=320),
        _safe_text(value.get("geoAddress"), maximum=320),
        _safe_nonnegative_number(value.get("accuracy")),
    )


def _private_id(kind: str, tenant_id: str, *parts: object) -> str:
    canonical = "\x1f".join((kind, tenant_id, *(str(part) for part in parts)))
    return "tw:" + kind + ":" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def _private_mobile(value: Any) -> Optional[str]:
    candidate = _safe_text(value, maximum=32)
    if candidate is None:
        return None
    digits = re.sub(r"[^0-9]", "", candidate)
    if not 7 <= len(digits) <= 15:
        return None
    return digits


def _private_status(value: Any) -> str:
    candidate = _safe_status(value, "unknown")
    return candidate if candidate in {"completed", "in_progress", "pending"} else "unknown"


def _task_customer_display_name(task: Mapping[str, Any]) -> Optional[str]:
    return _safe_text(task.get("customerName"), maximum=160)


def _timestamp_iso(value: Any, fallback_time: datetime) -> Optional[str]:
    parsed = _timestamp(value, fallback_time.tzinfo)
    return parsed.isoformat() if parsed is not None else None


def _timestamp_from_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _safe_coordinate(value: Any, *, lower: float, upper: float) -> Optional[float]:
    number = _safe_number(value)
    if number is None or not lower <= number <= upper:
        return None
    return round(number, 6)


def _safe_number(value: Any) -> Optional[float]:
    candidate = _safe_text(value, maximum=32)
    if candidate is None:
        return None
    try:
        parsed = float(candidate)
    except ValueError:
        return None
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        return None
    return parsed


def _safe_nonnegative_number(value: Any) -> Optional[float]:
    parsed = _safe_number(value)
    return parsed if parsed is not None and parsed >= 0 else None


def _safe_integer(value: Any) -> Optional[int]:
    candidate = _safe_whole_number(value)
    return int(candidate) if candidate is not None else None


def _safe_score(value: Any) -> Optional[float]:
    score = _safe_number(value)
    return score if score is not None and 1 <= score <= 10 else None


def _record(feed: str, source_id: str, source_updated_at: str, tenant_id: str, values: Mapping[str, str]) -> TrackolapRecord:
    return TrackolapRecord(
        feed=feed,
        source_id=source_id,
        source_updated_at=source_updated_at,
        tenant_id=tenant_id,
        values=MappingProxyType(dict(values)),
    )


def _task_time(task: Mapping[str, Any], fallback_time: datetime) -> Optional[str]:
    for value in (task.get("completed"), task.get("created"), task.get("started")):
        parsed = _timestamp(value, fallback_time.tzinfo)
        if parsed is not None:
            return parsed.isoformat()
    return None


def _date_time(value: Any, fallback_time: datetime, timezone_name: str) -> Optional[str]:
    if not isinstance(value, str):
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return datetime.combine(parsed, time.min, tzinfo=ZoneInfo(timezone_name)).isoformat()


def _timestamp(value: Any, tzinfo: Optional[timezone]) -> Optional[datetime]:
    if isinstance(value, bool) or value is None or value == "":
        return None
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.strip().isdigit()):
        milliseconds = float(value)
        if milliseconds <= 0:
            return None
        try:
            return datetime.fromtimestamp(milliseconds / 1000, tz=timezone.utc).astimezone(tzinfo)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(tzinfo)
    return None


def _safe_text(value: Any, maximum: int) -> Optional[str]:
    """Accept a compact scalar, never a provider object or free-text payload."""
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return None
    candidate = re.sub(r"\s+", " ", str(value).strip())
    if not candidate or len(candidate) > maximum or any(character in candidate for character in "\r\n\x00"):
        return None
    return candidate


def _safe_decimal(value: Any) -> Optional[str]:
    candidate = _safe_text(value, maximum=32)
    if candidate is None or re.fullmatch(r"(?:0|[1-9]\d*)(?:\.\d{1,4})?", candidate) is None:
        return None
    return candidate


def _safe_whole_number(value: Any) -> Optional[str]:
    candidate = _safe_text(value, maximum=16)
    if candidate is None or re.fullmatch(r"(?:0|[1-9]\d{0,5})", candidate) is None:
        return None
    return candidate


def _safe_date(value: Any) -> Optional[str]:
    candidate = _safe_text(value, maximum=32)
    if candidate is None:
        return None
    for pattern in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(candidate, pattern).date().isoformat()
        except ValueError:
            continue
    return None


def _safe_status(value: Any, fallback: str) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return fallback
    return re.sub(r"[^a-z0-9]+", "_", raw).strip("_")[:64] or fallback


def _kit_status(value: Any) -> str:
    answers = _answers(value)
    if not answers:
        return "unknown"
    return "taken" if any(answer.casefold() in {"yes", "taken", "received", "हाँ", "हां"} for answer in answers) else "not_taken"


def _severity(value: Any) -> str:
    """Accept only an explicit, configured severity field from the visit form."""
    labels = {
        "low": "low", "moderate": "moderate", "medium": "moderate", "high": "high", "critical": "critical",
        "कम": "low", "मध्यम": "moderate", "उच्च": "high", "गंभीर": "critical", "अति गंभीर": "critical",
    }
    values = {labels.get(answer.casefold(), "unknown") for answer in _answers(value)}
    known = values - {"unknown"}
    return known.pop() if len(known) == 1 else "unknown"


def _village_key(value: Any) -> str:
    answers = _answers(value)
    if not answers:
        return "not_reported"
    candidate = re.sub(r"\s+", " ", answers[0].strip())
    return candidate[:128] if candidate else "not_reported"


def _answers(value: Any) -> list[str]:
    values: Sequence[Any]
    if isinstance(value, list):
        values = value
    else:
        values = (value,)
    answers: list[str] = []
    for item in values:
        if not isinstance(item, (str, int, float)) or isinstance(item, bool):
            continue
        answer = str(item).strip()
        if answer and answer.casefold() not in _EMPTY_ANSWER and len(answer) <= 256 and not any(character in answer for character in "\r\n\x00"):
            answers.append(answer)
    return answers


def _value_code(value: str) -> Optional[str]:
    ascii_value = value.encode("ascii", "ignore").decode("ascii").lower()
    cleaned = re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")
    if cleaned:
        return cleaned[:96]
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return "reported-" + digest


def _opaque(value: Any) -> Optional[str]:
    candidate = str(value or "").strip()
    return candidate if _OPAQUE_ID.fullmatch(candidate) else None


def _farmer_code(task: Mapping[str, Any]) -> Optional[str]:
    """Read a provider ID without retaining the provider's farmer name.

    TrackWick normally supplies ``customerIden``.  The supplied Fortune task
    sample also shows an older shape: ``FC-01734 (GAJENDRA SINGH)`` in
    ``customerName``.  When the explicit identifier is absent, retain only the
    leading opaque code immediately followed by ``(``; a name by itself never
    becomes an identity or a source record.
    """
    direct = _opaque(task.get("customerIden"))
    if direct is not None:
        return direct
    value = task.get("customerName")
    if not isinstance(value, str):
        return None
    match = _CUSTOMER_NAME_CODE.match(value)
    return match.group(1) if match is not None else None


def _required_opaque(value: Optional[str], name: str) -> str:
    candidate = _opaque(value)
    if candidate is None:
        raise TrackwickConfigurationError(name + " is required and must be an opaque identifier")
    return candidate


def _optional_form_key(value: Optional[str], setting_name: str) -> Optional[str]:
    if value is None or not value.strip():
        return None
    candidate = value.strip()
    if len(candidate) > 256 or any(character in candidate for character in "\r\n\x00"):
        raise TrackwickConfigurationError(setting_name + " is invalid")
    return candidate


def _bounded_int(value: Optional[str], default: int, lower: int, upper: int) -> int:
    if value is None or str(value).strip() == "":
        return default
    try:
        parsed = int(str(value))
    except ValueError as error:
        raise TrackwickConfigurationError("TrackWick pagination setting must be an integer") from error
    if not lower <= parsed <= upper:
        raise TrackwickConfigurationError("TrackWick pagination setting is outside the approved bound")
    return parsed
