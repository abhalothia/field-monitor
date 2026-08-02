from pathlib import Path
import re


def test_manager_assets_define_a_four_view_farm_command_and_first_farm_check():
    root = Path(__file__).resolve().parents[2] / "ffl" / "static" / "manager"
    index_html = (root / "index.html").read_text()
    app_js = (root / "app.js").read_text()

    assert "Farm command." in index_html
    assert "Open field work" in index_html
    assert "Loading today’s work…" in index_html
    assert "Open work" in index_html
    assert "Awaiting review" in index_html
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
    assert "/api/v1/data-lanes" in app_js
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
    assert "Five data lanes" in index_html
    assert "What is usable now, what is missing, and the next safe move." in index_html
    assert "Trials &amp; playbooks" in index_html
    assert "Field truth" in app_js
    assert "India Meteorological Department (IMD)" in app_js
    assert "Reviewed lab report + field measurement" in app_js
    assert "Copernicus Sentinel-2" in app_js
    assert "AGMARKNET / data.gov.in" in app_js
    assert "renderDataLanes" in app_js
    assert "fetch(dataLanesUrl)" in app_js
    assert "Tools are unavailable. Home is still usable." in app_js
    assert "fetch(runtimeUrl)" in app_js
    assert "fetch(portfolioUrl)" in app_js
    assert ".catch(renderPortfolioUnavailable)" in app_js
    assert "ledger.slice(0, 6)" in app_js
    assert "Public context never replaces field evidence." in app_js
    assert "renderFieldFocus" in app_js
    assert "renderTodayFallback" in app_js
    assert "renderToday(attention)" in app_js
    assert "Nothing needs a look right now." in app_js
    assert "District context only. Check it against the field." in app_js
    assert "operational_block_name" in app_js
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
    assert 'actions[exceptionRecord.status] : ""' in app_js
    assert 'nextAction(focus) || "Review the field report and its proof."' in app_js
    assert "Review the record and assign the next action." not in app_js

    for unsupported_status in ("assigned", "in_progress", "escalated"):
        assert "{0}:".format(unsupported_status) not in app_js
