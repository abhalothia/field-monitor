from pathlib import Path


def test_manager_assets_define_a_fortune_coo_operating_loop_and_first_farm_check():
    root = Path(__file__).resolve().parents[2] / "ffl" / "static" / "manager"
    index_html = (root / "index.html").read_text()
    app_js = (root / "app.js").read_text()

    assert "Today." in index_html
    assert "Today" in index_html
    assert "Farms" in index_html
    assert "Farmers" in index_html
    assert "Field workers" in index_html
    assert "Inbox" in index_html
    assert "Settings" in index_html
    assert "One move" in index_html
    assert "Officer activity, visit gaps, and field signals determine the first move." in index_html
    assert "Operations board" not in index_html
    assert 'id="operations-board"' not in index_html
    assert "Verified fields" in index_html
    assert 'id="allocations-heading"' in index_html
    assert index_html.count('id="allocation-list"') == 1
    assert 'id="actions-allocation-context"' not in index_html
    assert 'id="open-focused-field"' not in index_html
    assert "Reading today’s network." in index_html
    assert index_html.count('<button id="tab-') == 6
    assert 'data-view="home"' in index_html
    assert 'data-view="farms"' in index_html
    assert 'data-view="farmers"' in index_html
    assert 'data-view="workers"' in index_html
    assert 'data-view="inbox"' in index_html
    assert 'data-view="settings"' in index_html
    assert 'data-view="programme"' not in index_html
    assert 'data-view="fields"' not in index_html
    assert 'data-view="map"' not in index_html
    assert 'data-view="actions"' not in index_html
    assert 'id="farmer-coverage"' in index_html
    assert 'id="farmer-observations"' not in index_html
    assert 'id="farmer-inputs"' not in index_html
    assert 'id="farmer-freshness"' not in index_html
    assert 'id="farmer-list"' not in index_html
    assert 'id="worker-activity"' in index_html
    assert 'id="worker-list"' not in index_html
    assert 'id="inbox-work-list"' not in index_html
    assert "Published coverage is a source aggregate. It does not prove a named farmer, farm, field, or input decision." in index_html
    assert "Tools" not in index_html
    assert "Next decision" in index_html
    assert "Manager access" in index_html
    assert "Data connections" not in index_html
    assert 'id="map-explorer"' not in index_html
    assert 'id="language-toggle"' in index_html
    assert 'id="action-dialog"' not in index_html
    assert "The facts we need before we steer." not in index_html
    assert "Pilot foundation" not in index_html
    assert "/api/v1/runtime" in app_js
    assert "/api/v1/portfolio" in app_js
    assert "/api/v1/trackolap/metrics" in app_js
    assert "/api/v1/trackolap/health" in app_js
    assert "/api/v1/pilot/quick-start/validate" in app_js
    assert "/api/v1/pilot/setup/accept" not in app_js
    assert "FFL_PILOT_SETUP_APPROVAL_TOKEN" not in app_js
    assert "Start with one field." in index_html
    assert "Six facts now." in index_html
    assert "Just the first field." in index_html
    assert "Village or PIN" in index_html
    assert 'name="location_hint"' in index_html
    assert 'name="village_name"' not in index_html
    assert 'name="pincode"' not in index_html
    assert "Use a CSV" in index_html
    assert 'id="setup-file"' in index_html
    assert "/assets/first-field-manifest.csv" in index_html
    assert "Check this field" in index_html
    assert "buildQuickSetup" in app_js
    assert "locationHint" in app_js
    assert "Add a village or six-digit PIN." in app_js
    assert "renderQuickSetup" in app_js
    assert "recognizeCsvFile" in app_js
    assert "Nothing from this file has left this device." in app_js
    assert "Purchase history recognized." in app_js
    assert "Farm / plot list recognized." in app_js
    assert "buildSetupProposal" not in app_js
    assert "renderPreparedSetup" not in app_js
    assert "Actions are unavailable. Home is still usable." in app_js
    assert "fetch(runtimeUrl)" in app_js
    assert "fetch(portfolioUrl)" in app_js
    assert ".catch(renderPortfolioUnavailable)" in app_js
    assert "ledger.slice(0, 1)" in app_js
    assert "renderDailyDirection" in app_js
    assert "active_officers_without_filed_visit" in app_js
    assert "active officers filed no visit" in app_js
    assert "renderAllocationCards" in app_js
    assert "renderRuntimeUnavailable" in app_js
    assert "showView" in app_js
    assert "moveTab" in app_js
    assert "renderWorkerActivity" in app_js
    assert "ffl.manager.interface-locale" in app_js
    assert "private_storage_uri" not in app_js
    assert "evidence_artifact_id" not in app_js
    assert "content_base64" not in app_js

    assert "Review the record and assign the next action." not in app_js
