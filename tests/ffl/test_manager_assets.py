from pathlib import Path


def test_manager_assets_define_the_fortune_coo_operating_views():
    root = Path(__file__).resolve().parents[2] / "ffl" / "static" / "manager"
    index_html = (root / "index.html").read_text()
    app_js = (root / "app.js").read_text()

    assert "Today" in index_html
    assert "Farms" in index_html
    assert "Farmers" in index_html
    assert "Field workers" in index_html
    assert "Inbox" in index_html
    assert "Settings" in index_html
    assert index_html.count('<button id="tab-') == 6

    assert 'id="today-date"' in index_html
    assert 'id="today-time"' in index_html
    assert 'id="weather-state"' in index_html
    assert 'id="home-visits-value"' in index_html
    assert 'id="home-overdue-value"' in index_html
    assert 'id="home-issues-value"' in index_html
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
    assert "renderFortuneMap" in app_js
    assert "renderMapCanvas" in app_js
    assert "setDirectoryView" in app_js
    assert "setInboxMode" in app_js
    assert "currentInboxMode" in app_js
    assert "currentFarmView" in app_js
    assert "renderPeople" in app_js
    assert "inboxRows" in app_js
    assert "Map detail comes only from the latest published, reviewed farm manifest." in app_js
    assert "Programme coverage never becomes a farm pin." in app_js

    assert 'name="location_hint"' in index_html
    assert 'id="setup-file"' in index_html
    assert "/assets/first-field-manifest.csv" in index_html
    assert "buildQuickSetup" in app_js
    assert "recognizeCsvFile" in app_js
    assert "ffl.manager.interface-locale" in app_js
    assert "X-FFL-Manager-Token" not in index_html + app_js
    assert "FFL_MANAGER_API_TOKEN" not in index_html + app_js
    assert "private_storage_uri" not in app_js
    assert "evidence_artifact_id" not in app_js
    assert "content_base64" not in app_js
