"""Small, server-only Gemini structured-output boundary.

Only deliberately approved, small fact packs may reach this module.  It never
receives browser input or exposes the server key.  Callers must still validate
every returned field before any private record is changed.
"""

from __future__ import annotations

import json
import os
from typing import Any, Mapping

import httpx


DEFAULT_MODEL = "gemini-3.5-flash-lite"
INTERACTIONS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"


def configured_model(environment: Mapping[str, str] | None = None) -> str:
    """Return the one bounded Gemini model choice, without browser input."""
    environment = os.environ if environment is None else environment
    return str(environment.get("FFL_GEMINI_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL


def structured_output(
    *,
    prompt: str,
    schema_name: str,
    schema: Mapping[str, Any],
    model: str | None = None,
    timeout_seconds: float = 25.0,
    environment: Mapping[str, str] | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Request validated JSON from Gemini, or quietly return no suggestion.

    The active Interactions endpoint for this project accepts an explicit JSON
    contract in the prompt, rather than a schema envelope. Keeping the schema
    at this boundary makes the contract visible, while caller validation remains
    the only authority for persistence.
    """
    del schema_name
    environment = os.environ if environment is None else environment
    api_key = str(environment.get("GEMINI_API_KEY") or "").strip()
    selected_model = (model or configured_model(environment)).strip()
    if not api_key or not selected_model:
        return None, None
    try:
        response = httpx.post(
            INTERACTIONS_URL,
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json={
                "model": selected_model,
                "input": _json_contract_prompt(prompt, schema),
            },
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError, TypeError):
        return None, None
    text = response_text(body)
    if not text:
        return None, None
    try:
        payload = json.loads(strip_code_fence(text))
    except json.JSONDecodeError:
        return None, None
    return (dict(payload), selected_model) if isinstance(payload, Mapping) else (None, None)


def response_text(payload: Any) -> str | None:
    """Read only model text from the Gemini Interactions envelope.

    Interaction responses include the original user input in ``steps``.  Never
    treat that echoed input as generated output: it could make a validator parse
    the prompt instead of the model's JSON.
    """
    if isinstance(payload, Mapping):
        for key in ("output_text", "outputText", "text"):
            value = payload.get(key)
            if isinstance(value, str):
                return value
        steps = payload.get("steps")
        if isinstance(steps, list):
            for step in steps:
                if not isinstance(step, Mapping):
                    continue
                if str(step.get("type") or "").lower() not in {
                    "model_output", "message", "assistant_output",
                }:
                    continue
                found = _model_content_text(step.get("content"))
                if found:
                    return found
        for key in ("outputs", "output"):
            value = payload.get(key)
            found = _model_content_text(value)
            if found:
                return found
        if str(payload.get("type") or "").lower() in {
            "model_output", "message", "assistant_output",
        }:
            return _model_content_text(payload.get("content"))
    elif isinstance(payload, list):
        for item in payload:
            found = _model_content_text(item)
            if found:
                return found
    return None


def strip_code_fence(value: str) -> str:
    """Tolerate a harmless Markdown fence while retaining strict JSON parsing."""
    value = value.strip()
    if value.startswith("```") and value.endswith("```"):
        return value.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return value


def _json_contract_prompt(prompt: str, schema: Mapping[str, Any]) -> str:
    """Make the requested JSON shape explicit without sending any new facts."""
    return prompt + "\n\nReturn JSON only. Required JSON schema:\n" + json.dumps(
        schema, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )


def _model_content_text(value: Any) -> str | None:
    if isinstance(value, Mapping):
        if str(value.get("type") or "").lower() in {"text", "output_text"}:
            text = value.get("text")
            if isinstance(text, str):
                return text
        return _model_content_text(value.get("content"))
    if isinstance(value, list):
        for item in value:
            found = _model_content_text(item)
            if found:
                return found
    return None
