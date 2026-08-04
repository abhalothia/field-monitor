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
from zoneinfo import ZoneInfo

import httpx

from .contracts import TrackolapRecord


BASE_URL = "https://app.trackolap.com"
TASK_LIST_PATH = "/cust/1/api/task/list"
PRODUCTIVITY_PATH = "/cust/1/api/asset/productivity"
DEFAULT_FORM_TITLE = "Farmer Visit"
DEFAULT_TIMEZONE = "Asia/Kolkata"
MAPPING_VERSION = "trackwick-task-v2"

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
}


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
        severity_form_key = _optional_form_key(values.get("FFL_TRACKWICK_SEVERITY_FORM_KEY"))
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
        )


@dataclass(frozen=True)
class TrackwickFetchResult:
    tasks: tuple[Mapping[str, Any], ...]
    attendance: tuple[Mapping[str, Any], ...]
    task_pages: int

    @property
    def rows_received(self) -> int:
        return len(self.tasks) + len(self.attendance)


@dataclass(frozen=True)
class TrackwickNormalisationResult:
    records: tuple[TrackolapRecord, ...]
    quarantined_rows: int


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
            "form-type": "CUSTOMER",
            "form-title": config.form_title,
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

            attendance_response = _get(
                client,
                PRODUCTIVITY_PATH,
                headers,
                {"date": now.date().isoformat()},
            )
            attendance, _unused_has_more = _rows(attendance_response, "attendance_response_invalid")
        return TrackwickFetchResult(tuple(tasks), tuple(attendance), page + 1)


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


def _optional_form_key(value: Optional[str]) -> Optional[str]:
    if value is None or not value.strip():
        return None
    candidate = value.strip()
    if len(candidate) > 256 or any(character in candidate for character in "\r\n\x00"):
        raise TrackwickConfigurationError("FFL_TRACKWICK_SEVERITY_FORM_KEY is invalid")
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
