from __future__ import annotations

from types import SimpleNamespace

from ffl.services import openai_responses


SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"label": {"type": "string"}},
    "required": ["label"],
}


def test_structured_output_uses_private_strict_responses_request(monkeypatch):
    calls = []

    def fake_post(url, *, headers, json, timeout):
        calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"output_text": '{"label":"Known label"}'},
        )

    monkeypatch.setattr(openai_responses.httpx, "post", fake_post)
    payload, model = openai_responses.structured_output(
        prompt="Only a safe fact pack", schema_name="safe_label", schema=SCHEMA,
        environment={"OPENAI_API_KEY": "server-key"},
    )

    assert payload == {"label": "Known label"}
    assert model == "gpt-5.6-luna"
    assert calls[0]["url"] == openai_responses.RESPONSES_URL
    assert calls[0]["headers"]["Authorization"] == "Bearer server-key"
    assert calls[0]["json"]["store"] is False
    assert calls[0]["json"]["reasoning"] == {"effort": "none"}
    assert calls[0]["json"]["text"]["format"] == {
        "type": "json_schema", "name": "safe_label", "strict": True, "schema": SCHEMA,
    }


def test_structured_output_does_not_attempt_a_request_without_a_server_key(monkeypatch):
    monkeypatch.setattr(openai_responses.httpx, "post", lambda **_: (_ for _ in ()).throw(AssertionError("should not call OpenAI")))
    assert openai_responses.structured_output(
        prompt="safe", schema_name="safe", schema=SCHEMA, environment={},
    ) == (None, None)


def test_structured_output_uses_vercels_short_lived_identity_when_available(monkeypatch):
    calls = []

    def fake_post(url, *, headers, json, timeout):
        calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"output_text": '{"label":"Known label"}'},
        )

    monkeypatch.setattr(openai_responses.httpx, "post", fake_post)
    payload, model = openai_responses.structured_output(
        prompt="Only a safe fact pack", schema_name="safe_label", schema=SCHEMA,
        environment={"VERCEL_OIDC_TOKEN": "short-lived-token"},
    )

    assert payload == {"label": "Known label"}
    assert model == "openai/gpt-5.6-luna"
    assert calls[0]["url"] == openai_responses.GATEWAY_RESPONSES_URL
    assert calls[0]["headers"]["Authorization"] == "Bearer short-lived-token"
    assert calls[0]["json"]["model"] == "openai/gpt-5.6-luna"


def test_response_text_reads_a_standard_nested_responses_envelope():
    assert openai_responses.response_text({
        "output": [{"type": "message", "content": [{"type": "output_text", "text": "{\"label\":\"x\"}"}]}]
    }) == '{"label":"x"}'
