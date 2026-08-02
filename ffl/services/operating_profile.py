"""Safe, read-only operating-profile configuration for the manager surface.

An operating profile is customer-owned display context, not farm data.  It is
deliberately supplied through deployment configuration while the pilot has one
manager, so it does not introduce a second database model or expose a write
surface.  The profile may describe a public operating area or public hub, but
it never contains field, farmer, contact, or evidence information.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qs, urlparse


_MAX_NAME = 120
_MAX_LABEL = 180
_MAX_URL = 600
_MAP_HOST = "www.openstreetmap.org"
_MAP_PATH = "/export/embed.html"
_MAP_QUERY_KEYS = {"bbox", "layer", "marker"}


def _empty_profile() -> dict[str, Any]:
    return {
        "configured": False,
        "display_name": "Operating profile not set",
        "website_url": None,
        "coverage_label": None,
        "network_summary": None,
        "public_hub_label": None,
        "source_url": None,
        "map_embed_url": None,
    }


def _required_string(value: Any, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    normalized = value.strip()
    if len(normalized) > maximum:
        raise ValueError(f"{field} is too long")
    return normalized


def _optional_string(value: Any, field: str, maximum: int) -> str | None:
    if value is None or value == "":
        return None
    return _required_string(value, field, maximum)


def _https_url(value: Any, field: str) -> str | None:
    if value is None or value == "":
        return None
    normalized = _required_string(value, field, _MAX_URL)
    parsed = urlparse(normalized)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise ValueError(f"{field} must be a clean HTTPS URL")
    return normalized


def _map_embed_url(value: Any) -> str | None:
    if value is None or value == "":
        return None
    normalized = _https_url(value, "map_embed_url")
    assert normalized is not None
    parsed = urlparse(normalized)
    query = parse_qs(parsed.query, keep_blank_values=True)
    if (
        parsed.hostname != _MAP_HOST
        or parsed.path != _MAP_PATH
        or set(query) - _MAP_QUERY_KEYS
    ):
        raise ValueError("map_embed_url must be an OpenStreetMap embed URL")
    return normalized


def normalize_operating_profile(profile: Mapping[str, Any] | None) -> dict[str, Any]:
    """Validate the tiny public display contract before it reaches the browser."""
    if profile is None:
        return _empty_profile()
    if not isinstance(profile, Mapping):
        raise ValueError("FFL_OPERATING_PROFILE_JSON must contain an object")
    allowed = {
        "display_name",
        "website_url",
        "coverage_label",
        "network_summary",
        "public_hub_label",
        "source_url",
        "map_embed_url",
    }
    unexpected = set(profile) - allowed
    if unexpected:
        raise ValueError("operating profile contains unsupported fields")

    display_name = _required_string(profile.get("display_name"), "display_name", _MAX_NAME)
    normalized = {
        "configured": True,
        "display_name": display_name,
        "website_url": _https_url(profile.get("website_url"), "website_url"),
        "coverage_label": _optional_string(profile.get("coverage_label"), "coverage_label", _MAX_LABEL),
        "network_summary": _optional_string(profile.get("network_summary"), "network_summary", _MAX_LABEL),
        "public_hub_label": _optional_string(profile.get("public_hub_label"), "public_hub_label", _MAX_LABEL),
        "source_url": _https_url(profile.get("source_url"), "source_url"),
        "map_embed_url": _map_embed_url(profile.get("map_embed_url")),
    }
    if normalized["map_embed_url"] and not normalized["public_hub_label"]:
        raise ValueError("public_hub_label is required when map_embed_url is set")
    if normalized["network_summary"] and not normalized["source_url"]:
        raise ValueError("source_url is required when network_summary is set")
    return normalized


def operating_profile_from_environment(environment: Mapping[str, str] | None = None) -> dict[str, Any]:
    environment = environment or os.environ
    raw = environment.get("FFL_OPERATING_PROFILE_JSON", "").strip()
    if not raw:
        return _empty_profile()
    try:
        profile = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError("FFL_OPERATING_PROFILE_JSON must contain valid JSON") from error
    return normalize_operating_profile(profile)
