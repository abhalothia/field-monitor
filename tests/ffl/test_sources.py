from datetime import datetime, timezone
import threading

from fastapi.testclient import TestClient
import pytest

from ffl.api.source_routes import router as source_router
from ffl.app import create_app
from ffl.persistence import repository
from ffl.persistence.database import open_connection
from ffl.persistence.repository import create_person
from ffl.persistence.schema import create_schema
from ffl.services import sources


FIXED_NOW = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)


class WeatherAdapter:
    source_type = "test_weather"
    requires_endpoint = False
    requires_credentials = True

    def __init__(self):
        self.credentials = []

    def fetch(self, source, credential, now):
        self.credentials.append(credential)
        return sources.AdapterRefreshResult(
            rows_received=1,
            cursor="cursor-not-exposed-to-manager-status",
            coverage={"state": "UP", "district": "pilot-district"},
            signals=(
                sources.RegionalSignalInput(
                    source_identifier="official-product-2026-08-01",
                    region="pilot-district",
                    signal_type="rainfall_forecast",
                    observed_at="2026-08-01T06:00:00Z",
                    value={"rain_mm": 8},
                    signal_kind="forecast",
                    valid_from="2026-08-01T06:00:00Z",
                    valid_to="2026-08-02T06:00:00Z",
                    resolution="district",
                ),
            ),
        )


class NeverCalledCredentialAdapter:
    source_type = "needs_credential"
    requires_endpoint = False
    requires_credentials = True

    def fetch(self, source, credential, now):
        raise AssertionError("adapter should not receive a missing credential")


class LeakyFailureAdapter:
    source_type = "bad_provider"
    requires_endpoint = False
    requires_credentials = False

    def fetch(self, source, credential, now):
        raise RuntimeError("provider failed at https://provider.example/?api-key=should-not-persist")


class UnsafeUnavailableAdapter:
    source_type = "unsafe_unavailable"
    requires_endpoint = False
    requires_credentials = False

    def fetch(self, source, credential, now):
        raise sources.SourceUnavailable("https://provider.example/?api-key=must-not-persist")


class PartiallyInvalidAdapter:
    source_type = "partially_invalid"
    requires_endpoint = False
    requires_credentials = False

    def fetch(self, source, credential, now):
        return sources.AdapterRefreshResult(
            rows_received=2,
            signals=(
                sources.RegionalSignalInput(
                    "safe-observation", "pilot-district", "forecast", "2026-08-01T00:00:00Z",
                    {"rain_mm": 2}, "forecast",
                ),
                sources.RegionalSignalInput(
                    "bad-observation", "pilot-district", "forecast", "not-a-time",
                    {"rain_mm": 7}, "forecast",
                ),
            ),
        )


class ContextAdapter:
    source_type = "context_provider"
    requires_endpoint = False
    requires_credentials = False

    def __init__(self, signals):
        self._signals = tuple(signals)

    def fetch(self, source, credential, now):
        return sources.AdapterRefreshResult(rows_received=len(self._signals), signals=self._signals)


def _context_signal(
    status="available", valid_to="2026-08-02T00:00:00Z", freshness_target_hours=None,
    valid_from="2026-07-31T00:00:00Z",
):
    return sources.RegionalSignalInput(
        source_identifier="normalised-context-1",
        region="pilot-district",
        signal_type="rainfall_forecast",
        observed_at="2026-08-01T06:00:00Z",
        value={"rain_mm": 8},
        signal_kind="forecast",
        source_url="https://source.example.invalid/published-product",
        coverage={"state": "UP", "district": "pilot-district"},
        valid_from=valid_from,
        valid_to=valid_to,
        resolution="district",
        freshness_target_hours=freshness_target_hours,
        status=status,
    )


def _register(ffl_db, owner, source_key="pilot-weather", source_type="test_weather", **overrides):
    fields = {
        "source_key": source_key,
        "display_name": "Pilot weather context",
        "source_type": source_type,
        "purpose": "regional weather context",
        "authority_level": "official",
        "owner_id": owner.id,
        "permitted_data_classes": ["forecast", "warning"],
        "schema_version": "2026-08",
        "mapping_version": "weather-v1",
        "default_coverage": {"state": "UP", "district": "pilot-district"},
        "credentials_reference": "env://FFL_TEST_WEATHER_TOKEN",
        "endpoint": "https://provider.example.invalid/weather",
        "freshness_target_hours": 6,
        "license_notes": "review before production use",
        "enabled": True,
    }
    fields.update(overrides)
    return sources.register_source(ffl_db, **fields)


def test_register_custom_source_is_idempotent_but_rejects_conflicting_configuration(ffl_db, owner):
    source = _register(ffl_db, owner)
    replay = _register(ffl_db, owner)

    assert replay == source
    with pytest.raises(ValueError, match="different configuration"):
        _register(ffl_db, owner, display_name="Different source")
    with pytest.raises(ValueError, match="env://"):
        _register(ffl_db, owner, source_key="bad-credential", credentials_reference="raw-secret")
    with pytest.raises(ValueError, match="without credentials"):
        _register(ffl_db, owner, source_key="bad-endpoint", endpoint="https://provider.example/?api-key=no")
    with pytest.raises(ValueError, match="precise coordinates"):
        _register(ffl_db, owner, source_key="bad-coverage", default_coverage={"latitude": 28.6})
    secret_backed = _register(
        ffl_db, owner, source_key="secret-backed", credentials_reference="secret://ffl/weather/api-key"
    )
    assert secret_backed.credentials_reference == "secret://ffl/weather/api-key"


def test_default_refresh_records_explicit_unavailable_health_without_network_or_fake_values(ffl_db, owner):
    source = _register(ffl_db, owner, source_type="not-installed")

    run = sources.refresh_source(ffl_db, source.source_key, now=FIXED_NOW)
    status = sources.get_source_status(ffl_db, source.source_key, now=FIXED_NOW)

    assert run.status == "unavailable"
    assert run.error_summary == "adapter_not_configured"
    assert repository.list_regional_signals(ffl_db, "pilot-district") == []
    assert status["health"] == "unavailable"
    assert status["freshness"] == "unknown"
    assert status["latest_run"]["reason_code"] == "adapter_not_configured"


def test_disabled_or_missing_credential_sources_are_explicitly_unavailable(ffl_db, owner):
    disabled = _register(ffl_db, owner, source_key="disabled-weather", enabled=False)
    needs_credential = _register(
        ffl_db, owner, source_key="credential-weather", source_type="needs_credential"
    )

    disabled_run = sources.refresh_source(ffl_db, disabled.source_key, now=FIXED_NOW)
    credential_run = sources.refresh_source(
        ffl_db, needs_credential.source_key,
        adapters=sources.AdapterRegistry([NeverCalledCredentialAdapter()]), now=FIXED_NOW,
    )

    assert (disabled_run.status, disabled_run.error_summary) == ("unavailable", "source_disabled")
    assert (credential_run.status, credential_run.error_summary) == ("unavailable", "credentials_unavailable")


def test_successful_adapter_refresh_persists_normalised_provenance_and_safe_manager_status(ffl_db, owner):
    source = _register(ffl_db, owner)
    adapter = WeatherAdapter()

    run = sources.refresh_source(
        ffl_db, source.source_key, adapters=sources.AdapterRegistry([adapter]),
        credential_resolver=lambda reference: "runtime-only-token", now=FIXED_NOW,
    )
    signals = repository.list_regional_signals(ffl_db, "pilot-district")
    manager_status = sources.get_source_status(ffl_db, source.source_key, now=FIXED_NOW)

    assert run.status == "succeeded"
    assert run.rows_received == 1
    assert run.rows_accepted == 1
    assert adapter.credentials == ["runtime-only-token"]
    assert len(signals) == 1
    assert signals[0].source_id == source.id
    assert signals[0].source_run_id == run.id
    assert signals[0].source_identifier == "official-product-2026-08-01"
    assert signals[0].signal_kind == "forecast"
    assert manager_status["health"] == "healthy"
    assert manager_status["freshness"] == "fresh"
    assert manager_status["regional_signal_counts"] == {"available": 1}
    rendered = repr(manager_status)
    assert "provider.example.invalid" not in rendered
    assert "FFL_TEST_WEATHER_TOKEN" not in rendered
    assert "runtime-only-token" not in rendered
    assert "rain_mm" not in rendered


def test_provider_exception_is_failed_without_persisting_exception_details(ffl_db, owner):
    source = _register(ffl_db, owner, source_type="bad_provider", credentials_reference=None)

    run = sources.refresh_source(
        ffl_db, source.source_key, adapters=sources.AdapterRegistry([LeakyFailureAdapter()]), now=FIXED_NOW,
    )

    assert (run.status, run.error_summary) == ("failed", "provider_refresh_failed")
    assert "api-key" not in repr(run)
    assert repository.list_regional_signals(ffl_db, "pilot-district") == []


def test_adapter_unavailable_codes_are_sanitised_before_persistence(ffl_db, owner):
    source = _register(ffl_db, owner, source_type="unsafe_unavailable", credentials_reference=None)

    run = sources.refresh_source(
        ffl_db, source.source_key, adapters=sources.AdapterRegistry([UnsafeUnavailableAdapter()]), now=FIXED_NOW,
    )

    assert (run.status, run.error_summary) == ("unavailable", "source_unavailable")
    assert "api-key" not in repr(run)


def test_invalid_normalised_result_is_atomic_and_legacy_error_text_is_redacted(ffl_db, owner):
    source = _register(ffl_db, owner, source_type="partially_invalid", credentials_reference=None)

    failed = sources.refresh_source(
        ffl_db, source.source_key, adapters=sources.AdapterRegistry([PartiallyInvalidAdapter()]), now=FIXED_NOW,
    )
    # A source imported by an older implementation must not make manager
    # status reveal endpoint/query information either.
    repository.create_source_run(
        ffl_db, source.id, source.default_coverage, source.mapping_version, status="failed",
        error_summary="https://legacy.example/?api-key=never-return-this",
    )
    manager_status = sources.get_source_status(ffl_db, source.source_key, now=FIXED_NOW)

    assert (failed.status, failed.error_summary) == ("failed", "provider_refresh_failed")
    assert repository.list_regional_signals(ffl_db, "pilot-district") == []
    assert manager_status["latest_run"]["reason_code"] == "error_redacted"
    assert "api-key" not in repr(manager_status)


def test_stale_status_and_run_summary_do_not_expose_coverage_values(ffl_db, owner):
    source = _register(ffl_db, owner)
    run = sources.refresh_source(
        ffl_db, source.source_key, adapters=sources.AdapterRegistry([WeatherAdapter()]),
        credential_resolver=lambda _: "runtime-only-token", now=FIXED_NOW,
    )

    status = sources.get_source_status(
        ffl_db, source.source_key, now=datetime(2026, 8, 2, 1, 0, tzinfo=timezone.utc)
    )
    runs = sources.list_source_run_summaries(ffl_db, source.source_key)

    assert status["health"] == "stale"
    assert status["freshness"] == "stale"
    assert runs == [status["latest_run"]]
    assert runs[0]["id"] == run.id
    assert runs[0]["coverage_dimensions"] == ["district", "state"]
    assert "pilot-district" not in repr(runs[0])


@pytest.mark.parametrize(
    "signals,source_freshness,expected_freshness",
    [
        ((), 6, "no_effective_signals"),
        ((_context_signal(status="stale"),), 6, "no_effective_signals"),
        ((_context_signal(valid_to="2026-08-01T11:59:59Z"),), 6, "no_effective_signals"),
        ((_context_signal(freshness_target_hours=0),), 6, "no_effective_signals"),
        ((_context_signal(),), 0, "not_configured"),
    ],
)
def test_transport_success_cannot_claim_healthy_or_fresh_without_current_effective_context(
    ffl_db, owner, signals, source_freshness, expected_freshness
):
    source = _register(
        ffl_db, owner, source_key="context-health-{}".format(source_freshness),
        source_type="context_provider", credentials_reference=None, freshness_target_hours=source_freshness,
    )

    run = sources.refresh_source(
        ffl_db, source.source_key, adapters=sources.AdapterRegistry([ContextAdapter(signals)]), now=FIXED_NOW,
    )
    status = sources.get_source_status(ffl_db, source.source_key, now=FIXED_NOW)

    assert run.status == "succeeded"
    assert status["freshness"] == expected_freshness
    assert status["health"] == expected_freshness
    assert status["health"] != "healthy"
    assert status["freshness"] != "fresh"
    assert status["effective_regional_signal_count"] == 0


def test_regional_context_returns_normalised_attributable_signals_without_provider_endpoints(tmp_path, monkeypatch):
    monkeypatch.setattr(sources, "_now", lambda: FIXED_NOW)
    app = create_app(str(tmp_path / "regional-context.db"))
    app.include_router(source_router)
    owner = create_person(app.state.conn, "Context Owner", "operations_lead")
    source = _register(
        app.state.conn, owner, source_key="regional-context", source_type="context_provider",
        credentials_reference=None,
    )
    sources.refresh_source(
        app.state.conn, source.source_key,
        adapters=sources.AdapterRegistry([ContextAdapter([_context_signal()])]), now=FIXED_NOW,
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/regional-context", params={"region": "pilot-district"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["region"] == "pilot-district"
    assert len(payload["signals"]) == 1
    signal = payload["signals"][0]
    assert signal["value"] == {"rain_mm": 8}
    assert signal["effective"] is True
    assert signal["provenance"] == {
        "source_key": "regional-context",
        "source_display_name": "Pilot weather context",
        "authority_level": "official",
        "source_run_id": signal["provenance"]["source_run_id"],
        "source_identifier": "normalised-context-1",
        "mapping_version": "weather-v1",
    }
    rendered = repr(payload)
    assert "source.example.invalid" not in rendered
    assert "provider.example.invalid" not in rendered
    assert "pilot-district" not in repr(signal["coverage_dimensions"])


def test_conflicting_concurrent_source_registration_never_looks_idempotent(tmp_path):
    database_path = tmp_path / "concurrent-sources.db"
    setup = open_connection(str(database_path))
    create_schema(setup)
    owner = create_person(setup, "Concurrent Owner", "operations_lead")
    setup.close()
    barrier = threading.Barrier(2)
    outcomes = []
    outcomes_lock = threading.Lock()

    def register(display_name):
        connection = open_connection(str(database_path))
        try:
            barrier.wait(timeout=5)
            source = _register(
                connection, owner, source_key="concurrent-weather", display_name=display_name,
                source_type="concurrent_provider", credentials_reference=None,
            )
            outcome = ("created", source.display_name)
        except Exception as error:
            outcome = ("error", str(error))
        finally:
            connection.close()
        with outcomes_lock:
            outcomes.append(outcome)

    first = threading.Thread(target=register, args=("First config",))
    second = threading.Thread(target=register, args=("Second config",))
    first.start()
    second.start()
    first.join(timeout=10)
    second.join(timeout=10)

    assert not first.is_alive()
    assert not second.is_alive()
    assert sorted(kind for kind, _ in outcomes) == ["created", "error"]
    assert any("different configuration" in detail for kind, detail in outcomes if kind == "error")


def test_india_candidates_are_discovery_only_and_do_not_claim_unverified_access():
    candidates = sources.india_source_candidates()
    by_key = {candidate["source_key"]: candidate for candidate in candidates}

    assert by_key["imd-weather"]["onboarding_status"] == "access_review_and_ip_whitelisting_required"
    assert by_key["agmarknet-market-context"]["onboarding_status"] == "programmatic_access_unverified"
    assert by_key["copernicus-sentinel-2-context"]["onboarding_status"] == "account_and_processing_design_review_required"
    assert by_key["nasa-power-weather-context"]["onboarding_status"] == "parameter_and_validation_review_required"
    assert by_key["soilgrids-baseline-context"]["onboarding_status"] == "licence_resolution_and_validation_review_required"
    assert set(by_key) == {
        "imd-weather",
        "agmarknet-market-context",
        "copernicus-sentinel-2-context",
        "nasa-power-weather-context",
        "soilgrids-baseline-context",
    }
    for candidate in candidates:
        assert candidate["purpose"]
        assert candidate["authority_level"]
        assert candidate["authority_notes"]
        assert candidate["access_notes"]
        assert candidate["limitations"]
        assert candidate["documentation_url"].startswith("https://")
        assert candidate["allowed_data_classes"]
    assert all("endpoint" not in candidate for candidate in candidates)


def test_source_router_is_safe_when_mounted_without_provider_adapters(tmp_path):
    app = create_app(str(tmp_path / "sources.db"))
    app.include_router(source_router)
    owner = create_person(app.state.conn, "Source Owner", "operations_lead")
    payload = {
        "source_key": "api-weather",
        "display_name": "Reviewed weather context",
        "source_type": "trusted_http_json",
        "purpose": "regional weather context",
        "authority_level": "official",
        "owner_id": owner.id,
        "permitted_data_classes": ["forecast"],
        "schema_version": "2026-08",
        "mapping_version": "weather-v1",
        "default_coverage": {"state": "UP", "district": "pilot-district"},
        "credentials_reference": "env://FFL_WEATHER_TOKEN",
        "endpoint": "https://provider.example.invalid/weather",
        "freshness_target_hours": 3,
        "enabled": True,
    }

    with TestClient(app) as client:
        created = client.post("/api/v1/sources", json=payload)
        replayed = client.post("/api/v1/sources", json=payload)
        refreshed = client.post("/api/v1/sources/api-weather/refresh")
        statuses = client.get("/api/v1/sources")
        runs = client.get("/api/v1/sources/api-weather/runs")
        candidates = client.get("/api/v1/sources/india-candidates")

    assert created.status_code == 201
    assert replayed.status_code == 200
    assert refreshed.status_code == 200
    assert refreshed.json()["health"] == "unavailable"
    assert refreshed.json()["latest_run"]["reason_code"] == "adapter_not_configured"
    assert statuses.status_code == 200
    assert runs.status_code == 200
    assert candidates.status_code == 200
    rendered = repr({"created": created.json(), "runs": runs.json(), "statuses": statuses.json()})
    assert "provider.example.invalid" not in rendered
    assert "FFL_WEATHER_TOKEN" not in rendered
