from pathlib import Path


def test_manager_assets_define_the_fortune_coo_operating_views():
    root = Path(__file__).resolve().parents[2] / "ffl" / "static" / "manager"
    index_html = (root / "index.html").read_text()
    app_js = (root / "app.js").read_text()

    assert "Home" in index_html
    assert "Farms" in index_html
    assert "Farmers" in index_html
    assert "Field workers" in index_html
    assert "Inbox" in index_html
    assert "Settings" in index_html
    assert index_html.count('<button id="tab-') == 6

    assert 'id="today-date"' in index_html
    assert 'id="today-time"' in index_html
    assert 'id="weather-state"' in index_html
    assert 'id="sample-state"' not in index_html
    assert 'id="home-supply-value"' in index_html
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
    assert "openInterventionCount" in app_js
    assert "purchaseDataUnavailable" in app_js
    assert "pesticideProofUnavailable" in app_js
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
    assert "नमूना दृश्य" not in index_html
    assert "Map detail comes only from the latest published, reviewed farm manifest." in app_js
    assert "Programme coverage never becomes a farm pin." in app_js

    assert "Start with one field" not in index_html + app_js
    assert "Prepare first farm" not in index_html + app_js
    assert "first-field-manifest" not in index_html + app_js
    assert "ffl.manager.interface-locale" in app_js
    assert "X-FFL-Manager-Token" not in index_html + app_js
    assert "FFL_MANAGER_API_TOKEN" not in index_html + app_js
    assert "private_storage_uri" not in app_js
    assert "evidence_artifact_id" not in app_js
    assert "content_base64" not in app_js
