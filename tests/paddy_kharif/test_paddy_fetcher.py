"""Fetcher tests: chunk coalescing + no-double-pull guards.

These don't hit Sentinel Hub. We mock SentinelClient / sar_client / cropsar
to just record the calls they receive and feed back synthetic responses.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from db.repository import upsert_field
from src.models import IndexReading
from src.paddy_kharif import config as pk_config
from src.paddy_kharif import paddy_fetcher as pf
from src.paddy_kharif.paddy_fetcher import (
    _coalesce_missing,
    _enumerate_weeks,
    _missing_weeks_for_index,
)
from src.paddy_kharif.repository_paddy import get_season_readings


def test_enumerate_weeks_every_7_days():
    weeks = _enumerate_weeks(date(2025, 6, 1), date(2025, 6, 29), 7)
    assert weeks == [date(2025, 6, 1), date(2025, 6, 8),
                     date(2025, 6, 15), date(2025, 6, 22), date(2025, 6, 29)]


def test_coalesce_merges_within_chunk_limit():
    missing = {date(2025, 6, 1), date(2025, 6, 8), date(2025, 9, 1)}
    ranges = _coalesce_missing(missing, chunk_days=60)
    # Jun 1 & Jun 8 merge; Sep 1 is a standalone range (gap > 60 days).
    assert ranges == [(date(2025, 6, 1), date(2025, 6, 8)),
                      (date(2025, 9, 1), date(2025, 9, 1))]


def test_coalesce_empty_returns_empty():
    assert _coalesce_missing(set()) == []


def test_missing_weeks_for_index_skips_already_fetched(paddy_db, test_field):
    upsert_field(paddy_db, test_field)
    from db.repository import upsert_reading
    upsert_reading(paddy_db, IndexReading(
        field_id=test_field.field_id, index_name="NDVI",
        reading_date="2025-06-01", mean_value=0.3,
        min_value=None, max_value=None, stdev_value=None,
        sample_count=10, cloud_cover_pct=None,
    ), season_tag="kharif_2025")

    weeks = [date(2025, 6, 1), date(2025, 6, 8), date(2025, 6, 15)]
    missing = _missing_weeks_for_index(
        paddy_db, test_field.field_id, "NDVI", weeks, "kharif_2025",
    )
    assert missing == {date(2025, 6, 8), date(2025, 6, 15)}


def _mock_sentinel_client():
    client = MagicMock()
    client._base_url = "https://example.invalid"
    # Return 2 intervals so upserts happen
    fake_interval = {
        "interval": {"from": "2025-06-01T00:00:00Z"},
        "outputs": {
            "ndvi": {"bands": {"B0": {"stats": {
                "mean": 0.4, "min": 0.3, "max": 0.5,
                "stDev": 0.05, "sampleCount": 42,
            }}}},
            "lswi": {"bands": {"B0": {"stats": {
                "mean": 0.25, "min": 0.2, "max": 0.3,
                "stDev": 0.03, "sampleCount": 42,
            }}}},
            "ndwi": {"bands": {"B0": {"stats": {
                "mean": 0.15, "min": 0.1, "max": 0.2,
                "stDev": 0.02, "sampleCount": 42,
            }}}},
            "ndre": {"bands": {"B0": {"stats": {
                "mean": 0.22, "min": 0.18, "max": 0.26,
                "stDev": 0.02, "sampleCount": 42,
            }}}},
        },
    }
    client.fetch_statistics.return_value = [fake_interval]
    return client


def test_fetch_kharif_season_rerun_makes_zero_api_calls(
    paddy_db, test_field, monkeypatch,
):
    """Guard 1: pre-flight diff means a rerun of a fully-populated DB is free."""
    upsert_field(paddy_db, test_field)

    # Prepopulate every weekly slot for every index + SAR signal.
    from db.repository import upsert_reading
    weeks = _enumerate_weeks(
        date(2025, 6, 1), date(2026, 1, 15), pk_config.SLIDER_STEP_DAYS,
    )
    for idx in pk_config.OPTICAL_INDICES + pk_config.SAR_SIGNALS:
        for w in weeks:
            upsert_reading(paddy_db, IndexReading(
                field_id=test_field.field_id, index_name=idx,
                reading_date=w.isoformat(), mean_value=0.5,
                min_value=None, max_value=None, stdev_value=None,
                sample_count=1, cloud_cover_pct=None,
            ), season_tag="kharif_2025")

    # Prepopulate overlays so G4 is also satisfied for every slider week.
    from db.repository import upsert_imagery
    from src.models import ImageryRecord
    for w in weeks:
        upsert_imagery(paddy_db, ImageryRecord(
            field_id=test_field.field_id,
            image_date=w.isoformat(),
            image_type="ndvi_overlay",
            file_path="/tmp/does-not-matter.png",
            width_px=256, height_px=256,
        ), season_tag="kharif_2025")

    # Mocks that would explode if accidentally called.
    mock_client = _mock_sentinel_client()
    fake_config = MagicMock(base_url="https://x", client_id="x", client_secret="x")

    monkeypatch.setattr(pf, "SentinelClient", lambda *_a, **_kw: mock_client)
    monkeypatch.setattr(pf, "TokenManager", lambda *_a, **_kw: MagicMock())
    monkeypatch.setattr(pf, "_try_cropsar", lambda *a, **kw: False)
    monkeypatch.setattr(
        pf, "fetch_s1_statistics",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("should not fetch SAR")),
    )
    monkeypatch.setattr(
        pf, "fetch_s2_image_by_geometry",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("should not fetch S2 img")),
    )
    monkeypatch.setattr(
        pf, "fetch_s1_image_by_geometry",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("should not fetch S1 img")),
    )

    summary = pf.fetch_kharif_season(
        paddy_db, test_field, fake_config, year=2025, run_detect=False,
    )

    assert mock_client.fetch_statistics.call_count == 0
    assert summary["api_requests"] == 0


def test_fetch_kharif_season_fresh_run_makes_chunked_calls(
    paddy_db, test_field, monkeypatch,
):
    """Fresh run: all weeks missing → at most one chunked call per optical
    index, one chunked call for SAR."""
    upsert_field(paddy_db, test_field)

    mock_client = _mock_sentinel_client()
    fake_config = MagicMock(base_url="https://x", client_id="x", client_secret="x")

    sar_calls: list = []
    def fake_s1_stats(_client, _geom, d_from, d_to, _evalscript,
                      aggregation_interval="P7D"):
        sar_calls.append((d_from, d_to))
        return [{
            "interval": {"from": "2025-06-01T00:00:00Z"},
            "outputs": {
                "vv_db": {"bands": {"B0": {"stats": {
                    "mean": -10.0, "min": -12.0, "max": -8.0,
                    "stDev": 1.0, "sampleCount": 100,
                }}}},
                "vh_db": {"bands": {"B0": {"stats": {
                    "mean": -17.0, "min": -19.0, "max": -15.0,
                    "stDev": 1.0, "sampleCount": 100,
                }}}},
                "rvi": {"bands": {"B0": {"stats": {
                    "mean": 0.35, "min": 0.2, "max": 0.5,
                    "stDev": 0.05, "sampleCount": 100,
                }}}},
            },
        }]

    monkeypatch.setattr(pf, "SentinelClient", lambda *_a, **_kw: mock_client)
    monkeypatch.setattr(pf, "TokenManager", lambda *_a, **_kw: MagicMock())
    monkeypatch.setattr(pf, "_try_cropsar", lambda *a, **kw: False)
    monkeypatch.setattr(pf, "fetch_s1_statistics", fake_s1_stats)
    # No overlay fetching — sample_count is 0 for this week after above upsert,
    # and we don't care about overlays in this test. Stub both.
    monkeypatch.setattr(pf, "fetch_s2_image_by_geometry",
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("stub")))
    monkeypatch.setattr(pf, "fetch_s1_image_by_geometry",
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("stub")))

    summary = pf.fetch_kharif_season(
        paddy_db, test_field, fake_config, year=2025, run_detect=False,
    )

    # 4 optical indices × 1 coalesced call each = 4
    assert mock_client.fetch_statistics.call_count == 4
    # SAR: 1 call covers VV/VH/RVI in one shot
    assert len(sar_calls) == 1
    assert summary["readings_stored"] >= 4


def test_fetch_rejects_non_2025_year(paddy_db, test_field):
    with pytest.raises(NotImplementedError):
        pf.fetch_kharif_season(
            paddy_db, test_field, MagicMock(), year=2024,
        )
