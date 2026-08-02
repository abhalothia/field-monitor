from pathlib import Path
import re


def test_manager_assets_define_a_four_view_farm_command_and_first_farm_check():
    root = Path(__file__).resolve().parents[2] / "ffl" / "static" / "manager"
    index_html = (root / "index.html").read_text()
    app_js = (root / "app.js").read_text()

    assert "Farm command." in index_html
    assert "Review field signal" in index_html
    assert index_html.count('<button id="tab-') == 4
    assert 'data-view="home"' in index_html
    assert 'data-view="fields"' in index_html
    assert 'data-view="farmers"' in index_html
    assert 'data-view="tools"' in index_html
    assert "The facts we need before we steer." not in index_html
    assert "Pilot foundation" not in index_html
    assert "/api/v1/runtime" in app_js
    assert "/api/v1/exceptions/" in app_js
    assert "/api/v1/portfolio" in app_js
    assert "/api/v1/pilot/readiness" in app_js
    assert "/api/v1/pilot/setup/validate" in app_js
    assert "/api/v1/pilot/setup/accept" not in app_js
    assert "FFL_PILOT_SETUP_APPROVAL_TOKEN" not in app_js
    assert "Make the farm real." in index_html
    assert "Nothing is saved from this screen." in index_html
    assert "Check this farm pack" in index_html
    assert "renderPilotReadiness" in app_js
    assert "buildSetupProposal" in app_js
    assert "renderPreparedSetup" in app_js
    assert "Prepare first farm" in app_js
    assert "allocation.crop_name" in app_js
    assert "allocation.cultivar" in app_js
    assert "Risk &amp; action" in index_html
    assert "Data health" in index_html
    assert "Trials &amp; playbooks" in index_html
    assert "Imports awaiting review" in app_js
    assert "Tools are unavailable. Home is still usable." in app_js
    assert "fetch(runtimeUrl)" in app_js
    assert "fetch(portfolioUrl)" in app_js
    assert ".catch(renderPortfolioUnavailable)" in app_js
    assert "ledger.slice(0, 6)" in app_js
    assert "Sources needing attention" in app_js
    assert "renderFieldFocus" in app_js
    assert "renderRuntimeUnavailable" in app_js
    assert "showView" in app_js
    assert "moveTab" in app_js
    assert "renderPeople" in app_js
    assert "/morning-brief" in app_js
    assert "loadMorningBrief" in app_js
    assert "Next move · " in app_js
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
