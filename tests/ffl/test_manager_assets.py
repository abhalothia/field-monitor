from pathlib import Path
import re


def test_manager_assets_define_field_ledger():
    root = Path(__file__).resolve().parents[2] / "ffl" / "static" / "manager"
    app_js = (root / "app.js").read_text()

    assert "Today on the farm." in (root / "index.html").read_text()
    assert "Review field signal" in (root / "index.html").read_text()
    assert "/api/v1/runtime" in app_js
    assert "/api/v1/exceptions/" in app_js
    assert "/api/v1/portfolio" in app_js
    assert "allocation.crop_name" in app_js
    assert "allocation.cultivar" in app_js
    assert "Risk &amp; action ledger" in (root / "index.html").read_text()
    assert "Source &amp; import health" in (root / "index.html").read_text()
    assert "Trials &amp; playbooks" in (root / "index.html").read_text()
    assert "Imports awaiting review" in app_js
    assert "Portfolio context is unavailable. Current action centre data is still usable." in app_js
    assert "fetch(runtimeUrl)" in app_js
    assert "fetch(portfolioUrl)" in app_js
    assert ".catch(renderPortfolioUnavailable)" in app_js
    assert "ledger.slice(0, 6)" in app_js
    assert "Sources needing attention" in app_js
    assert "renderFieldFocus" in app_js
    assert "focusExceptionId" in app_js
    assert 'element("audit").scrollIntoView' in app_js
    assert "private_storage_uri" not in app_js
    assert "evidence_artifact_id" not in app_js
    assert "content_base64" not in app_js

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
