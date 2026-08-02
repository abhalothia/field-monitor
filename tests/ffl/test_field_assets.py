from pathlib import Path


def test_field_assets_define_offline_exception_capture():
    root = Path(__file__).resolve().parents[2] / "ffl" / "static" / "field"

    assert "अपवाद दर्ज करें" in (root / "index.html").read_text()
    assert "ffl.pendingExceptions" in (root / "app.js").read_text()
    assert "ffl-field-v1" in (root / "sw.js").read_text()
