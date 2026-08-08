"""A small, cached Gemini layer for the source-backed daily field brief.

The model never receives names, identifiers, coordinates, or raw source forms.
It can only turn a compact aggregate fact pack into two concise manager-facing
sentences.  Counts, filters, and every operating decision remain deterministic.
"""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import os
from threading import Lock
from time import monotonic
from typing import Any, Mapping

import httpx


MODEL = "gemini-3.5-flash-lite"
_API_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
_SUCCESS_CACHE_TTL_SECONDS = 60 * 60 * 8
_FAILURE_CACHE_TTL_SECONDS = 60 * 5
_CACHE_LIMIT = 128
_cache: dict[str, tuple[float, dict[str, Any] | None]] = {}
_cache_lock = Lock()


def daily_field_read(facts: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return an optional, tightly bounded reading of already-safe aggregates.

    A fact fingerprint makes repeated page loads free.  A source refresh changes
    the input fingerprint, so a new reading is generated once only when the
    verified operating facts actually change.
    """
    if not _is_worth_reading(facts):
        return None
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    fingerprint = _fingerprint(facts)
    now = monotonic()
    with _cache_lock:
        cached = _cache.get(fingerprint)
        if cached and now - cached[0] < (
            _SUCCESS_CACHE_TTL_SECONDS if cached[1] is not None else _FAILURE_CACHE_TTL_SECONDS
        ):
            return deepcopy(cached[1])
    reading = _request_reading(api_key, facts)
    with _cache_lock:
        if len(_cache) >= _CACHE_LIMIT:
            oldest = min(_cache, key=lambda key: _cache[key][0])
            _cache.pop(oldest, None)
        _cache[fingerprint] = (now, deepcopy(reading))
    return reading


def _is_worth_reading(facts: Mapping[str, Any]) -> bool:
    latest = facts.get("latest_record")
    return isinstance(latest, Mapping) and bool(latest.get("as_of")) and any(
        int(latest.get(key, 0) or 0) > 0
        for key in ("visits", "farmers_updated", "disease_reports", "open_tasks")
    )


def _fingerprint(facts: Mapping[str, Any]) -> str:
    encoded = json.dumps(facts, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(encoded.encode("utf-8")).hexdigest()


def _request_reading(api_key: str, facts: Mapping[str, Any]) -> dict[str, Any] | None:
    prompt = """You are Luna, a concise operating assistant for a farm team.
Use only the JSON fact pack below. Do not infer causes, forecasts, advice, names,
locations, crop details, or facts not supplied. Do not call activity 'today'; it
is the latest recorded field day. Write exactly two short plain-English sentences:
one neutral summary of the latest recorded field day, then one clear attention
sentence only when disease reports or open tasks are non-zero. If neither is
non-zero, make the second sentence say that no disease reports or open tasks are
recorded in this brief. Return strict JSON only in this exact shape:
{"summary":"...","attention":"..."}

FACT PACK:
""" + json.dumps(facts, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    try:
        response = httpx.post(
            _API_URL,
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json={"model": MODEL, "input": prompt},
            timeout=12.0,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError, TypeError):
        return None
    text = _response_text(payload)
    if not text:
        return None
    try:
        decoded = json.loads(_strip_code_fence(text))
    except json.JSONDecodeError:
        return None
    if not isinstance(decoded, Mapping):
        return None
    summary = _safe_sentence(decoded.get("summary"), 220)
    attention = _safe_sentence(decoded.get("attention"), 220)
    if not summary or not attention:
        return None
    return {"summary": summary, "attention": attention, "model": MODEL}


def _response_text(payload: Any) -> str | None:
    """Read text from either the REST interaction envelope or SDK-style output."""
    if isinstance(payload, Mapping):
        for key in ("output_text", "outputText", "text"):
            value = payload.get(key)
            if isinstance(value, str):
                return value
        for key in ("outputs", "output", "content"):
            value = payload.get(key)
            if isinstance(value, list):
                for item in value:
                    found = _response_text(item)
                    if found:
                        return found
            elif isinstance(value, Mapping):
                found = _response_text(value)
                if found:
                    return found
    elif isinstance(payload, list):
        for item in payload:
            found = _response_text(item)
            if found:
                return found
    return None


def _strip_code_fence(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        return stripped.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return stripped


def _safe_sentence(value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    clean = " ".join(value.split()).strip()
    if not clean or len(clean) > limit or "\n" in clean:
        return None
    return clean


def _clear_cache_for_tests() -> None:
    with _cache_lock:
        _cache.clear()
