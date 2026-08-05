from pathlib import Path
import subprocess


def _function_body(source, name, next_name):
    return source.split("function " + name, 1)[1].split("function " + next_name, 1)[0]


def test_manager_assets_define_the_fortune_coo_operating_views():
    root = Path(__file__).resolve().parents[2] / "ffl" / "static" / "manager"
    index_html = (root / "index.html").read_text()
    app_js = (root / "app.js").read_text()
    styles_css = (root / "styles.css").read_text()

    assert "Home" in index_html
    assert "Farms" in index_html
    assert "Farmers" in index_html
    assert "Field workers" in index_html
    assert "Inbox" in index_html
    assert "Settings" in index_html
    assert index_html.count('<button id="tab-') == 6
    assert 'id="farm-truth-open"' in index_html
    assert 'id="farm-truth-dialog"' in index_html
    assert 'id="farm-truth-refresh"' in index_html
    assert 'id="farm-truth-list"' in index_html
    assert 'id="farm-truth-detail"' in index_html
    assert 'id="farm-truth-accept-form"' in index_html
    assert 'id="farm-truth-needs-form"' in index_html
    assert 'id="farm-truth-reject-form"' in index_html

    assert 'id="today-date"' in index_html
    assert 'id="today-time"' in index_html
    assert 'id="weather-state"' in index_html
    assert 'id="sample-state"' not in index_html
    assert 'id="home-supply-value"' in index_html
    assert 'id="home-supply-label"' in index_html
    assert 'id="home-compliance-value"' in index_html
    assert 'id="home-interventions-value"' in index_html
    assert 'id="home-map-canvas"' in index_html
    assert "Where verified farms are." in index_html

    assert 'data-farm-view="map"' in index_html
    assert 'data-farm-view="cards"' in index_html
    assert 'data-farm-view="table"' in index_html
    assert 'id="farm-map-canvas"' in index_html
    assert 'id="allocation-list"' in index_html
    assert 'id="farm-table-body"' in index_html

    assert 'data-farmer-view="cards"' in index_html
    assert 'data-farmer-view="table"' in index_html
    assert 'id="farmer-list"' in index_html
    assert 'id="farmer-table-body"' in index_html
    assert 'data-worker-view="cards"' in index_html
    assert 'data-worker-view="table"' in index_html
    assert 'id="worker-list"' in index_html
    assert 'id="worker-table-body"' in index_html

    assert 'data-inbox-mode="priority"' in index_html
    assert 'data-inbox-mode="all"' in index_html
    assert 'id="portfolio-ledger"' in index_html
    assert "Operations board" not in index_html
    assert "renderOperationsBoard" not in app_js
    assert "loadPilotReadiness" not in app_js
    assert 'id="action-dialog"' not in index_html
    assert "Data connections" not in index_html

    assert "leaflet@1.9.4" in index_html
    assert "/api/v1/runtime" in app_js
    assert "/api/v1/portfolio" in app_js
    assert "/api/v1/fortune-map" in app_js
    assert "/api/v1/data-lanes" in app_js
    assert "renderTodayClock" in app_js
    assert "renderWeatherContext" in app_js
    assert "renderHomeMetrics" in app_js
    assert "formatPercent" in app_js
    assert "formatQuantity" in app_js
    assert "farmerReachNote" in app_js
    assert "purchaseShareNote" in app_js
    assert "chemicalRecordNote" in app_js
    assert "cropSignalsNote" in app_js
    assert "renderFortuneMap" in app_js
    assert "renderMapCanvas" in app_js
    assert "setDirectoryView" in app_js
    assert "setInboxMode" in app_js
    assert "currentInboxMode" in app_js
    assert "currentFarmView" in app_js
    assert "renderPeople" in app_js
    assert "inboxRows" in app_js
    assert "sampleRuntime" in app_js
    assert "sampleProgramme" in app_js
    assert "samplePortfolio" in app_js
    assert "sampleMap" in app_js
    assert "North Block" in app_js
    assert "Jewar Model Farm" in app_js
    assert "Dargava, Gabhana, Aligarh" in app_js
    assert "Asha Devi" in app_js
    assert "Ravi Kumar" in app_js
    assert 'id="record-dialog"' in index_html
    assert 'id="record-dialog-action"' in index_html
    assert 'id="inbox-filter-clear"' in index_html
    assert "openRecordDialog" in app_js
    assert "updateRecordRoute" in app_js
    assert "restoreConnectedRecord" in app_js
    assert "connectFarm" in app_js
    assert "popstate" in app_js
    assert "record_id" in app_js
    assert "viewRelatedDecisions" in app_js
    assert "data-record-kind" in app_js
    assert "directory-card-metric" in app_js
    assert "sampleWeather" in app_js
    assert "mapPrivacyNote" in app_js
    assert "noReviewedFarmer" in app_js
    assert "noReviewedWorker" in app_js
    assert "नमूना दृश्य" not in index_html
    assert "Map detail comes only from the latest published, reviewed farm manifest." in app_js
    assert "Programme coverage never becomes a farm pin." in app_js

    for endpoint in (
        '"/api/v1/farm-truth/refresh"',
        '"/api/v1/farm-truth/cases"',
        '"/accept"',
        '"/needs-evidence"',
        '"/reject"',
    ):
        assert endpoint in app_js
    for copy_key in (
        "reviewCandidates", "farmTruthTitle", "farmTruthEmpty", "farmTruthUnavailable",
        "acceptCandidate", "needsEvidence", "rejectCandidate", "evidenceNeeded",
        "reviewSaved", "reviewNext", "reviewReason", "reviewRefresh", "reviewSeason",
        "chooseReviewSeason", "farmTruthLoading", "reviewFailed",
        "reviewContextLabel", "activeSeason",
    ):
        assert app_js.count(copy_key + ":") == 2
    assert "loadFarmTruthCases" in app_js
    assert "loadFarmTruthCaseDetail" in app_js
    assert "refreshFarmTruthCases" in app_js
    assert "submitFarmTruthDecision" in app_js
    assert "farmTruthInboxRows" in app_js
    assert "farmTruthContexts" in app_js
    assert "selectedFarmTruthContextKey" in app_js
    assert ".farm-truth-dialog" in styles_css
    assert ".evidence-chips" in styles_css
    assert ".farm-truth-fields" in styles_css

    render_best_map = app_js.split("function renderBestMap()", 1)[1].split(
        "function renderFortuneMapUnavailable", 1
    )[0]
    assert "sourceBoardFeatureCollection()" not in render_best_map
    assert "sourcePoints" not in render_best_map
    assert "reviewed.concat" not in render_best_map
    assert "currentFortuneMap" in render_best_map
    assert "sourceBoardFeatureCollection" not in app_js
    assert "currentSourceBoard.map" not in app_js
    assert "renderFortuneMap(sampleMap())" not in app_js

    assert "Start with one field" not in index_html + app_js
    assert "Prepare first farm" not in index_html + app_js
    assert "first-field-manifest" not in index_html + app_js
    assert "ffl.manager.interface-locale" in app_js
    assert "X-FFL-Manager-Token" not in index_html + app_js
    assert "FFL_MANAGER_API_TOKEN" not in index_html + app_js
    assert "private_storage_uri" not in app_js
    assert "evidence_artifact_id" not in app_js
    assert "content_base64" not in app_js


def test_farm_truth_review_behaviors_fail_closed_and_retain_feedback():
    root = Path(__file__).resolve().parents[2] / "ffl" / "static" / "manager"
    index_html = (root / "index.html").read_text()
    app_js = (root / "app.js").read_text()

    contexts = _function_body(app_js, "farmTruthContexts()", "renderFarmTruthContextChooser()")
    assert "currentPortfolio.scope" in contexts
    assert "active_allocations" in contexts
    assert "active_farms" in contexts
    assert "currentRuntime" not in contexts
    assert "label:" in contexts
    assert "label: (unit.name || unit.id) + \" · \" + item.season_id" not in contexts
    assert "labelCounts" in contexts
    assert "labelCounts[context.label] > 1" in contexts

    chooser = _function_body(app_js, "renderFarmTruthContextChooser()", "farmTruthContext()")
    assert "contexts.length === 1" in chooser
    assert "selectedFarmTruthContextKey" in chooser
    assert "contexts[0]" not in chooser
    open_review = _function_body(
        app_js, "openFarmTruthReview()", "submitFarmTruthDecision(event, decision)"
    )
    assert 'if (contexts.length === 1)' in open_review
    assert "refreshFarmTruthCases()" in open_review
    assert "renderFarmTruthUnavailable()" in open_review
    render_portfolio = _function_body(app_js, "renderPortfolio(portfolio)", "sourceBoardReady()")
    assert "renderFarmTruthContextChooser()" in render_portfolio
    assert "refreshFarmTruthCases()" not in render_portfolio

    best_map = _function_body(app_js, "renderBestMap()", "renderFortuneMapUnavailable()")
    assert "sampleMode" not in best_map
    assert "sampleLocation" not in best_map
    assert "sampleGeometry" not in best_map
    unavailable_map = _function_body(app_js, "renderFortuneMapUnavailable()", "loadFortuneMap()")
    assert 't("noReviewedGeometry")' in unavailable_map
    runtime_unavailable = _function_body(app_js, "renderRuntimeUnavailable()", "loadActionCentre()")
    assert "renderFortuneMapUnavailable()" in runtime_unavailable
    assert "renderFortuneMap({" not in runtime_unavailable

    assert index_html.index('id="farm-truth-feedback"') < index_html.index(
        'id="farm-truth-decision-panel"'
    )
    detail = _function_body(app_js, "renderFarmTruthDetail()", "renderFarmTruthUnavailable()")
    assert 'setFarmTruthFeedback("")' not in detail
    decision = _function_body(app_js, "submitFarmTruthDecision(event, decision)", "setSampleMode(enabled)")
    assert "showFarmTruthDecisionSuccess" in decision

    close_unlock = _function_body(app_js, "closeManagerSessionDialog()", "toggleManagerSession()")
    assert "farmTruthOpenPending = false" in close_unlock
    assert "dialog.close()" in close_unlock
    close_handler = app_js.split('element("close-manager-session").addEventListener', 1)[1].split(
        'element("manager-session-form").addEventListener', 1
    )[0]
    assert close_handler.count("closeManagerSessionDialog") == 2

    unavailable = _function_body(app_js, "renderFarmTruthUnavailable()", "loadFarmTruthCaseDetail(caseId)")
    assert "error.message" not in unavailable
    assert 't("farmTruthUnavailable")' in unavailable
    assert "error.message" not in decision
    assert 't("reviewFailed")' in decision


def test_manager_app_farm_truth_behaviors_execute_in_node():
    harness = Path(__file__).with_name("manager_app_behavior_test.js")
    result = subprocess.run(
        ["node", str(harness)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "manager Farm Truth behavior harness passed" in result.stdout
