from pathlib import Path
import re


def test_manager_assets_define_action_centre():
    root = Path(__file__).resolve().parents[2] / "ffl" / "static" / "manager"
    app_js = (root / "app.js").read_text()

    assert "FFL Action Centre" in (root / "index.html").read_text()
    assert "/api/v1/runtime" in app_js
    assert "/api/v1/exceptions/" in app_js
    assert "allocation.crop_name" in app_js
    assert "allocation.cultivar" in app_js

    expected_exception_states = (
        "reported",
        "triaged",
        "owned",
        "mitigated",
        "monitoring",
        "resolved",
        "accepted_risk",
        "reopened",
    )
    actions_match = re.search(
        r"var actions = \{(?P<entries>.*?)\n    \};", app_js, re.DOTALL
    )

    assert actions_match is not None
    assert tuple(re.findall(r"^      ([a-z_]+):", actions_match.group("entries"), re.MULTILINE)) == expected_exception_states
    assert "Unsupported exception state" in app_js
    assert 'actions[exceptionRecord.status] : ""' in app_js
    assert "Review the record and assign the next action." not in app_js

    for unsupported_status in ("assigned", "in_progress", "escalated"):
        assert "{0}:".format(unsupported_status) not in app_js
