"""Tiny, server-only OpenAI Responses client for bounded structured work.

The operating product does not expose a model key to browsers and never needs
an LLM to render its factual boards.  Callers pass only deliberately approved,
small fact packs and validate every returned field before persistence.
"""

from __future__ import annotations

import json
import os
from typing import Any, Mapping

import httpx


DEFAULT_MODEL = "gpt-5.6-luna"
RESPONSES_URL = "https://api.openai.com/v1/responses"
GATEWAY_RESPONSES_URL = "https://ai-gateway.vercel.sh/v1/responses"


def configured_model(environment: Mapping[str, str] | None = None) -> str:
    """Return the one bounded model choice, without accepting browser input."""
    environment = os.environ if environment is None else environment
    return str(environment.get("FFL_AI_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL


def structured_output(
    *,
    prompt: str,
    schema_name: str,
    schema: Mapping[str, Any],
    model: str | None = None,
    timeout_seconds: float = 25.0,
    environment: Mapping[str, str] | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Request strict JSON, returning ``(payload, model)`` or ``(None, None)``.

    Missing credentials and transient provider failures are intentionally quiet:
    model wording is optional and must never blank an operating experience.
    """
    environment = os.environ if environment is None else environment
    request = _request_configuration(environment, model=model)
    if request is None:
        return None, None
    url, api_key, selected_model = request
    try:
        response = httpx.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": selected_model,
                "store": False,
                "reasoning": {"effort": "none"},
                "input": prompt,
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": schema_name,
                        "strict": True,
                        "schema": dict(schema),
                    },
                },
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


def _request_configuration(
    environment: Mapping[str, str], *, model: str | None,
) -> tuple[str, str, str] | None:
    """Prefer a direct key; otherwise use Vercel's short-lived gateway identity.

    Vercel injects ``VERCEL_OIDC_TOKEN`` at runtime, so production performs
    bounded model work without a second long-lived provider secret.  Local
    deliberate runs can use either an OpenAI key or ``AI_GATEWAY_API_KEY``.
    """
    selected_model = (model or configured_model(environment)).strip()
    if not selected_model:
        return None
    openai_key = str(environment.get("OPENAI_API_KEY") or "").strip()
    if openai_key:
        return RESPONSES_URL, openai_key, selected_model.removeprefix("openai/")
    gateway_key = str(
        environment.get("AI_GATEWAY_API_KEY") or environment.get("VERCEL_OIDC_TOKEN") or ""
    ).strip()
    if not gateway_key:
        return None
    gateway_model = selected_model if "/" in selected_model else "openai/" + selected_model
    return GATEWAY_RESPONSES_URL, gateway_key, gateway_model


def response_text(payload: Any) -> str | None:
    """Accept the current Responses envelope plus a conservative test shape."""
    if isinstance(payload, Mapping):
        for key in ("output_text", "outputText", "text"):
            value = payload.get(key)
            if isinstance(value, str):
                return value
        for key in ("output", "content"):
            value = payload.get(key)
            if isinstance(value, list):
                for item in value:
                    found = response_text(item)
                    if found:
                        return found
            elif isinstance(value, Mapping):
                found = response_text(value)
                if found:
                    return found
    elif isinstance(payload, list):
        for item in payload:
            found = response_text(item)
            if found:
                return found
    return None


def strip_code_fence(value: str) -> str:
    value = value.strip()
    if value.startswith("```") and value.endswith("```"):
        return value.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return value
