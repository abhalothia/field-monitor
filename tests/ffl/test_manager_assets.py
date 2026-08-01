from pathlib import Path


def test_manager_assets_define_action_centre():
    root = Path(__file__).resolve().parents[2] / "ffl" / "static" / "manager"
    app_js = (root / "app.js").read_text()

    assert "FFL Action Centre" in (root / "index.html").read_text()
    assert "/api/v1/runtime" in app_js
    assert "/api/v1/exceptions/" in app_js
    assert "allocation.crop_name" in app_js
    assert "allocation.cultivar" in app_js

    for status in (
        "reported",
        "triaged",
        "owned",
        "mitigated",
        "monitoring",
        "resolved",
        "accepted_risk",
        "reopened",
    ):
        assert "{0}:".format(status) in app_js

    for unsupported_status in ("assigned", "in_progress", "escalated"):
        assert "{0}:".format(unsupported_status) not in app_js
