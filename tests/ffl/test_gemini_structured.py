from __future__ import annotations

from types import SimpleNamespace

from ffl.services import gemini_structured


SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"label": {"type": "string"}},
    "required": ["label"],
}


def test_structured_output_uses_private_gemini_interactions_request(monkeypatch):
    calls = []

    def fake_post(url, *, headers, json, timeout):
        calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"output_text": '{"label":"Known label"}'},
        )

    monkeypatch.setattr(gemini_structured.httpx, "post", fake_post)
    payload, model = gemini_structured.structured_output(
        prompt="Only a safe fact pack", schema_name="safe_label", schema=SCHEMA,
        environment={"GEMINI_API_KEY": "server-key"},
    )

    assert payload == {"label": "Known label"}
    assert model == "gemini-3.5-flash-lite"
    assert calls[0]["url"] == gemini_structured.INTERACTIONS_URL
    assert calls[0]["headers"]["x-goog-api-key"] == "server-key"
    assert calls[0]["json"]["model"] == "gemini-3.5-flash-lite"
    assert calls[0]["json"]["input"].startswith("Only a safe fact pack\n\nReturn JSON only.")
    assert '"type":"object"' in calls[0]["json"]["input"]


def test_structured_output_does_not_attempt_a_request_without_a_server_key(monkeypatch):
    monkeypatch.setattr(gemini_structured.httpx, "post", lambda **_: (_ for _ in ()).throw(AssertionError("should not call Gemini")))
    assert gemini_structured.structured_output(
        prompt="safe", schema_name="safe", schema=SCHEMA, environment={},
    ) == (None, None)


def test_response_text_reads_a_standard_interactions_envelope():
    assert gemini_structured.response_text({
        "steps": [
            {"type": "user_input", "content": [{"type": "text", "text": "ignore this"}]},
            {"type": "model_output", "content": [{"type": "text", "text": '{"label":"x"}'}]},
        ]
    }) == '{"label":"x"}'
