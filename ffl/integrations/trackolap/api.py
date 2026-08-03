"""Configuration-bound, GET-only TrackOlap API adapter.

The adapter has no product-specific endpoint guesses.  A Fortune data owner
must supply the complete reviewed configuration and server-side token before
it can make even a single request.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
from types import MappingProxyType
from typing import Any, Callable, Mapping, Optional
from urllib.parse import urlparse

import httpx

from .contracts import FEEDS
from .mapping import MappingManifest, MappingManifestError


_PATH = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}(?:\.[A-Za-z_][A-Za-z0-9_]{0,63})*")
_HEADER = re.compile(r"[A-Za-z][A-Za-z0-9-]{0,63}")
_PARAM = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")
_REFERENCE = re.compile(r"(?:env|secret)://[A-Za-z0-9][A-Za-z0-9._/-]{0,127}")


class TrackolapConfigurationError(ValueError):
    """A live connector setting is missing, unsafe, or too vague to use."""


class SourceUnavailable(RuntimeError):
    """A safe, operator-actionable condition before network access begins."""


class SourceFailure(RuntimeError):
    """A provider or schema failure represented by a non-sensitive code."""


@dataclass(frozen=True)
class FeedEndpoint:
    path: str
    rows_path: str
    next_cursor_path: Optional[str]
    cursor_param: Optional[str]
    page_size_param: Optional[str]
    page_size: Optional[int]
    max_pages: int


@dataclass(frozen=True)
class TrackolapApiConfig:
    tenant_id: str
    base_url: str
    allowed_hosts: tuple[str, ...]
    reporting_timezone: str
    endpoints: Mapping[str, FeedEndpoint]
    read_only: bool
    token_reference: str
    project_scope: Mapping[str, str]
    mapping_manifest: MappingManifest
    auth_header: str = "Authorization"
    auth_prefix: str = "Bearer "

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "TrackolapApiConfig":
        if not isinstance(value, Mapping):
            raise TrackolapConfigurationError("TrackOlap API configuration must be an object")
        tenant_id = _required_string(value, "tenant_id")
        base_url = _validated_base_url(_required_string(value, "base_url"))
        allowed_hosts_raw = value.get("allowed_hosts")
        if not isinstance(allowed_hosts_raw, list) or not allowed_hosts_raw:
            raise TrackolapConfigurationError("allowed_hosts must name the approved HTTPS host")
        allowed_hosts = tuple(_host(host) for host in allowed_hosts_raw)
        parsed_base = urlparse(base_url)
        if parsed_base.netloc not in allowed_hosts:
            raise TrackolapConfigurationError("base_url host is not in allowed_hosts")
        if value.get("read_only") is not True:
            raise TrackolapConfigurationError("read_only must be true")
        token_reference = _required_string(value, "token_reference")
        if _REFERENCE.fullmatch(token_reference) is None:
            raise TrackolapConfigurationError("token_reference must be an env:// or secret:// reference")
        project_scope = _project_scope(value.get("project_scope"))
        try:
            manifest = MappingManifest.from_dict(value.get("mapping_manifest", {}))
            manifest.requires_all_feeds()
        except MappingManifestError as error:
            raise TrackolapConfigurationError(str(error)) from error
        endpoints = _endpoints(value.get("endpoints"))
        reporting_timezone = _required_string(value, "reporting_timezone")
        try:
            from zoneinfo import ZoneInfo

            ZoneInfo(reporting_timezone)
        except Exception as error:
            raise TrackolapConfigurationError("reporting_timezone must be an IANA timezone") from error
        auth_header = str(value.get("auth_header", "Authorization"))
        if _HEADER.fullmatch(auth_header) is None:
            raise TrackolapConfigurationError("auth_header is invalid")
        auth_prefix = str(value.get("auth_prefix", "Bearer "))
        if len(auth_prefix) > 64 or any(character in auth_prefix for character in "\r\n\x00"):
            raise TrackolapConfigurationError("auth_prefix is invalid")
        return cls(
            tenant_id=tenant_id,
            base_url=base_url,
            allowed_hosts=allowed_hosts,
            reporting_timezone=reporting_timezone,
            endpoints=MappingProxyType(endpoints),
            read_only=True,
            token_reference=token_reference,
            project_scope=MappingProxyType(project_scope),
            mapping_manifest=manifest,
            auth_header=auth_header,
            auth_prefix=auth_prefix,
        )

    @classmethod
    def from_environment(cls, environment: Optional[Mapping[str, str]] = None) -> Optional["TrackolapApiConfig"]:
        values = environment or os.environ
        if values.get("FFL_TRACKOLAP_ENABLED", "").strip().lower() != "true":
            return None
        raw = values.get("FFL_TRACKOLAP_API_CONFIG_JSON")
        if not raw:
            raise TrackolapConfigurationError("FFL_TRACKOLAP_API_CONFIG_JSON is required when enabled")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as error:
            raise TrackolapConfigurationError("FFL_TRACKOLAP_API_CONFIG_JSON must contain JSON") from error
        if not isinstance(parsed, dict):
            raise TrackolapConfigurationError("FFL_TRACKOLAP_API_CONFIG_JSON must contain an object")
        token_reference = values.get("FFL_TRACKOLAP_API_TOKEN_REFERENCE", "env://FFL_TRACKOLAP_API_TOKEN")
        if "token_reference" in parsed and parsed["token_reference"] != token_reference:
            raise TrackolapConfigurationError("token reference must be supplied by the server environment")
        parsed["token_reference"] = token_reference
        return cls.from_dict(parsed)


@dataclass(frozen=True)
class ApiRequest:
    method: str
    path: str


@dataclass(frozen=True)
class ApiFetchResult:
    feed: str
    rows: tuple[Mapping[str, Any], ...]
    cursor: Optional[str]
    rows_received: int
    requests: tuple[ApiRequest, ...]


@dataclass(frozen=True)
class LiveRefreshResult:
    status: str
    reason_code: Optional[str]
    feed_results: Mapping[str, ApiFetchResult]
    cursor: Mapping[str, Optional[str]]

    @property
    def rows_received(self) -> int:
        return sum(result.rows_received for result in self.feed_results.values())


class TrackolapApiAdapter:
    """Small GET-only client with bounded, configured cursor pagination."""

    def fetch(
        self,
        config: TrackolapApiConfig,
        token: str,
        cursor: Optional[str] = None,
        transport: Optional[httpx.BaseTransport] = None,
        feed: str = "visits",
    ) -> ApiFetchResult:
        if not config.read_only:
            raise SourceUnavailable("read_only_required")
        if not token:
            raise SourceUnavailable("credentials_unavailable")
        endpoint = config.endpoints.get(feed)
        if endpoint is None:
            raise SourceFailure("feed_endpoint_unavailable")
        request_log: list[ApiRequest] = []
        rows: list[Mapping[str, Any]] = []
        next_cursor = cursor
        last_cursor = cursor
        seen_cursors: set[str] = set()
        try:
            with httpx.Client(transport=transport, follow_redirects=False, timeout=20.0) as client:
                for _ in range(endpoint.max_pages):
                    params: dict[str, str | int] = dict(config.project_scope)
                    if endpoint.page_size_param and endpoint.page_size is not None:
                        params[endpoint.page_size_param] = endpoint.page_size
                    if endpoint.cursor_param and next_cursor:
                        if next_cursor in seen_cursors:
                            raise SourceFailure("cursor_loop_detected")
                        seen_cursors.add(next_cursor)
                        params[endpoint.cursor_param] = next_cursor
                    url = config.base_url + endpoint.path
                    response = client.get(
                        url,
                        params=params,
                        headers={config.auth_header: config.auth_prefix + token},
                    )
                    request_log.append(ApiRequest(method="GET", path=endpoint.path))
                    if response.status_code < 200 or response.status_code >= 300:
                        raise SourceFailure("http_status")
                    try:
                        payload = response.json()
                    except ValueError as error:
                        raise SourceFailure("invalid_json") from error
                    page_rows = _extract_path(payload, endpoint.rows_path, "response_rows_invalid")
                    if not isinstance(page_rows, list) or not all(isinstance(row, Mapping) for row in page_rows):
                        raise SourceFailure("response_rows_invalid")
                    rows.extend(dict(row) for row in page_rows)
                    if not endpoint.next_cursor_path:
                        break
                    candidate = _extract_path(payload, endpoint.next_cursor_path, "response_cursor_invalid")
                    if candidate is None or candidate == "":
                        break
                    if not isinstance(candidate, str) or len(candidate) > 512:
                        raise SourceFailure("response_cursor_invalid")
                    last_cursor = candidate
                    next_cursor = candidate
                else:
                    # Hitting an explicitly reviewed cap is not a schema
                    # failure. The persisted cursor permits an operator-run
                    # follow-up refresh; no implicit background loop begins.
                    pass
        except httpx.RequestError as error:
            raise SourceFailure("network_error") from error
        return ApiFetchResult(
            feed=feed,
            rows=tuple(rows),
            cursor=last_cursor,
            rows_received=len(rows),
            requests=tuple(request_log),
        )


def refresh_trackolap(
    source: Any,
    config: Optional[TrackolapApiConfig],
    credential_resolver: Callable[[str], Optional[str]],
    transport: Optional[httpx.BaseTransport] = None,
    cursor: Optional[Mapping[str, Optional[str]]] = None,
    adapter: Optional[TrackolapApiAdapter] = None,
) -> LiveRefreshResult:
    """Fetch all reviewed feeds, returning safe health codes instead of payloads."""
    if config is None:
        return LiveRefreshResult("unavailable", "configuration_unavailable", MappingProxyType({}), MappingProxyType({}))
    token = credential_resolver(config.token_reference)
    if not token:
        return LiveRefreshResult("unavailable", "credentials_unavailable", MappingProxyType({}), MappingProxyType({}))
    client = adapter or TrackolapApiAdapter()
    results: dict[str, ApiFetchResult] = {}
    next_cursors: dict[str, Optional[str]] = {}
    try:
        for feed in sorted(FEEDS):
            result = client.fetch(
                config,
                token,
                cursor=(cursor or {}).get(feed),
                transport=transport,
                feed=feed,
            )
            results[feed] = result
            next_cursors[feed] = result.cursor
    except SourceUnavailable as error:
        return LiveRefreshResult("unavailable", _safe_code(error), MappingProxyType({}), MappingProxyType({}))
    except SourceFailure as error:
        return LiveRefreshResult("failed", _safe_code(error), MappingProxyType({}), MappingProxyType({}))
    return LiveRefreshResult(
        "succeeded", None, MappingProxyType(results), MappingProxyType(next_cursors)
    )


def _endpoints(value: Any) -> dict[str, FeedEndpoint]:
    if not isinstance(value, Mapping):
        raise TrackolapConfigurationError("endpoints must define all approved feeds")
    missing = sorted(FEEDS - set(value))
    extra = sorted(set(value) - FEEDS)
    if missing or extra:
        detail = ("missing: " + ", ".join(missing)) if missing else "unknown: " + ", ".join(extra)
        raise TrackolapConfigurationError("endpoints must define only approved feeds (" + detail + ")")
    result: dict[str, FeedEndpoint] = {}
    for feed, raw in value.items():
        if not isinstance(raw, Mapping):
            raise TrackolapConfigurationError(f"endpoint for {feed} must be an object")
        if raw.get("method") != "GET":
            raise TrackolapConfigurationError(f"endpoint for {feed} must use GET")
        path = _relative_path(raw.get("path"), f"endpoint path for {feed}")
        rows_path = _response_path(raw.get("rows_path"), f"rows_path for {feed}")
        next_cursor_path = _optional_response_path(raw.get("next_cursor_path"), f"next_cursor_path for {feed}")
        cursor_param = _optional_param(raw.get("cursor_param"), f"cursor_param for {feed}")
        page_size_param = _optional_param(raw.get("page_size_param"), f"page_size_param for {feed}")
        page_size = raw.get("page_size")
        if page_size is not None and (isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= 1000):
            raise TrackolapConfigurationError(f"page_size for {feed} must be between 1 and 1000")
        max_pages = raw.get("max_pages", 100)
        if isinstance(max_pages, bool) or not isinstance(max_pages, int) or not 1 <= max_pages <= 1000:
            raise TrackolapConfigurationError(f"max_pages for {feed} must be between 1 and 1000")
        if next_cursor_path and not cursor_param:
            raise TrackolapConfigurationError(f"cursor_param is required for paginated {feed} endpoint")
        result[feed] = FeedEndpoint(
            path, rows_path, next_cursor_path, cursor_param, page_size_param, page_size, max_pages
        )
    return result


def _validated_base_url(value: str) -> str:
    parsed = urlparse(value.rstrip("/"))
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.path not in {"", "/"}
        or parsed.params
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise TrackolapConfigurationError("base_url must be an HTTPS origin without credentials or path")
    return value.rstrip("/")


def _host(value: Any) -> str:
    if not isinstance(value, str) or not value or ":" in value or "/" in value or "@" in value:
        raise TrackolapConfigurationError("allowed_hosts must contain bare host names")
    return value.lower()


def _project_scope(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping) or not value:
        raise TrackolapConfigurationError("project_scope is required")
    scope: dict[str, str] = {}
    for key, item in value.items():
        if _PARAM.fullmatch(str(key)) is None or not isinstance(item, str) or not item.strip() or len(item) > 128:
            raise TrackolapConfigurationError("project_scope must contain bounded string parameters")
        scope[str(key)] = item.strip()
    return scope


def _required_string(value: Mapping[str, Any], field: str) -> str:
    item = value.get(field)
    if not isinstance(item, str) or not item.strip():
        raise TrackolapConfigurationError(field + " is required")
    return item.strip()


def _relative_path(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.startswith("/") or "?" in value or "#" in value or "//" in value:
        raise TrackolapConfigurationError(label + " must be a relative path")
    if any(segment in {"", ".", ".."} for segment in value.split("/")[1:]):
        raise TrackolapConfigurationError(label + " is invalid")
    return value


def _response_path(value: Any, label: str) -> str:
    if not isinstance(value, str) or _PATH.fullmatch(value) is None:
        raise TrackolapConfigurationError(label + " is invalid")
    return value


def _optional_response_path(value: Any, label: str) -> Optional[str]:
    if value is None:
        return None
    return _response_path(value, label)


def _optional_param(value: Any, label: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str) or _PARAM.fullmatch(value) is None:
        raise TrackolapConfigurationError(label + " is invalid")
    return value


def _extract_path(payload: Any, path: str, code: str) -> Any:
    current = payload
    for segment in path.split("."):
        if not isinstance(current, Mapping) or segment not in current:
            raise SourceFailure(code)
        current = current[segment]
    return current


def _safe_code(error: Exception) -> str:
    code = str(error)
    return code if re.fullmatch(r"[a-z_]{3,64}", code) else "source_unavailable"
