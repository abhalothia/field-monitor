from pathlib import Path


def test_manager_assets_define_a_fortune_coo_operating_loop_and_first_farm_check():
    root = Path(__file__).resolve().parents[2] / "ffl" / "static" / "manager"
    index_html = (root / "index.html").read_text()
    app_js = (root / "app.js").read_text()

    assert "Today." in index_html
    assert "Briefing" in index_html
    assert "Programme" in index_html
    assert "Crop work" in index_html
    assert "Places" in index_html
    assert "Decisions" in index_html
    assert "System" in index_html
    assert "Open field work" in index_html
    assert "Field pulse" in index_html
    assert "Operations board" in index_html
    assert "Record health, not a performance score." in index_html
    assert 'id="operations-board"' in index_html
    assert "Crop allocations" in index_html
    assert 'id="allocations-heading"' in index_html
    assert index_html.count('id="allocation-list"') == 1
    assert "Evidence / record" in index_html
    assert 'id="actions-allocation-context"' in index_html
    assert 'id="open-focused-field"' in index_html
    assert "Loading the field." in index_html
    assert "Open work" in index_html
    assert "Awaiting review" in index_html
    assert index_html.count('<button id="tab-') == 6
    assert 'data-view="home"' in index_html
    assert 'data-view="programme"' in index_html
    assert 'data-view="fields"' in index_html
    assert 'data-view="farmers"' not in index_html
    assert 'data-view="map"' in index_html
    assert 'data-view="actions"' in index_html
    assert 'data-view="settings"' in index_html
    assert 'id="programme-coverage"' in index_html
    assert 'id="programme-observations"' in index_html
    assert 'id="programme-inputs"' in index_html
    assert 'id="programme-freshness"' in index_html
    assert 'id="programme-people"' in index_html
    assert "Source programme context does not prove a farm, field, work completion, or input compliance." in index_html
    assert "Tools" not in index_html
    assert "Actions" in index_html
    assert "Data connections" in index_html
    assert 'id="open-map"' in index_html
    assert 'id="map-explorer"' in index_html
    assert "How this map earns detail" in index_html
    assert "A village name never becomes a field pin." in index_html
    assert "Network map" in index_html
    assert "Public coverage only" in index_html
    assert 'id="language-toggle"' in index_html
    assert 'id="action-dialog"' in index_html
    assert "The facts we need before we steer." not in index_html
    assert "Pilot foundation" not in index_html
    assert "/api/v1/runtime" in app_js
    assert 'allocationCalendarUrl = "/api/v1/allocations/"' in app_js
    assert '"/calendar"' in app_js
    assert "/api/v1/exceptions/" in app_js
    assert "/api/v1/portfolio" in app_js
    assert "/api/v1/data-lanes" in app_js
    assert "/api/v1/operating-profile" in app_js
    assert "/api/v1/trackolap/metrics" in app_js
    assert "/api/v1/trackolap/health" in app_js
    assert "Unlock manager actions in System to view Fortune programme data." in app_js
    assert "review cue only; not an application recommendation or compliance verdict" in app_js
    assert "Observation confidence is low. Fewer detections do not mean risk has fallen." in app_js
    assert "/api/v1/pilot/readiness" in app_js
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
    assert "renderPilotReadiness" in app_js
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
    assert "Operating right" not in index_html
    assert "Right starts" not in index_html
    assert "First work" not in index_html
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
    assert "Actions are unavailable. Home is still usable." in app_js
    assert "fetch(runtimeUrl)" in app_js
    assert "fetch(portfolioUrl)" in app_js
    assert ".catch(renderPortfolioUnavailable)" in app_js
    assert "ledger.slice(0, 6)" in app_js
    assert "Public context never replaces field evidence." in app_js
    assert "renderFieldPulse" in app_js
    assert "renderOperationsBoard" in app_js
    assert "Farmer programme" in app_js
    assert "Source programme context, not a canonical farmer record." in app_js
    assert "data-board-view" in app_js
    assert "renderAllocationCards" in app_js
    assert "allocationSnapshot" in app_js
    assert "loadAllocationCalendars" in app_js
    assert "selectAllocation" in app_js
    assert "renderActionAllocationContext" in app_js
    assert "Evidence attached" in app_js
    assert "evidence detail unavailable" in app_js
    assert "No risk or action is linked to this crop allocation." in app_js
    assert "latest_field_update" in app_js
    assert "renderTodayFallback" in app_js
    assert "renderToday(attention)" in app_js
    assert "Nothing needs a look right now." in app_js
    assert "Field ask" in app_js
    assert "field_information_request" in app_js
    assert "field proof required" in app_js
    assert "The linked work stays open until a human closes it." in app_js
    assert "District context only. Check it against the field." in app_js
    assert "operational_block_name" in app_js
    assert "renderRuntimeUnavailable" in app_js
    assert "showView" in app_js
    assert "moveTab" in app_js
    assert "renderPeople" in app_js
    assert "person_operating_relationships" in app_js
    assert "Field relationship setup is pending." in app_js
    assert "/morning-brief" in app_js
    assert "loadMorningBrief" in app_js
    assert "The latest field record is visible here" in app_js
    assert "focusExceptionId" in app_js
    assert 'element("audit").scrollIntoView' in app_js
    assert "renderOperatingProfile" in app_js
    assert "renderMapExplorer" in app_js
    assert 'showView("map")' in app_js
    assert "map_embed_url" in app_js
    assert "currentAttention" in app_js
    assert "openActionDetail" in app_js
    assert "data-first-farm" in app_js
    assert "ffl.manager.interface-locale" in app_js
    assert "Farm records remain exactly as entered." in index_html
    assert "private_storage_uri" not in app_js
    assert "evidence_artifact_id" not in app_js
    assert "content_base64" not in app_js

    assert "Review the record and assign the next action." not in app_js
