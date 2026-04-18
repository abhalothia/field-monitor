"""Sanity checks on the paddy evalscripts: correct version, bands, outputs."""

from src.paddy_kharif import evalscripts_paddy as ep


def test_lswi_is_version_3_and_uses_b08_b11():
    script = ep.statistical_lswi()
    assert "//VERSION=3" in script
    assert "B08" in script and "B11" in script
    assert '"lswi"' in script  # output id
    assert "sampleType: \"FLOAT32\"" in script


def test_s1_vvvh_rvi_declares_all_three_outputs():
    script = ep.statistical_s1_vvvh_rvi()
    assert "//VERSION=3" in script
    # SAR bands
    assert '"VV"' in script and '"VH"' in script
    # All three named outputs plus dataMask
    for key in ('"vv_db"', '"vh_db"', '"rvi"', '"dataMask"'):
        assert key in script, f"missing output {key}"
    # dB conversion uses natural log / LN10 (Sentinel Hub evalscripts have no Math.log10)
    assert "Math.log" in script and "Math.LN10" in script


def test_ndvi_overlay_returns_rgba_and_transparent_clouds():
    script = ep.imagery_paddy_ndvi_overlay()
    assert "//VERSION=3" in script
    assert "bands: 4" in script
    # transparent alpha (0) on invalid SCL
    assert "[0, 0, 0, 0]" in script


def test_rvi_overlay_returns_rgba():
    script = ep.imagery_paddy_rvi_overlay()
    assert "//VERSION=3" in script
    assert "bands: 4" in script
    assert '"VV"' in script and '"VH"' in script


def test_registry_entries_exist():
    assert "LSWI" in ep.PADDY_OPTICAL_STATISTICAL
    assert ep.PADDY_SAR_STATISTICAL is ep.statistical_s1_vvvh_rvi
    assert "ndvi_overlay" in ep.PADDY_IMAGERY_EVALSCRIPTS
    assert "rvi_overlay" in ep.PADDY_IMAGERY_EVALSCRIPTS
