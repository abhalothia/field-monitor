from pathlib import Path


def test_manager_assets_define_action_centre():
    root = Path(__file__).resolve().parents[2] / "ffl" / "static" / "manager"

    assert "FFL Action Centre" in (root / "index.html").read_text()
    assert "/api/v1/runtime" in (root / "app.js").read_text()
    assert "/api/v1/exceptions/" in (root / "app.js").read_text()
