"""Trusted external-context source registry and refresh boundary.

This module deliberately keeps public weather/market context outside the farm
operating record.  A provider result is normalised into attributable regional
signals, while the original provider payload is neither retained nor exposed
through the manager status API.  The default adapter registry is empty: a
source refresh therefore records an explicit ``unavailable`` run until an
operator deliberately installs a reviewed provider adapter and runtime access.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import math
import os
import re
import sqlite3
from typing import Any, Callable, Dict, Iterable, List, Optional, Protocol, Sequence, Tuple
from urllib.parse import urlparse

from ffl.domain.models import SourceRegistry, SourceRun
from ffl.persistence import repository


_SOURCE_KEY_PATTERN = re.compile(r"[a-z][a-z0-9-]{2,63}")
_CREDENTIAL_REFERENCE_PATTERN = re.compile(r"(?:env|secret)://[A-Za-z0-9][A-Za-z0-9._/-]*")
_ENV_CREDENTIAL_REFERENCE_PATTERN = re.compile(r"env://([A-Z][A-Z0-9_]*)")
_SAFE_REASON_CODE_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,63}")
_SAFE_AUTHORITY_LEVELS = {"official", "first_party", "partner", "internal"}
_PROHIBITED_DATA_CLASSES = {"personal_data", "precise_location", "raw_payload"}
_PROHIBITED_COVERAGE_KEYS = {"latitude", "longitude", "coordinates", "geometry", "gps"}
_SIGNAL_KINDS = {
    "observation", "forecast", "human_assessment", "model_inference", "aggregate_statistic",
}


# These are discovery/onboarding candidates, not pre-enabled sources.  IMD's
# official API page explicitly directs users to API documentation and IP
# whitelisting; AGMARKNET's official material establishes its market-price
# role, but this product has not verified an approved programmatic feed yet.
INDIA_SOURCE_CANDIDATES = (
    {
        "source_key": "imd-weather",
        "display_name": "India Meteorological Department weather and warnings",
        "authority_level": "official",
        "purpose": "regional weather context",
        "documentation_url": "https://mausam.imd.gov.in/responsive/apis.php",
        "onboarding_status": "access_review_and_ip_whitelisting_required",
        "allowed_data_classes": ("forecast", "warning", "observation"),
    },
    {
        "source_key": "agmarknet-market-context",
        "display_name": "AGMARKNET mandi arrivals and market-price context",
        "authority_level": "official",
        "purpose": "regional market context",
        "documentation_url": "https://agmarknet.gov.in/doc/Final%20_RFP_Agmarknet_2.0_v0.8.pdf",
        "onboarding_status": "programmatic_access_unverified",
        "allowed_data_classes": ("market_price", "arrival"),
    },
)


class SourceUnavailable(RuntimeError):
    """A deliberate non-fetch outcome with a safe, manager-visible reason."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class SourceFailure(RuntimeError):
    """A provider attempted a refresh but did not return a usable result."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class RegionalSignalInput:
    """A normalised fact supplied by a reviewed adapter, never a raw payload."""

    source_identifier: str
    region: str
    signal_type: str
    observed_at: str
    value: Any
    signal_kind: str
    coverage: Optional[Dict[str, Any]] = None
    source_url: Optional[str] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    resolution: Optional[str] = None
    freshness_target_hours: Optional[float] = None
    status: str = "available"


@dataclass(frozen=True)
class AdapterRefreshResult:
    signals: Tuple[RegionalSignalInput, ...]
    rows_received: int
    cursor: Optional[str] = None
    coverage: Optional[Dict[str, Any]] = None


class SourceAdapter(Protocol):
    """Small adapter port; source-specific parsing lives outside the kernel."""

    source_type: str
    requires_endpoint: bool
    requires_credentials: bool

    def fetch(
        self, source: SourceRegistry, credential: Optional[str], now: datetime
    ) -> AdapterRefreshResult:
        ...


class AdapterRegistry:
    """Explicit adapter registration prevents a source row from enabling I/O."""

    def __init__(self, adapters: Sequence[SourceAdapter] = ()):
        self._adapters = {adapter.source_type: adapter for adapter in adapters}

    def get(self, source_type: str) -> Optional[SourceAdapter]:
        return self._adapters.get(source_type)


class TrustedHttpJsonAdapter:
    """Opt-in HTTP JSON adapter for a reviewed, allow-listed provider.

    It is intentionally not placed in the default registry.  Production must
    explicitly supply the allowed host(s), a source-specific normaliser, and
    ``allow_network=True``; otherwise refresh reports ``runtime_fetch_disabled``.
    Credentials are supplied only at runtime and never stored in FFL records.
    """

    source_type = "trusted_http_json"
    requires_endpoint = True

    def __init__(
        self,
        allowed_hosts: Iterable[str],
        normalise: Callable[[Any, SourceRegistry], Iterable[RegionalSignalInput]],
        credential_header: Optional[str] = None,
        requires_credentials: bool = False,
        allow_network: bool = False,
        timeout_seconds: float = 10.0,
    ):
        self._allowed_hosts = {host.lower() for host in allowed_hosts}
        self._normalise = normalise
        self._credential_header = credential_header
        self.requires_credentials = requires_credentials
        self._allow_network = allow_network
        self._timeout_seconds = timeout_seconds

    def fetch(
        self, source: SourceRegistry, credential: Optional[str], now: datetime
    ) -> AdapterRefreshResult:
        endpoint = _trusted_endpoint(source.endpoint, self._allowed_hosts)
        if not self._allow_network:
            raise SourceUnavailable("runtime_fetch_disabled")
        if self.requires_credentials and not credential:
            raise SourceUnavailable("credentials_unavailable")

        # Import here so test runs and a no-op deployment never require a
        # network client.  The response body remains in memory only.
        import httpx

        headers = {"Accept": "application/json"}
        if credential and self._credential_header:
            headers[self._credential_header] = credential
        try:
            with httpx.Client(timeout=self._timeout_seconds, follow_redirects=False) as client:
                response = client.get(endpoint, headers=headers)
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError as exc:
            raise SourceFailure("provider_request_failed") from exc
        except ValueError as exc:
            raise SourceFailure("provider_invalid_json") from exc

        signals = tuple(self._normalise(payload, source))
        return AdapterRefreshResult(signals=signals, rows_received=len(signals), coverage=source.default_coverage)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _require_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("{0} is required".format(field_name))
    return value.strip()


def _parse_time(value: str, field_name: str) -> datetime:
    _require_text(value, field_name)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("{0} must be an ISO-8601 timestamp".format(field_name)) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _safe_coverage(value: Any, field_name: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("{0} must be an object".format(field_name))
    prohibited = {str(key).lower() for key in value}.intersection(_PROHIBITED_COVERAGE_KEYS)
    if prohibited:
        raise ValueError("{0} must not contain precise coordinates".format(field_name))
    return value


def _safe_endpoint(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    endpoint = _require_text(value, "endpoint")
    parsed = urlparse(endpoint)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("endpoint must be an HTTPS URL without credentials, query, or fragment")
    return endpoint


def _trusted_endpoint(endpoint: Optional[str], allowed_hosts: Iterable[str]) -> str:
    validated = _safe_endpoint(endpoint)
    if validated is None:
        raise SourceUnavailable("endpoint_unavailable")
    hostname = (urlparse(validated).hostname or "").lower()
    if hostname not in set(allowed_hosts):
        raise SourceUnavailable("endpoint_not_allowlisted")
    return validated


def _source_fields(source: SourceRegistry) -> Dict[str, Any]:
    """Fields compared for idempotent registration; credentials remain opaque."""
    return {
        "display_name": source.display_name,
        "source_type": source.source_type,
        "purpose": source.purpose,
        "authority_level": source.authority_level,
        "owner_id": source.owner_id,
        "credentials_reference": source.credentials_reference,
        "endpoint": source.endpoint,
        "permitted_data_classes": source.permitted_data_classes,
        "freshness_target_hours": source.freshness_target_hours,
        "license_notes": source.license_notes,
        "schema_version": source.schema_version,
        "mapping_version": source.mapping_version,
        "default_coverage": source.default_coverage,
        "enabled": source.enabled,
    }


def _request_fields(
    display_name: str, source_type: str, purpose: str, authority_level: str, owner_id: str,
    permitted_data_classes: Any, schema_version: str, mapping_version: str, default_coverage: Any,
    credentials_reference: Optional[str], endpoint: Optional[str], freshness_target_hours: Optional[float],
    license_notes: Optional[str], enabled: bool,
) -> Dict[str, Any]:
    return {
        "display_name": display_name,
        "source_type": source_type,
        "purpose": purpose,
        "authority_level": authority_level,
        "owner_id": owner_id,
        "credentials_reference": credentials_reference,
        "endpoint": endpoint,
        "permitted_data_classes": permitted_data_classes,
        "freshness_target_hours": freshness_target_hours,
        "license_notes": license_notes,
        "schema_version": schema_version,
        "mapping_version": mapping_version,
        "default_coverage": default_coverage,
        "enabled": enabled,
    }


def register_source(
    conn: sqlite3.Connection, source_key: str, display_name: str, source_type: str, purpose: str,
    authority_level: str, owner_id: str, permitted_data_classes: Any, schema_version: str,
    mapping_version: str, default_coverage: Any, credentials_reference: Optional[str] = None,
    endpoint: Optional[str] = None, freshness_target_hours: Optional[float] = None,
    license_notes: Optional[str] = None, enabled: bool = False,
) -> SourceRegistry:
    """Register a reviewed source configuration without accepting secret values."""
    source_key = _require_text(source_key, "source_key")
    if _SOURCE_KEY_PATTERN.fullmatch(source_key) is None:
        raise ValueError("source_key must be lowercase kebab-case")
    display_name = _require_text(display_name, "display_name")
    source_type = _require_text(source_type, "source_type")
    purpose = _require_text(purpose, "purpose")
    authority_level = _require_text(authority_level, "authority_level")
    if authority_level not in _SAFE_AUTHORITY_LEVELS:
        raise ValueError("authority_level must be official, first_party, partner, or internal")
    _require_text(owner_id, "owner_id")
    if conn.execute("SELECT 1 FROM people WHERE id = ?", (owner_id,)).fetchone() is None:
        raise ValueError("owner_id does not exist")
    if not isinstance(permitted_data_classes, list) or not permitted_data_classes:
        raise ValueError("permitted_data_classes must be a non-empty list")
    data_classes = [_require_text(item, "permitted_data_classes entry") for item in permitted_data_classes]
    if set(data_classes).intersection(_PROHIBITED_DATA_CLASSES):
        raise ValueError("permitted_data_classes includes a prohibited data class")
    schema_version = _require_text(schema_version, "schema_version")
    mapping_version = _require_text(mapping_version, "mapping_version")
    coverage = _safe_coverage(default_coverage, "default_coverage")
    endpoint = _safe_endpoint(endpoint)
    if credentials_reference is not None and _CREDENTIAL_REFERENCE_PATTERN.fullmatch(credentials_reference) is None:
        raise ValueError("credentials_reference must be an env:// or secret:// identifier")
    if freshness_target_hours is not None:
        if (
            not isinstance(freshness_target_hours, (int, float))
            or isinstance(freshness_target_hours, bool)
            or not math.isfinite(float(freshness_target_hours))
            or freshness_target_hours < 0
        ):
            raise ValueError("freshness_target_hours must be a non-negative number")
        freshness_target_hours = float(freshness_target_hours)
    if not isinstance(enabled, bool):
        raise ValueError("enabled must be a boolean")
    if license_notes is not None:
        license_notes = _require_text(license_notes, "license_notes")

    requested = _request_fields(
        display_name, source_type, purpose, authority_level, owner_id, data_classes, schema_version,
        mapping_version, coverage, credentials_reference, endpoint, freshness_target_hours, license_notes, enabled,
    )
    existing = repository.get_source_registry_by_key(conn, source_key)
    if existing is not None:
        if _source_fields(existing) != requested:
            raise ValueError("source_key is already registered with a different configuration")
        return existing
    return repository.create_source_registry(
        conn, source_key, display_name, source_type, purpose, authority_level, owner_id, data_classes,
        schema_version, mapping_version, coverage, credentials_reference=credentials_reference,
        endpoint=endpoint, freshness_target_hours=freshness_target_hours, license_notes=license_notes,
        enabled=enabled,
    )


def _credential_for(reference: Optional[str], resolver: Optional[Callable[[str], Optional[str]]]) -> Optional[str]:
    if reference is None:
        return None
    if resolver is None:
        return None
    return resolver(reference)


def environment_credential_resolver(reference: str) -> Optional[str]:
    """Resolve only a validated env:// reference and never return it to callers."""
    match = _ENV_CREDENTIAL_REFERENCE_PATTERN.fullmatch(reference)
    if match is None:
        return None
    return os.environ.get(match.group(1))


def _validate_signal_input(signal: RegionalSignalInput, source: SourceRegistry) -> RegionalSignalInput:
    _require_text(signal.source_identifier, "source_identifier")
    _require_text(signal.region, "region")
    _require_text(signal.signal_type, "signal_type")
    _parse_time(signal.observed_at, "observed_at")
    if signal.valid_from is not None:
        _parse_time(signal.valid_from, "valid_from")
    if signal.valid_to is not None:
        _parse_time(signal.valid_to, "valid_to")
    if signal.valid_from is not None and signal.valid_to is not None:
        if _parse_time(signal.valid_to, "valid_to") < _parse_time(signal.valid_from, "valid_from"):
            raise ValueError("valid_to cannot be before valid_from")
    if signal.signal_kind not in _SIGNAL_KINDS:
        raise ValueError("signal_kind is not supported")
    if signal.status not in {"available", "stale", "unavailable", "quarantined"}:
        raise ValueError("regional signal status is not supported")
    coverage = source.default_coverage if signal.coverage is None else _safe_coverage(signal.coverage, "coverage")
    source_url = _safe_endpoint(signal.source_url) if signal.source_url else None
    if signal.freshness_target_hours is not None:
        if (
            not isinstance(signal.freshness_target_hours, (int, float))
            or isinstance(signal.freshness_target_hours, bool)
            or not math.isfinite(float(signal.freshness_target_hours))
            or signal.freshness_target_hours < 0
        ):
            raise ValueError("freshness_target_hours must be a non-negative number")
    return RegionalSignalInput(
        source_identifier=signal.source_identifier.strip(), region=signal.region.strip(),
        signal_type=signal.signal_type.strip(), observed_at=_iso(_parse_time(signal.observed_at, "observed_at")),
        value=signal.value, signal_kind=signal.signal_kind, coverage=coverage, source_url=source_url,
        valid_from=_iso(_parse_time(signal.valid_from, "valid_from")) if signal.valid_from else None,
        valid_to=_iso(_parse_time(signal.valid_to, "valid_to")) if signal.valid_to else None,
        resolution=signal.resolution, freshness_target_hours=signal.freshness_target_hours,
        status=signal.status,
    )


def _unavailable_run(
    conn: sqlite3.Connection, source: SourceRegistry, reason: str, now: datetime
) -> SourceRun:
    reason = _safe_reason_code(reason, "source_unavailable")
    return repository.create_source_run(
        conn, source.id, source.default_coverage, source.mapping_version, status="unavailable",
        fetched_at=_iso(now), error_summary=reason,
    )


def _failed_run(
    conn: sqlite3.Connection, source: SourceRegistry, now: datetime, reason: str = "provider_refresh_failed"
) -> SourceRun:
    reason = _safe_reason_code(reason, "provider_refresh_failed")
    return repository.create_source_run(
        conn, source.id, source.default_coverage, source.mapping_version, status="failed",
        fetched_at=_iso(now), error_summary=reason,
    )


def refresh_source(
    conn: sqlite3.Connection, source_key: str, adapters: Optional[AdapterRegistry] = None,
    credential_resolver: Optional[Callable[[str], Optional[str]]] = None,
    now: Optional[datetime] = None,
) -> SourceRun:
    """Run one source through an explicit adapter or record why it could not run."""
    source = repository.get_source_registry_by_key(conn, source_key)
    if source is None:
        raise LookupError("source not found")
    current_time = now or _now()
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    current_time = current_time.astimezone(timezone.utc)
    if not source.enabled:
        return _unavailable_run(conn, source, "source_disabled", current_time)

    adapter = (adapters or AdapterRegistry()).get(source.source_type)
    if adapter is None:
        return _unavailable_run(conn, source, "adapter_not_configured", current_time)
    if adapter.requires_endpoint and source.endpoint is None:
        return _unavailable_run(conn, source, "endpoint_unavailable", current_time)
    credential = _credential_for(source.credentials_reference, credential_resolver)
    if adapter.requires_credentials and not credential:
        return _unavailable_run(conn, source, "credentials_unavailable", current_time)

    try:
        result = adapter.fetch(source, credential, current_time)
        if not isinstance(result, AdapterRefreshResult):
            raise ValueError("adapter did not return AdapterRefreshResult")
        if not isinstance(result.rows_received, int) or result.rows_received < len(result.signals):
            raise ValueError("adapter rows_received cannot be smaller than normalised signals")
        if result.rows_received < 0:
            raise ValueError("adapter rows_received must be non-negative")
        coverage = source.default_coverage if result.coverage is None else _safe_coverage(result.coverage, "coverage")
        signals = tuple(_validate_signal_input(signal, source) for signal in result.signals)
    except SourceUnavailable as exc:
        return _unavailable_run(conn, source, exc.code, current_time)
    except SourceFailure as exc:
        return _failed_run(conn, source, current_time, exc.code)
    except Exception:
        # Do not store provider exception strings: they commonly echo URLs,
        # credentials, or location filters.  The durable code is enough for
        # manager health and retry triage.
        return _failed_run(conn, source, current_time)

    try:
        conn.execute("BEGIN IMMEDIATE")
        run = repository.create_source_run(
            conn, source.id, coverage, source.mapping_version, status="succeeded",
            cursor=result.cursor, fetched_at=_iso(current_time), rows_received=result.rows_received,
            rows_accepted=len(signals), commit=False,
        )
        for signal in signals:
            repository.create_regional_signal(
                conn, source.id, signal.source_identifier, signal.region, signal.signal_type,
                signal.observed_at, signal.value, signal.coverage or source.default_coverage,
                signal.signal_kind, source_run_id=run.id, source_url=signal.source_url,
                received_at=_iso(current_time), valid_from=signal.valid_from, valid_to=signal.valid_to,
                resolution=signal.resolution,
                freshness_target_hours=(
                    signal.freshness_target_hours
                    if signal.freshness_target_hours is not None
                    else source.freshness_target_hours
                ),
                status=signal.status, commit=False,
            )
        conn.commit()
        return run
    except Exception:
        conn.rollback()
        return _failed_run(conn, source, current_time)


def _coverage_dimensions(coverage: Any) -> List[str]:
    return sorted(str(key) for key in coverage) if isinstance(coverage, dict) else []


def _latest_successful_run(runs: Sequence[SourceRun]) -> Optional[SourceRun]:
    successful = [run for run in runs if run.status == "succeeded" and run.fetched_at]
    if not successful:
        return None
    return max(successful, key=lambda run: _parse_time(run.fetched_at or "", "fetched_at"))


def _freshness_state(source: SourceRegistry, runs: Sequence[SourceRun], now: datetime) -> str:
    latest = _latest_successful_run(runs)
    if latest is None:
        return "unknown"
    if source.freshness_target_hours is None:
        return "not_configured"
    age_hours = (now - _parse_time(latest.fetched_at or "", "fetched_at")).total_seconds() / 3600
    return "fresh" if age_hours <= source.freshness_target_hours else "stale"


def _health_state(source: SourceRegistry, runs: Sequence[SourceRun], now: datetime) -> str:
    if not source.enabled:
        return "disabled"
    if not runs:
        return "not_run"
    latest = runs[-1]
    if latest.status in {"failed", "unavailable", "quarantined", "pending"}:
        return latest.status
    return "stale" if _freshness_state(source, runs, now) == "stale" else "healthy"


def _run_summary(run: SourceRun) -> Dict[str, Any]:
    reason_code = _safe_reason_code(run.error_summary, "error_redacted") if run.error_summary else None
    return {
        "id": run.id,
        "status": run.status,
        "fetched_at": run.fetched_at,
        "created_at": run.created_at,
        "rows_received": run.rows_received,
        "rows_accepted": run.rows_accepted,
        "mapping_version": run.mapping_version,
        "next_retry_at": run.next_retry_at,
        "reason_code": reason_code,
        "coverage_dimensions": _coverage_dimensions(run.coverage),
    }


def _safe_reason_code(value: Optional[str], fallback: str) -> str:
    if value and _SAFE_REASON_CODE_PATTERN.fullmatch(value):
        return value
    return fallback


def source_status(
    conn: sqlite3.Connection, source: SourceRegistry, now: Optional[datetime] = None
) -> Dict[str, Any]:
    """Manager-safe source status: no endpoint, credential reference, or raw data."""
    current_time = now or _now()
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    current_time = current_time.astimezone(timezone.utc)
    runs = repository.list_source_runs(conn, source.id)
    latest = runs[-1] if runs else None
    signal_counts = conn.execute(
        "SELECT status, COUNT(*) AS count FROM regional_signals WHERE source_id = ? GROUP BY status", (source.id,)
    ).fetchall()
    return {
        "source_key": source.source_key,
        "display_name": source.display_name,
        "source_type": source.source_type,
        "purpose": source.purpose,
        "authority_level": source.authority_level,
        "enabled": source.enabled,
        "permitted_data_classes": source.permitted_data_classes,
        "freshness_target_hours": source.freshness_target_hours,
        "mapping_version": source.mapping_version,
        "schema_version": source.schema_version,
        "coverage_dimensions": _coverage_dimensions(source.default_coverage),
        "configuration": {
            "endpoint_configured": source.endpoint is not None,
            "credentials_reference_configured": source.credentials_reference is not None,
        },
        "health": _health_state(source, runs, current_time),
        "freshness": _freshness_state(source, runs, current_time),
        "latest_run": _run_summary(latest) if latest else None,
        "regional_signal_counts": {row["status"]: row["count"] for row in signal_counts},
    }


def list_source_statuses(conn: sqlite3.Connection, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    return [source_status(conn, source, now) for source in repository.list_source_registry(conn)]


def get_source_status(conn: sqlite3.Connection, source_key: str, now: Optional[datetime] = None) -> Dict[str, Any]:
    source = repository.get_source_registry_by_key(conn, source_key)
    if source is None:
        raise LookupError("source not found")
    return source_status(conn, source, now)


def list_source_run_summaries(conn: sqlite3.Connection, source_key: str) -> List[Dict[str, Any]]:
    source = repository.get_source_registry_by_key(conn, source_key)
    if source is None:
        raise LookupError("source not found")
    return [_run_summary(run) for run in repository.list_source_runs(conn, source.id)]


def india_source_candidates() -> List[Dict[str, Any]]:
    """Return capability discovery, clearly separate from an approved feed."""
    return [
        {
            **candidate,
            "allowed_data_classes": list(candidate["allowed_data_classes"]),
        }
        for candidate in INDIA_SOURCE_CANDIDATES
    ]
