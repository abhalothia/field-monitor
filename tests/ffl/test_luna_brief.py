from __future__ import annotations

from types import SimpleNamespace

from ffl.services import luna_brief


FACTS = {
    "latest_record": {
        "as_of": "2026-08-03", "visits": 4, "farmers_updated": 3,
        "disease_reports": 1, "open_tasks": 2,
    },
    "operating_totals": {
        "farmers": 12, "farm_candidates": 10, "field_workers": 2,
        "open_work": 2, "reported_visits": 18,
    },
    "reported_disease_severity": {"high": 1},
}


def setup_function():
    luna_brief._clear_cache_for_tests()


def test_daily_field_read_uses_only_a_cached_aggregate_fact_pack(monkeypatch):
    calls = []

    def fake_post(url, *, headers, json, timeout):
        calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {
                "steps": [{"type": "reasoning"}, {"type": "message", "content": [{"type": "text", "text":
                    '{"summary":"Four visits were filed for three farmers on the latest recorded field day.",'
                    '"attention":"One disease report and two open tasks need review."}'}]}]
            },
        )

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(luna_brief.httpx, "post", fake_post)

    first = luna_brief.daily_field_read(FACTS)
    second = luna_brief.daily_field_read(FACTS)

    assert first == second == {
        "summary": "Four visits were filed for three farmers on the latest recorded field day.",
        "attention": "One disease report and two open tasks need review.",
        "model": "gemini-3.5-flash-lite",
    }
    assert len(calls) == 1
    assert calls[0]["json"]["model"] == "gemini-3.5-flash-lite"
    assert "Ramesh" not in calls[0]["json"]["input"]
    assert "FACT PACK:" in calls[0]["json"]["input"]


def test_daily_field_read_is_absent_without_a_server_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert luna_brief.daily_field_read(FACTS) is None


def test_daily_field_read_skips_empty_activity_without_calling_gemini(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(luna_brief.httpx, "post", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not call Gemini")))
    facts = {**FACTS, "latest_record": {"as_of": None, "visits": 0, "farmers_updated": 0, "disease_reports": 0, "open_tasks": 0}}
    assert luna_brief.daily_field_read(facts) is None


def test_daily_field_read_caches_a_provider_failure_so_home_stays_fast(monkeypatch):
    calls = []

    def fake_post(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(
            raise_for_status=lambda: (_ for _ in ()).throw(luna_brief.httpx.HTTPStatusError(
                "invalid key", request=SimpleNamespace(), response=SimpleNamespace(),
            )),
        )

    monkeypatch.setenv("GEMINI_API_KEY", "invalid-key")
    monkeypatch.setattr(luna_brief.httpx, "post", fake_post)
    assert luna_brief.daily_field_read(FACTS) is None
    assert luna_brief.daily_field_read(FACTS) is None
    assert len(calls) == 1
