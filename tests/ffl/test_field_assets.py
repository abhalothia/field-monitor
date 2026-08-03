from pathlib import Path


def test_field_assets_define_fail_closed_field_capture():
    root = Path(__file__).resolve().parents[2] / "ffl" / "static" / "field"

    assert "अवलोकन दर्ज करें" in (root / "index.html").read_text()
    assert "/api/v1/field-capture/context" in (root / "app.js").read_text()
    assert "ffl-field-v2" in (root / "sw.js").read_text()
