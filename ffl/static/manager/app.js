(function () {
  "use strict";

  var runtimeUrl = "/api/v1/runtime";
  var portfolioUrl = "/api/v1/portfolio";
  var fortuneMapUrl = "/api/v1/fortune-map";
  var allocationCalendarUrl = "/api/v1/allocations/";
  var dataLanesUrl = "/api/v1/data-lanes";
  var operatingProfileUrl = "/api/v1/operating-profile";
  var pilotReadinessUrl = "/api/v1/pilot/readiness";
  var managerSessionStatusUrl = "/api/v1/manager-session/status";
  var managerSessionLoginUrl = "/api/v1/manager-session/login";
  var managerSessionLogoutUrl = "/api/v1/manager-session/logout";
  var trackolapMetricsUrl = "/api/v1/trackolap/metrics";
  var trackolapHealthUrl = "/api/v1/trackolap/health";
  var currentRuntime = null;
  var currentPortfolio = null;
  var currentProgramme = null;
  var currentFortuneMap = null;
  var currentView = "home";
  var currentOperatingUnitName = "";
  var currentFarmView = "map";
  var currentFarmerView = "cards";
  var currentWorkerView = "cards";
  var currentInboxMode = "priority";
  var leafletMaps = {};
  var sampleMode = false;
  var inboxOwnerId = null;
  var allocationCalendars = {};
  var focusedAllocationId = null;
  var allocationCalendarRequest = 0;
  var pendingAction = null;
  var focusExceptionId = null;
  var focusTargetView = "farms";
  var managerSessionAuthenticated = false;
  var localeStorageKey = "ffl.manager.interface-locale";
  var interfaceLocale = window.localStorage.getItem(localeStorageKey) === "hi" ? "hi" : "en";
  var copy = {
    en: {
      navHome: "Today", navFarms: "Farms", navFarmers: "Farmers", navWorkers: "Field workers", navInbox: "Inbox", navSettings: "Settings",
      refresh: "Refresh", pageTitle: "Today.", fieldPulse: "Daily direction", lastUpdate: "Last update", from: "From",
      openFieldWork: "Open field workers", today: "Today", openWork: "Open work", awaitingReview: "Awaiting review",
      currentFields: "Current fields", work: "Work", selectedSignal: "Selected signal", review: "Review",
      priority: "Priority", riskAction: "Risk & action", learning: "Learning", trialsPlaybooks: "Trials & playbooks",
      operatingProfile: "Operating profile", coverage: "Coverage", interface: "Interface", language: "Language",
      languageHelp: "Choose Hindi or English for the interface. Farm records remain exactly as entered.",
      dataConnections: "Data connections", fiveDataLanes: "Five data lanes",
      lanesIntro: "What is usable now, what is missing, and the next safe move.", nextMove: "Next move",
      fieldAsk: "Field ask", fieldProofRequired: "field proof required", fieldUpdateRequested: "field update requested",
      noFieldPerson: "No field person assigned", due: "due", fieldAskNeedsReview: "needs manager review",
      fieldAskReady: "is reviewed; delivery stays independently gated", awaitingFieldAnswer: "Awaiting a reviewable field answer from",
      checkDelivery: "Check delivery eligibility or cancel and reissue it. Do not assume an answer.",
      reviewFieldAnswer: "Review any response and retained proof. The linked work stays open until a human closes it.",
      openFieldAsks: "Open field asks"
    },
    hi: {
      navHome: "आज", navFarms: "खेत", navFarmers: "किसान", navWorkers: "फील्ड टीम", navInbox: "इनबॉक्स", navSettings: "सेटिंग्स",
      refresh: "ताज़ा करें", pageTitle: "आज।", fieldPulse: "आज की दिशा", lastUpdate: "आख़िरी अपडेट", from: "किससे",
      openFieldWork: "फील्ड टीम खोलें", today: "आज", openWork: "खुला काम", awaitingReview: "समीक्षा के लिए",
      currentFields: "मौजूदा खेत", work: "काम", selectedSignal: "चुना हुआ संकेत", review: "समीक्षा",
      priority: "प्राथमिकता", riskAction: "जोखिम और अगला काम", learning: "सीख", trialsPlaybooks: "परीक्षण और तरीके",
      operatingProfile: "ऑपरेटिंग प्रोफ़ाइल", coverage: "कवरेज", interface: "इंटरफ़ेस", language: "भाषा",
      languageHelp: "इंटरफ़ेस के लिए हिंदी या अंग्रेज़ी चुनें। खेत के रिकॉर्ड जैसे दर्ज किए गए हैं वैसे ही रहेंगे।",
      dataConnections: "डेटा कनेक्शन", fiveDataLanes: "पांच डेटा लेन",
      lanesIntro: "क्या उपयोगी है, क्या नहीं है, और अगला सुरक्षित कदम।", nextMove: "अगला कदम",
      fieldAsk: "खेत की जानकारी", fieldProofRequired: "खेत का प्रमाण चाहिए", fieldUpdateRequested: "खेत का अपडेट चाहिए",
      noFieldPerson: "कोई फील्ड व्यक्ति तय नहीं", due: "समय", fieldAskNeedsReview: "को प्रबंधक की समीक्षा चाहिए",
      fieldAskReady: "की समीक्षा हो चुकी है; भेजना अलग से स्वीकृत होगा", awaitingFieldAnswer: "समीक्षा योग्य उत्तर की प्रतीक्षा",
      checkDelivery: "भेजने की पात्रता जाँचें या इसे रद्द करके फिर से जारी करें। उत्तर मान कर न चलें।",
      reviewFieldAnswer: "किसी भी उत्तर और सुरक्षित प्रमाण की समीक्षा करें। मानव बंद होने तक जुड़ा काम खुला रहता है।",
      openFieldAsks: "खेत की जानकारी खोलें"
    }
  };

  function element(id) {
    return document.getElementById(id);
  }

  function text(value) {
    return value === null || value === undefined || value === "" ? "Not assigned" : String(value);
  }

  function t(key) {
    return (copy[interfaceLocale] && copy[interfaceLocale][key]) || (copy.en[key] || key);
  }

  function applyLanguage() {
    document.documentElement.lang = interfaceLocale === "hi" ? "hi" : "en";
    Array.prototype.forEach.call(document.querySelectorAll("[data-i18n]"), function (node) {
      node.textContent = t(node.getAttribute("data-i18n"));
    });
    element("language-toggle").textContent = interfaceLocale === "hi" ? "EN" : "हिं";
    element("language-toggle").setAttribute(
      "aria-label", interfaceLocale === "hi" ? "Switch interface language to English" : "इंटरफ़ेस भाषा हिंदी में बदलें"
    );
    Array.prototype.forEach.call(document.querySelectorAll("[data-locale]"), function (button) {
      var selected = button.getAttribute("data-locale") === interfaceLocale;
      button.classList.toggle("is-selected", selected);
      button.setAttribute("aria-pressed", String(selected));
    });
    renderPageIntro();
  }

  function setLocale(locale) {
    interfaceLocale = locale === "hi" ? "hi" : "en";
    window.localStorage.setItem(localeStorageKey, interfaceLocale);
    applyLanguage();
    // Repaint the manager-safe summaries that use localized status language;
    // underlying farm records and reviewed request copy stay exactly as stored.
    if (currentPortfolio) {
      renderPortfolio(currentPortfolio);
    }
    if (currentProgramme) {
      renderProgramme(currentProgramme.metrics, currentProgramme.health);
    }
    renderTodayClock();
  }

  function setManagerSessionFeedback(message) {
    var feedback = element("manager-session-feedback");
    feedback.textContent = message || "";
    feedback.hidden = !message;
  }

  function renderManagerSessionStatus(session) {
    managerSessionAuthenticated = Boolean(session && session.authenticated === true);
    var status = element("manager-session-status");
    var action = element("manager-session-action");
    status.classList.toggle("is-unlocked", managerSessionAuthenticated);
    status.textContent = managerSessionAuthenticated ?
      "Manager actions are unlocked briefly on this browser." :
      "Manager actions are locked on this browser.";
    action.textContent = managerSessionAuthenticated ? "Lock manager actions" : "Unlock manager actions";
  }

  function loadManagerSessionStatus() {
    return fetch(managerSessionStatusUrl, { credentials: "same-origin" })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("Manager status is unavailable.");
        }
        return response.json();
      })
      .then(renderManagerSessionStatus)
      .catch(function () {
        renderManagerSessionStatus({ authenticated: false });
      });
  }

  function openManagerSessionDialog() {
    setManagerSessionFeedback("");
    var dialog = element("manager-session-dialog");
    if (!dialog.open) {
      dialog.showModal();
    }
    element("manager-session-secret").focus();
  }

  function submitManagerSession(event) {
    event.preventDefault();
    var form = event.currentTarget;
    if (!form.reportValidity()) {
      return;
    }
    setManagerSessionFeedback("");
    var submit = element("submit-manager-session");
    submit.disabled = true;
    submit.textContent = "Unlocking…";
    // The secret exists only in the form/request body.  It is deliberately
    // never written to localStorage, sessionStorage, a URL, or an API header.
    fetch(managerSessionLoginUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ secret: formValue(form, "secret") })
    })
      .then(function (response) {
        return response.json().then(function (body) {
          if (!response.ok) {
            throw new Error(body.detail || "Manager access could not be unlocked.");
          }
          return body;
        });
      })
      .then(function () {
        form.reset();
        element("manager-session-dialog").close();
        return loadManagerSessionStatus();
      })
      .then(loadActionCentre)
      .catch(function (error) {
        form.reset();
        setManagerSessionFeedback(error.message || "Manager access could not be unlocked.");
      })
      .finally(function () {
        submit.disabled = false;
        submit.textContent = "Unlock actions";
      });
  }

  function toggleManagerSession() {
    if (!managerSessionAuthenticated) {
      openManagerSessionDialog();
      return;
    }
    element("manager-session-action").disabled = true;
    fetch(managerSessionLogoutUrl, { method: "POST", credentials: "same-origin" })
      .then(function () { return loadManagerSessionStatus(); })
      .then(loadActionCentre)
      .finally(function () {
        element("manager-session-action").disabled = false;
      });
  }

  function setSampleMode(enabled) {
    sampleMode = Boolean(enabled);
    element("sample-state").hidden = !sampleMode;
  }

  function sampleRuntime() {
    return {
      operating_unit: { name: "Fortune Rice" },
      allocations: [{ id: "sample-north-block", operational_block_name: "North Block", crop_name: "Pusa Basmati 1121", cultivar: "1121" }],
      people: [
        { id: "sample-asha", name: "Asha Devi", role: "grower" },
        { id: "sample-ravi", name: "Ravi Kumar", role: "field_operator" }
      ],
      work_items: [{ id: "sample-visit", allocation_id: "sample-north-block", title: "Check stem borer cluster", owner_id: "sample-ravi", due_at: new Date().toISOString(), status: "planned" }],
      exceptions: [],
      latest_field_update: null,
      person_operating_relationships: {
        availability: "available",
        items: [
          { person_id: "sample-asha", role: "grower", scope_name: "North Block" },
          { person_id: "sample-ravi", role: "field operator", scope_name: "North Block" }
        ]
      }
    };
  }

  function sampleProgramme() {
    return {
      coverage: { taken_kit: 2592, visited: 1941, recent: 1585, overdue: 1007, never_visited: 651 },
      visits: { filed_on_reporting_day: 5, filing_officers: 2, active_officers: 24, active_officers_without_filed_visit: 22 },
      issues: {
        window_days: 7,
        observation_count: 545,
        by_issue: [
          { issue_code: "stem borer", count: 215, highest_severity: "high" },
          { issue_code: "leaf folder", count: 265, highest_severity: "moderate" }
        ]
      },
      freshness: { status: "available", age_hours: 1 }
    };
  }

  function samplePortfolio() {
    return {
      risk_action_ledger: {
        items: [{
          severity: "high", action: "review field signal", entity: { type: "exception_record", id: "sample-stem-borer" },
          status: "reported", title: "Review stem borer cluster", allocation_id: "sample-north-block",
          owner_id: "sample-ravi", observed_at: new Date().toISOString()
        }]
      }
    };
  }

  function sampleMap() {
    return {
      type: "FeatureCollection",
      features: [{
        type: "Feature",
        geometry: { type: "Point", coordinates: [77.5555503, 28.5534523] },
        properties: { plot_label: "North Block", crop_name: "Pusa Basmati 1121", cultivar: "1121", area_hectares: 2.5, location_precision: "sample" }
      }]
    };
  }

  function renderSampleWeather() {
    element("weather-state").textContent = "31°C · partly cloudy";
    element("weather-note").textContent = "Sample local context";
  }

  function formatTime(value) {
    if (!value) {
      return "Not scheduled";
    }
    var date = new Date(value);
    return isNaN(date.getTime()) ? value : date.toLocaleString(interfaceLocale === "hi" ? "hi-IN" : "en-IN");
  }

  function formatCount(value) {
    var count = Number(value);
    if (!isFinite(count) || count < 0) {
      return "—";
    }
    return Math.round(count).toLocaleString(interfaceLocale === "hi" ? "hi-IN" : "en-IN");
  }

  function formatAgeHours(value) {
    var hours = Number(value);
    if (!isFinite(hours) || hours < 0) {
      return "No published timestamp";
    }
    if (hours < 1) {
      return "Under 1 hour";
    }
    return Math.round(hours) + (Math.round(hours) === 1 ? " hour" : " hours");
  }

  function programmeFact(label, value) {
    return "<div><dt>" + escapeHtml(label) + "</dt><dd>" + escapeHtml(formatCount(value)) + "</dd></div>";
  }

  function workerFact(label, value) {
    return "<div><dt>" + escapeHtml(label) + "</dt><dd>" + escapeHtml(value) + "</dd></div>";
  }

  function renderTodayClock() {
    var now = new Date();
    var locale = interfaceLocale === "hi" ? "hi-IN" : "en-IN";
    element("today-date").textContent = now.toLocaleDateString(locale, {
      weekday: "long", day: "numeric", month: "long", timeZone: "Asia/Kolkata"
    });
    element("today-time").textContent = now.toLocaleTimeString(locale, {
      hour: "numeric", minute: "2-digit", timeZone: "Asia/Kolkata"
    });
  }

  function renderWeatherContext(snapshot) {
    if (sampleMode) {
      renderSampleWeather();
      return;
    }
    var lanes = snapshot && Array.isArray(snapshot.lanes) ? snapshot.lanes : [];
    var weather = lanes.filter(function (lane) { return lane.key === "weather"; })[0];
    if (!weather) {
      element("weather-state").textContent = "Weather pending";
      element("weather-note").textContent = "";
      return;
    }
    var ready = weather.status === "context_available";
    element("weather-state").textContent = ready ? "Weather context ready" : "Weather pending";
    element("weather-note").textContent = ready ? weather.fact : "";
  }

  function renderWeatherUnavailable() {
    if (sampleMode) {
      renderSampleWeather();
      return;
    }
    element("weather-state").textContent = "Weather pending";
    element("weather-note").textContent = "";
  }

  function setHomeMetric(valueId, noteId, value, note) {
    element(valueId).textContent = value;
    element(noteId).textContent = note;
  }

  function renderHomeMetrics() {
    var metrics = currentProgramme && currentProgramme.metrics ? currentProgramme.metrics : null;
    var visits = metrics && metrics.visits ? metrics.visits : null;
    var coverage = metrics && metrics.coverage ? metrics.coverage : null;
    setHomeMetric(
      "home-visits-value", "home-visits-note",
      visits ? formatCount(visits.filed_on_reporting_day) : "—",
      visits ? "filed today" : "loading"
    );
    setHomeMetric(
      "home-overdue-value", "home-overdue-note",
      coverage ? formatCount(coverage.overdue) : "—",
      coverage ? "farmers need a visit" : "loading"
    );
    var issues = metrics && metrics.issues ? metrics.issues : null;
    var highRiskIssues = issues && Array.isArray(issues.by_issue) ? issues.by_issue.reduce(function (total, issue) {
      return ["critical", "high"].indexOf(issue.highest_severity) !== -1 ? total + (Number(issue.count) || 0) : total;
    }, 0) : null;
    setHomeMetric(
      "home-issues-value", "home-issues-note",
      highRiskIssues === null ? "—" : formatCount(highRiskIssues),
      highRiskIssues === null ? "loading" : "high / critical · 7 days"
    );
  }

  function renderWorkerActivity() {
    var metrics = currentProgramme && currentProgramme.metrics ? currentProgramme.metrics : null;
    if (!metrics) {
      element("worker-boundary").textContent = "";
      element("worker-activity").textContent = managerSessionAuthenticated ?
        "Daily filing is unavailable." : "Daily filing is loading.";
      renderHomeMetrics();
      return;
    }
    var visits = metrics.visits || {};
    var freshness = metrics.freshness || {};
    var active = Number(visits.active_officers) || 0;
    var filed = Number(visits.filed_on_reporting_day) || 0;
    var filing = Number(visits.filing_officers) || 0;
    var missing = Number(visits.active_officers_without_filed_visit) || 0;
    element("worker-boundary").textContent = "";
    element("worker-activity").textContent = formatCount(filed) + " visits filed today · " +
      formatCount(missing) + " active officers have not filed.";
    renderHomeMetrics();
  }

  function programmeWarningCopy(code) {
    if (code === "low_observation_confidence") {
      return "Observation confidence is low. Fewer detections do not mean risk has fallen.";
    }
    return "Review source limitation: " + readable(code) + ".";
  }

  function renderProgrammeLocked() {
    if (sampleMode) {
      renderProgramme(sampleProgramme(), { state: "sample" });
      return;
    }
    currentProgramme = null;
    element("farmer-boundary").textContent = "";
    element("farmer-coverage").textContent = "Coverage is loading.";
    renderWorkerActivity();
    renderDailyDirection();
    renderHomeMetrics();
  }

  function renderProgrammeUnavailable() {
    if (sampleMode) {
      renderProgramme(sampleProgramme(), { state: "sample" });
      return;
    }
    currentProgramme = null;
    element("farmer-boundary").textContent = "";
    element("farmer-coverage").textContent = "Coverage is unavailable.";
    renderWorkerActivity();
    renderDailyDirection();
    renderHomeMetrics();
  }

  function renderProgramme(metrics, health) {
    var coverage = metrics && metrics.coverage ? metrics.coverage : {};

    currentProgramme = { metrics: metrics || {}, health: health || {} };
    renderDailyDirection();
    element("farmer-boundary").textContent = "";
    element("farmer-coverage").textContent = formatCount(coverage.overdue) + " farmers overdue · " +
      formatCount(coverage.never_visited) + " never visited · " + formatCount(coverage.recent) +
      " reached in 14 days.";
    renderWorkerActivity();
    renderHomeMetrics();
  }

  function loadProgramme() {
    if (!managerSessionAuthenticated) {
      renderProgrammeLocked();
      return Promise.resolve();
    }
    return Promise.all([
      fetch(trackolapMetricsUrl, { credentials: "same-origin" }),
      fetch(trackolapHealthUrl, { credentials: "same-origin" })
    ])
      .then(function (responses) {
        if (!responses[0].ok || !responses[1].ok) {
          throw new Error("Programme context is unavailable.");
        }
        return Promise.all([responses[0].json(), responses[1].json()]);
      })
      .then(function (payloads) {
        renderProgramme(payloads[0], payloads[1]);
      })
      .catch(renderProgrammeUnavailable);
  }

  function isOpenException(exceptionRecord) {
    return ["resolved", "accepted_risk"].indexOf(exceptionRecord.status) === -1;
  }

  function isOpenWork(workItem) {
    return ["accepted", "completed", "cancelled"].indexOf(workItem.status) === -1;
  }

  function isOverdue(workItem) {
    return isOpenWork(workItem) && workItem.due_at && new Date(workItem.due_at).getTime() < Date.now();
  }

  function setHtml(id, markup) {
    element(id).innerHTML = markup;
  }

  function escapeHtml(value) {
    return text(value).replace(/[&<>'"]/g, function (character) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", "\"": "&quot;" }[character];
    });
  }

  function readable(value) {
    return text(value).replace(/_/g, " ");
  }

  function listedItems(summary) {
    return summary && Array.isArray(summary.items) ? summary.items : [];
  }

  function safeSeverity(value) {
    return ["critical", "high", "medium", "low", "info"].indexOf(value) === -1 ? "medium" : value;
  }

  function formValue(form, name) {
    return String(new FormData(form).get(name) || "").trim();
  }

  function pageMeta(viewName) {
    var labels = {
      home: { title: "Today.", detail: currentOperatingUnitName || "What needs to move today." },
      farms: { title: "Farms.", detail: "Ground truth from reviewed farm and field records." },
      farmers: { title: "Farmers.", detail: "Coverage context and reviewed farmer relationships." },
      workers: { title: "Field workers.", detail: "Daily activity and reviewed ownership." },
      inbox: { title: "Inbox.", detail: "Decisions, work, and follow-through." },
      settings: { title: "Settings.", detail: "Access and source boundaries." }
    };
    return labels[viewName] || labels.home;
  }

  function renderPageIntro() {
    var meta = pageMeta(currentView);
    element("page-title").textContent = meta.title;
    element("operating-unit").textContent = meta.detail;
  }

  function showView(viewName) {
    currentView = viewName;
    var tabs = document.querySelectorAll(".command-tab");
    var views = document.querySelectorAll(".command-view");
    Array.prototype.forEach.call(tabs, function (tab) {
      var selected = tab.getAttribute("data-view") === viewName;
      tab.classList.toggle("is-active", selected);
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
    });
    Array.prototype.forEach.call(views, function (view) {
      var selected = view.id === "panel-" + viewName;
      view.hidden = !selected;
      view.classList.toggle("is-active", selected);
    });
    renderPageIntro();
    window.setTimeout(function () {
      if (viewName === "home" || (viewName === "farms" && currentFarmView === "map")) {
        Object.keys(leafletMaps).forEach(function (id) { leafletMaps[id].invalidateSize(); });
      }
    }, 0);
  }

  function setDirectoryView(kind, value) {
    var settings = {
      farm: { value: value, cards: "farm-cards-view", table: "farm-table-view", map: "farm-map-view", selector: "[data-farm-view]" },
      farmer: { value: value, cards: "farmer-cards-view", table: "farmer-table-view", selector: "[data-farmer-view]" },
      worker: { value: value, cards: "worker-cards-view", table: "worker-table-view", selector: "[data-worker-view]" }
    };
    var setting = settings[kind];
    if (!setting) {
      return;
    }
    if (kind === "farm") { currentFarmView = value; }
    if (kind === "farmer") { currentFarmerView = value; }
    if (kind === "worker") { currentWorkerView = value; }
    ["cards", "table", "map"].forEach(function (view) {
      if (!setting[view]) {
        return;
      }
      element(setting[view]).hidden = view !== value;
    });
    Array.prototype.forEach.call(document.querySelectorAll(setting.selector), function (button) {
      var selected = button.getAttribute(kind === "farm" ? "data-farm-view" : (kind === "farmer" ? "data-farmer-view" : "data-worker-view")) === value;
      button.classList.toggle("is-selected", selected);
      button.setAttribute("aria-pressed", String(selected));
    });
    if (kind === "farm" && value === "map" && leafletMaps["farm-map-canvas"]) {
      window.setTimeout(function () { leafletMaps["farm-map-canvas"].invalidateSize(); }, 0);
    }
  }

  function setInboxMode(mode) {
    currentInboxMode = mode === "all" ? "all" : "priority";
    Array.prototype.forEach.call(document.querySelectorAll("[data-inbox-mode]"), function (button) {
      var selected = button.getAttribute("data-inbox-mode") === currentInboxMode;
      button.classList.toggle("is-selected", selected);
      button.setAttribute("aria-pressed", String(selected));
    });
    renderRiskLedger();
  }

  function activateView(event) {
    showView(event.currentTarget.getAttribute("data-view"));
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function moveTab(event) {
    var tabs = Array.prototype.slice.call(document.querySelectorAll(".command-tab"));
    var currentIndex = tabs.indexOf(event.currentTarget);
    if (["ArrowLeft", "ArrowRight", "Home", "End"].indexOf(event.key) === -1) {
      return;
    }
    event.preventDefault();
    var nextIndex = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 :
      (currentIndex + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
    tabs[nextIndex].focus();
    showView(tabs[nextIndex].getAttribute("data-view"));
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function renderPortfolioUnavailable() {
    if (sampleMode) {
      currentPortfolio = samplePortfolio();
      renderRiskLedger();
      renderHomeMetrics();
      return;
    }
    currentPortfolio = null;
    if (currentRuntime) {
      renderDailyDirection();
    }
    element("portfolio-status").textContent = "Actions are unavailable. Home is still usable.";
    element("inbox-summary").textContent = "The decision queue is unavailable right now.";
    setHtml("portfolio-ledger", '<tr><td colspan="6" class="table-empty">Risk and action context is unavailable right now.</td></tr>');
    renderHomeMetrics();
  }

  function inboxRows() {
    var ledger = currentPortfolio ? listedItems(currentPortfolio.risk_action_ledger) : [];
    var rows = ledger.map(function (item) {
      return {
        key: (item.entity && item.entity.type ? item.entity.type : "decision") + ":" + (item.entity && item.entity.id ? item.entity.id : item.title),
        severity: safeSeverity(item.severity), title: item.title, allocationId: item.allocation_id,
        ownerId: item.owner_id, dueAt: item.due_at || item.observed_at, status: item.status,
        action: item.action
      };
    });
    if (currentInboxMode !== "all" || !currentRuntime) {
      return rows;
    }
    var known = {};
    rows.forEach(function (row) { known[row.key] = true; });
    (currentRuntime.exceptions || []).filter(isOpenException).forEach(function (item) {
      var key = "exception_record:" + item.id;
      if (!known[key]) {
        rows.push({ key: key, severity: safeSeverity(item.severity), title: item.title, allocationId: item.allocation_id,
          ownerId: item.owner_id, dueAt: item.observed_at, status: item.status, action: "review exception" });
      }
    });
    (currentRuntime.work_items || []).filter(isOpenWork).forEach(function (item) {
      var key = "work_item:" + item.id;
      if (!known[key]) {
        rows.push({ key: key, severity: item.status === "blocked" ? "high" : "medium", title: item.title,
          allocationId: item.allocation_id, ownerId: item.owner_id, dueAt: item.due_at, status: item.status,
          action: "complete or replan" });
      }
    });
    return rows;
  }

  function renderRiskLedger() {
    var rows = inboxRows();
    if (!rows.length) {
      element("inbox-summary").textContent = currentInboxMode === "all" ?
        "No reviewed open work or decisions." : "No decision needs attention right now.";
      setHtml("portfolio-ledger", '<tr><td colspan="6" class="table-empty">Nothing is waiting for a manager decision.</td></tr>');
      renderHomeMetrics();
      return;
    }
    element("inbox-summary").textContent = currentInboxMode === "all" ?
      formatCount(rows.length) + " reviewed decisions and open work items." :
      formatCount(rows.length) + " priority decisions, most urgent first.";
    setHtml("portfolio-ledger", rows.map(function (item) {
      return '<tr><td><span class="severity severity-' + escapeHtml(item.severity) + '">' + escapeHtml(item.severity) +
        '</span></td><th scope="row">' + escapeHtml(item.title) + '</th><td>' + escapeHtml(fieldNameFor(item.allocationId)) +
        '</td><td>' + escapeHtml(personName(item.ownerId)) + '</td><td>' + escapeHtml(formatTime(item.dueAt)) +
        '</td><td><span class="status">' + escapeHtml(readable(item.status)) + '</span></td></tr>';
    }).join(""));
    renderHomeMetrics();
  }

  function portfolioActionDetail(item) {
    var entity = item && item.entity ? item.entity : {};
    if (entity.type !== "field_information_request") {
      return readable(item.action);
    }
    var owner = item.owner_id ? personName(item.owner_id) : t("noFieldPerson");
    var due = item.due_at ? " · " + t("due") + " " + formatTime(item.due_at) : "";
    var proof = item.proof_required ? " · " + t("fieldProofRequired") : " · " + t("fieldUpdateRequested");
    if (item.status === "draft") {
      return t("fieldAsk") + " · " + owner + " " + t("fieldAskNeedsReview") + proof + ".";
    }
    if (item.status === "ready") {
      return t("fieldAsk") + " · " + owner + " " + t("fieldAskReady") + due + proof + ".";
    }
    return t("awaitingFieldAnswer") + " " + owner + due + proof + ".";
  }

  function laneStatusLabel(status) {
    var labels = {
      ready: "ready",
      context_available: "context ready",
      review_needed: "review needed",
      attention: "needs attention",
      needs_first_farm: "start here",
      needs_active_crop: "needs crop plan",
      needs_first_observation: "needs field check",
      needs_verified_district: "needs district",
      needs_lab_report: "needs lab report",
      needs_field_boundary: "needs boundary",
      needs_market_mapping: "needs market mapping",
      not_connected: "not connected",
      access_review: "access review",
      not_run: "not run"
    };
    return labels[status] || readable(status);
  }

  function laneClass(status) {
    return ["ready", "context_available"].indexOf(status) !== -1 ? "is-ready" :
      status === "review_needed" || status === "attention" ? "is-attention" : "is-gated";
  }

  function fallbackDataLanes() {
    return [
      { name: "Field truth", status: "needs_first_farm", source: "Field team + retained FFL evidence", fact: "Set up the first farm to begin the field loop.", limitation: "Public context never replaces field evidence.", next_move: "Prepare the first farm." },
      { name: "Weather", status: "needs_first_farm", source: "India Meteorological Department (IMD)", fact: "District context is not connected yet.", limitation: "Weather is context, not a field reading or instruction.", next_move: "Verify the farm district." },
      { name: "Soil & water", status: "needs_first_farm", source: "Reviewed lab report + field measurement", fact: "No soil baseline is ready yet.", limitation: "Predicted soil data does not replace a lab report.", next_move: "Retain one reviewed lab report." },
      { name: "Satellite", status: "needs_first_farm", source: "Copernicus Sentinel-2", fact: "No farm or field boundary is ready yet.", limitation: "Imagery is corroboration, never diagnosis.", next_move: "Build field truth before imagery." },
      { name: "Market", status: "needs_first_farm", source: "AGMARKNET / data.gov.in", fact: "No crop or market mapping is ready yet.", limitation: "Mandi context is not a sale price.", next_move: "Record the active crop first." }
    ];
  }

  function renderDataLanes(snapshot) {
    var lanes = snapshot && Array.isArray(snapshot.lanes) && snapshot.lanes.length === 5 ? snapshot.lanes : fallbackDataLanes();
    setHtml("data-lanes", lanes.map(function (lane) {
      var status = lane.status || "not_connected";
      return '<article class="data-lane ' + laneClass(status) + '">' +
        '<div class="data-lane-heading"><h4>' + escapeHtml(lane.name) + '</h4><span class="status">' +
        escapeHtml(laneStatusLabel(status)) + '</span></div>' +
        '<p class="data-lane-fact">' + escapeHtml(lane.fact) + '</p>' +
        '<p class="data-lane-source">' + escapeHtml(lane.source) + '</p>' +
        '<p class="data-lane-limit">' + escapeHtml(lane.limitation) + '</p>' +
        '<p class="data-lane-next"><strong>Next</strong> ' + escapeHtml(lane.next_move) + '</p>' +
        '</article>';
    }).join(""));
  }

  function renderDataLanesUnavailable() {
    renderDataLanes({ lanes: fallbackDataLanes() });
  }

  function setProfileLink(id, url, label) {
    var link = element(id);
    if (!url) {
      link.hidden = true;
      link.removeAttribute("href");
      return;
    }
    link.href = url;
    link.textContent = label;
    link.hidden = false;
  }

  function renderMapExplorer(profile) {
    var configured = profile && profile.configured === true;
    element("map-stage-guard").textContent = "Public coverage only";
    if (!configured) {
      element("map-stage-note").textContent = "No approved public operating area is configured yet.";
      setHtml("map-explorer", '<p class="map-empty">This map stays empty until a reviewed public hub or operating area is configured.</p>');
      setHtml("map-facts", '<div><dt>Farm locations</dt><dd>Not supplied</dd></div><div><dt>Supply villages</dt><dd>Not supplied</dd></div>');
      setProfileLink("map-source", null, "");
      return;
    }
    var facts = [];
    if (profile.public_hub_label) {
      facts.push('<div><dt>Public anchor</dt><dd>' + escapeHtml(profile.public_hub_label) + "</dd></div>");
    }
    if (profile.network_summary) {
      facts.push('<div><dt>Public network</dt><dd>' + escapeHtml(profile.network_summary) + "</dd></div>");
    }
    facts.push('<div><dt>Supply villages</dt><dd>Waiting for Fortune’s reviewed village hierarchy.</dd></div>');
    facts.push('<div><dt>Verified fields</dt><dd>Waiting for a reviewed farm manifest with location proof.</dd></div>');
    setHtml("map-facts", facts.join(""));
    setProfileLink("map-source", profile.source_url, "View public source");
    if (!profile.map_embed_url) {
      element("map-stage-note").textContent = "Public context is configured, but no map anchor has been approved.";
      setHtml("map-explorer", '<p class="map-empty">No map anchor is configured. Partner farms and field boundaries are never guessed here.</p>');
      return;
    }
    element("map-stage-note").textContent = "The mark is a public hub or coverage anchor. It is not a partner farm or a field boundary.";
    setHtml("map-explorer", '<iframe title="Approved public operating footprint" loading="lazy" referrerpolicy="no-referrer" src="' +
      escapeHtml(profile.map_embed_url) + '"></iframe>');
  }

  function renderOperatingProfile(profile) {
    var configured = profile && profile.configured === true;
    var displayName = configured ? text(profile.display_name) : "No operating profile set";
    element("wordmark-name").textContent = configured ? displayName : "AGRO CEO";
    element("profile-heading").textContent = displayName;
    if (!configured) {
      element("profile-summary").textContent = "Add approved public operating context in deployment settings. No farm locations are guessed.";
      setHtml("profile-facts", "");
      setProfileLink("profile-website", null, "");
      setProfileLink("profile-source", null, "");
      renderMapExplorer(profile);
      return;
    }
    element("profile-summary").textContent = "Public operating context only. It is not a field map or a source of record.";
    var facts = [];
    if (profile.coverage_label) {
      facts.push('<div><dt>Operating area</dt><dd>' + escapeHtml(profile.coverage_label) + "</dd></div>");
    }
    if (profile.network_summary) {
      facts.push('<div><dt>Publicly stated network</dt><dd>' + escapeHtml(profile.network_summary) + "</dd></div>");
    }
    if (profile.public_hub_label) {
      facts.push('<div><dt>Public hub</dt><dd>' + escapeHtml(profile.public_hub_label) + "</dd></div>");
    }
    setHtml("profile-facts", facts.join("") || '<p class="empty-state">No public coverage details configured.</p>');
    setProfileLink("profile-website", profile.website_url, "Open company site");
    setProfileLink("profile-source", profile.source_url, "View public source");
    if (!profile.map_embed_url) {
      renderMapExplorer(profile);
      return;
    }
    renderMapExplorer(profile);
  }

  function renderOperatingProfileUnavailable() {
    renderOperatingProfile({ configured: false });
  }

  function countStatusItems(statuses) {
    if (!statuses || typeof statuses !== "object") {
      return 0;
    }
    return Object.keys(statuses).reduce(function (total, status) {
      return total + (typeof statuses[status] === "number" ? statuses[status] : 0);
    }, 0);
  }

  function renderLearning(portfolio) {
    var learning = portfolio.learning || {};
    var trialStatuses = learning.trials && learning.trials.by_status;
    var playbookStatuses = learning.playbooks && learning.playbooks.by_status;
    var availability = learning.availability ? readable(learning.availability) : "unavailable";
    if (availability !== "available") {
      setHtml("portfolio-learning", '<p class="empty-state portfolio-unavailable">Learning context is ' +
        escapeHtml(availability) + '.</p>');
      return;
    }
    setHtml("portfolio-learning", '<dl class="portfolio-counts"><div><dt>Trials</dt><dd>' +
      countStatusItems(trialStatuses) + '</dd></div><div><dt>Playbooks</dt><dd>' +
      countStatusItems(playbookStatuses) + '</dd></div></dl>');
  }

  function renderPortfolio(portfolio) {
    if (!portfolio || typeof portfolio !== "object") {
      renderPortfolioUnavailable();
      return;
    }
    if (sampleMode && !listedItems(portfolio.risk_action_ledger).length) {
      currentPortfolio = samplePortfolio();
      renderRiskLedger();
      renderHomeMetrics();
      return;
    }
    currentPortfolio = portfolio;
    if (currentRuntime) {
      renderDailyDirection();
    }
    renderRiskLedger();
    element("portfolio-status").textContent = "Actions updated just now.";
    renderHomeMetrics();
  }

  function renderPilotReadiness(readiness) {
    var progress = readiness && readiness.progress ? readiness.progress : { completed: 0, total: 6 };
    var stages = readiness && Array.isArray(readiness.stages) ? readiness.stages : [];
    var nextStage = readiness && readiness.next_stage ? readiness.next_stage : null;
    element("today-heading").textContent = interfaceLocale === "hi" ? "पहला खेत" : "First farm";
    element("today-count").textContent = progress.completed + "/" + progress.total;
    element("today-summary").textContent = nextStage ?
      "Start with " + nextStage.title.toLowerCase() + "." :
      "The minimum field loop is ready.";
    setHtml("today-list", stages.slice(0, 3).map(function (stage) {
      var ready = stage.status === "ready";
      return '<button class="queue-item foundation-item foundation-action" type="button" data-first-farm="true"><span class="item-title"><h3>' +
        escapeHtml(stage.title) + '</h3><span class="status">' +
        (ready ? "ready" : "next") + '</span></span><span>' +
        escapeHtml(ready ? "Recorded and ready for the field loop." : stage.next_action) +
        '</span></button>';
    }).join("") || '<p class="empty-state">The first farm has not been prepared yet.</p>');
    element("active-work-count").textContent = progress.completed;
    element("submitted-work-count").textContent = progress.total;
    setHtml("active-work-summary", "<span>Foundations ready</span>");
    setHtml("submitted-work-summary", "<span>Minimum needed</span>");
  }

  function loadPilotReadiness() {
    fetch(pilotReadinessUrl)
      .then(function (response) {
        if (!response.ok) {
          throw new Error("Unable to load first-farm readiness.");
        }
        return response.json();
      })
      .then(renderPilotReadiness)
      .catch(function () {
        element("today-heading").textContent = interfaceLocale === "hi" ? "पहला खेत" : "First farm";
        element("today-count").textContent = "0/6";
        element("today-summary").textContent = "Prepare one real farm before external data can help.";
        setHtml("today-list", '<p class="empty-state">Farm, field, people, place, soil report, then the first work loop.</p>');
      });
  }

  function allocationLabel(allocation) {
    if (!allocation) {
      return "No active crop allocation";
    }
    return (allocation.operational_block_name || "Field") + " · " + allocation.crop_name +
      (allocation.cultivar ? " · " + allocation.cultivar : "");
  }

  function activeAllocation(runtime) {
    var source = runtime || currentRuntime || {};
    var allocations = Array.isArray(source.allocations) ? source.allocations : [];
    var focused = allocations.filter(function (allocation) { return allocation.id === focusedAllocationId; })[0] || null;
    if (!focused && allocations.length) {
      focused = allocations[0];
      focusedAllocationId = focused.id;
    }
    if (!allocations.length) {
      focusedAllocationId = null;
    }
    return focused;
  }

  function allocationCalendarFor(allocationId) {
    var record = allocationCalendars[allocationId];
    return record && record.state === "ready" ? record.data : null;
  }

  function scheduleValue(value) {
    var parsed = new Date(value || "");
    return isNaN(parsed.getTime()) ? Number.POSITIVE_INFINITY : parsed.getTime();
  }

  function nextOpenWork(allocationId, runtime) {
    var workItems = runtime && Array.isArray(runtime.work_items) ? runtime.work_items : [];
    return workItems.filter(function (item) {
      return item.allocation_id === allocationId && isOpenWork(item);
    }).sort(function (left, right) {
      return scheduleValue(left.due_at) - scheduleValue(right.due_at);
    })[0] || null;
  }

  function latestUpdateForAllocation(allocation, runtime) {
    var update = latestFieldUpdate(runtime);
    if (!update || !allocation) {
      return null;
    }
    var matchingAllocations = (runtime.allocations || []).filter(function (candidate) {
      return candidate.operational_block_name === update.operational_block_name && candidate.crop_name === update.crop_name;
    });
    return matchingAllocations.length === 1 && matchingAllocations[0].id === allocation.id ? update : null;
  }

  function reviewableEvidenceForAllocation(allocationId) {
    var signals = currentPortfolio && currentPortfolio.field_signals && currentPortfolio.field_signals.open;
    var items = signals && Array.isArray(signals.items) ? signals.items : [];
    return items.filter(function (item) {
      return item.allocation_id === allocationId;
    }).sort(function (left, right) {
      return scheduleValue(right.received_at || right.observed_at) - scheduleValue(left.received_at || left.observed_at);
    })[0] || null;
  }

  function allocationSnapshot(allocation, runtime) {
    var calendarRecord = allocationCalendars[allocation.id];
    var calendar = allocationCalendarFor(allocation.id);
    var work = nextOpenWork(allocation.id, runtime);
    var update = latestUpdateForAllocation(allocation, runtime);
    var reviewableEvidence = reviewableEvidenceForAllocation(allocation.id);
    var missing = [];
    var stage;
    var stageMissing = false;
    var stageGap = null;

    if (calendarRecord && calendarRecord.state === "loading") {
      stage = "Loading stage plan…";
    } else if (!calendar) {
      stage = "Stage plan unavailable";
      stageMissing = true;
      stageGap = "stage plan";
    } else if (calendar.current_stage) {
      stage = "Confirmed: " + calendar.current_stage.stage_name;
    } else if (calendar.next_checkpoint) {
      stage = "Next check: " + calendar.next_checkpoint.stage_name + " · " + formatTime(calendar.next_checkpoint.planned_for);
      stageMissing = true;
      stageGap = "stage confirmation";
    } else {
      stage = "No stage check planned";
      stageMissing = true;
      stageGap = "stage check";
    }
    if (stageGap) {
      missing.push(stageGap);
    }

    if (!work) {
      missing.push("next work");
    }
    if (!update) {
      missing.push("field record");
    }
    if (reviewableEvidence && reviewableEvidence.evidence_attached === false) {
      missing.push("retained evidence");
    }
    return {
      stage: stage,
      stageMissing: stageMissing,
      nextWork: work ? work.title + " · " + formatTime(work.due_at) : "No open work planned",
      workMissing: !work,
      owner: work ? personName(work.owner_id) : "No work owner set",
      ownerMissing: !work || personName(work.owner_id) === "Unassigned",
      fieldRecord: reviewableEvidence ?
        (reviewableEvidence.evidence_attached ? "Evidence attached · observed " + formatTime(reviewableEvidence.observed_at) :
          "Field signal has no attached evidence") :
        (update ? "Field record observed " + formatTime(update.observed_at) + " · evidence detail unavailable" :
          "No field update recorded"),
      fieldRecordMissing: !update || Boolean(reviewableEvidence && reviewableEvidence.evidence_attached === false),
      missing: missing
    };
  }

  function boardStatusLabel(status) {
    var labels = {
      ready: "recorded",
      attention: "attention",
      missing: "needs record",
      private: "private",
      unavailable: "unavailable"
    };
    return labels[status] || "review";
  }

  function boardPiece(view, icon, label, status, count, detail, action) {
    return '<button class="board-piece is-' + escapeHtml(status) + '" type="button" data-board-view="' +
      escapeHtml(view) + '"><span class="board-piece-top"><span class="board-piece-icon material-symbols-outlined" aria-hidden="true">' +
      escapeHtml(icon) + '</span><span class="status">' + escapeHtml(boardStatusLabel(status)) +
      '</span></span><span class="board-piece-label">' + escapeHtml(label) + '</span><strong>' +
      escapeHtml(count) + '</strong><span class="board-piece-detail">' + escapeHtml(detail) +
      '</span><span class="board-piece-action">' + escapeHtml(action) +
      ' <span class="material-symbols-outlined" aria-hidden="true">arrow_forward</span></span></button>';
  }

  function renderOperationsBoard(runtime) {
    var source = runtime || currentRuntime;
    if (!source) {
      setHtml("operations-board", '<p class="empty-state">Set up one reviewed field to begin the operations board.</p>');
      return;
    }
    var allocations = Array.isArray(source.allocations) ? source.allocations : [];
    var workItems = Array.isArray(source.work_items) ? source.work_items : [];
    var exceptions = Array.isArray(source.exceptions) ? source.exceptions.filter(isOpenException) : [];
    var people = Array.isArray(source.people) ? source.people : [];
    var relationships = source.person_operating_relationships && Array.isArray(source.person_operating_relationships.items) ?
      source.person_operating_relationships.items : [];
    var snapshots = allocations.map(function (allocation) { return allocationSnapshot(allocation, source); });
    var fieldNames = allocations.map(function (allocation) { return allocation.operational_block_name || "Field"; })
      .filter(function (name, index, values) { return values.indexOf(name) === index; });
    var fieldEvidenceGaps = snapshots.filter(function (snapshot) { return snapshot.fieldRecordMissing; }).length;
    var cropPlanGaps = snapshots.filter(function (snapshot) { return snapshot.stageMissing || snapshot.workMissing; }).length;
    var unownedWork = workItems.filter(function (item) { return isOpenWork(item) && !item.owner_id; }).length;
    var fieldTeam = people.filter(isFieldWorker);
    var fieldStatus = !fieldNames.length ? "missing" : (exceptions.length ? "attention" :
      (fieldEvidenceGaps ? "missing" : "ready"));
    var fieldDetail = !fieldNames.length ? "No reviewed operating block yet." : exceptions.length ?
      exceptions.length + (exceptions.length === 1 ? " open field issue." : " open field issues.") : fieldEvidenceGaps ?
      fieldEvidenceGaps + (fieldEvidenceGaps === 1 ? " field needs a record." : " fields need records.") :
      "Reviewed field record is present.";
    var cropStatus = !allocations.length ? "missing" : (cropPlanGaps ? "attention" : "ready");
    var cropDetail = !allocations.length ? "No active crop allocation yet." : cropPlanGaps ?
      cropPlanGaps + (cropPlanGaps === 1 ? " crop needs a stage or work plan." : " crops need a stage or work plan.") :
      "Stage and next work are in place.";
    var teamStatus = !fieldTeam.length ? "missing" : (unownedWork || !relationships.length ? "attention" : "ready");
    var teamDetail = !fieldTeam.length ? "No canonical field team yet." : unownedWork ?
      unownedWork + (unownedWork === 1 ? " open item has no owner." : " open items have no owner.") : !relationships.length ?
      "Reviewed team scope is still needed." : "Roles and scopes are recorded.";
    var inboxItems = exceptions.length + workItems.filter(isOpenWork).length;
    var inboxStatus = !inboxItems ? "ready" : (exceptions.length || unownedWork || workItems.some(isOverdue) ? "attention" : "ready");
    var inboxDetail = !inboxItems ? "No open issues or work items." :
      inboxItems + (inboxItems === 1 ? " item needs a decision or next step." : " items need a decision or next step.");
    var farmerStatus = "private";
    var farmerCount = "Private programme";
    var farmerDetail = "Unlock manager actions to read source coverage.";
    if (managerSessionAuthenticated && currentProgramme && currentProgramme.metrics) {
      var coverage = currentProgramme.metrics.coverage || {};
      var takenKit = Number(coverage.taken_kit) || 0;
      var recent = Number(coverage.recent) || 0;
      var neverVisited = Number(coverage.never_visited) || 0;
      var recentShare = takenKit ? recent / takenKit : 0;
      farmerStatus = !takenKit ? "unavailable" : (recentShare >= 0.75 ? "ready" : "attention");
      farmerCount = takenKit ? formatCount(takenKit) + " programme members" : "No published members";
      farmerDetail = takenKit ? formatCount(recent) + " reached in 14 days · " + formatCount(neverVisited) + " never visited." :
        "No published TrackOlap programme context.";
    }
    setHtml("operations-board",
      boardPiece("farms", "landscape", "Farms", fieldStatus, fieldNames.length + (fieldNames.length === 1 ? " operating block" : " operating blocks"), fieldDetail + " " + cropDetail, "Open farms") +
      boardPiece("farmers", "diversity_3", "Farmers", farmerStatus, farmerCount, farmerDetail + " Source coverage is not a named farmer record.", "Open farmers") +
      boardPiece("workers", "groups", "Field workers", teamStatus, fieldTeam.length + (fieldTeam.length === 1 ? " field worker" : " field workers"), teamDetail, "Open field workers") +
      boardPiece("inbox", "inbox", "Inbox", inboxStatus, inboxItems + (inboxItems === 1 ? " open item" : " open items"), inboxDetail, "Open inbox")
    );
  }

  function allocationFact(label, value, missing) {
    return '<div><dt>' + escapeHtml(label) + '</dt><dd' + (missing ? ' class="is-missing"' : '') + '>' +
      escapeHtml(value) + '</dd></div>';
  }

  function renderAllocationCards(runtime) {
    var allocations = Array.isArray(runtime.allocations) ? runtime.allocations : [];
    if (!allocations.length) {
      element("allocation-summary").textContent = "No active crop allocation has been recorded yet.";
      setHtml("allocation-list", '<p class="empty-state">Add a verified field and a crop allocation to start the operating loop.</p>');
      setHtml("farm-table-body", '<tr><td colspan="4" class="table-empty">No verified fields yet.</td></tr>');
      return;
    }
    element("allocation-summary").textContent = allocations.length === 1 ?
      "One verified field is recorded." : "Verified fields and active crops.";
    setHtml("allocation-list", allocations.map(function (allocation) {
      return '<article class="directory-card allocation-card">' +
        '<div class="allocation-card-heading"><h3>' + escapeHtml(allocation.operational_block_name || "Field") + '</h3>' +
        '<span class="status">verified record</span></div>' +
        '<p class="allocation-crop">' + escapeHtml(allocation.crop_name || "Crop not recorded") + '</p>' +
        '<p class="directory-detail">' + escapeHtml(allocation.cultivar || "Variety not recorded") + '</p>' +
        '</article>';
    }).join(""));
    setHtml("farm-table-body", allocations.map(function (allocation) {
      return '<tr><th scope="row">' + escapeHtml(allocation.operational_block_name || "Field") + '</th><td>' +
        escapeHtml(allocation.crop_name || "Not recorded") + '</td><td>' + escapeHtml(allocation.cultivar || "Not recorded") +
        '</td><td><span class="status">verified</span></td></tr>';
    }).join(""));
  }

  function renderCards(runtime) {
    renderAllocationCards(runtime);
  }

  function clearLeafletMap(containerId, emptyMessage) {
    var container = element(containerId);
    if (leafletMaps[containerId]) {
      leafletMaps[containerId].remove();
      delete leafletMaps[containerId];
    }
    container.innerHTML = '<p class="map-empty-state">' + escapeHtml(emptyMessage) + '</p>';
  }

  function mapPopup(feature) {
    var properties = feature && feature.properties ? feature.properties : {};
    var parts = [properties.plot_label || "Reviewed field"];
    if (properties.crop_name) {
      parts.push(properties.crop_name + (properties.cultivar ? " · " + properties.cultivar : ""));
    }
    if (properties.area_hectares) {
      parts.push(properties.area_hectares + " ha");
    }
    return escapeHtml(parts.join(" · "));
  }

  function renderMapCanvas(containerId, featureCollection) {
    var features = featureCollection && Array.isArray(featureCollection.features) ? featureCollection.features : [];
    if (!features.length) {
      clearLeafletMap(containerId, "No reviewed field geometry is available yet. A programme village or coverage count is never placed on this map.");
      return;
    }
    var container = element(containerId);
    if (!window.L) {
      clearLeafletMap(containerId, "The map library is unavailable. Reviewed field geometry remains protected until the map can load.");
      return;
    }
    if (leafletMaps[containerId]) {
      leafletMaps[containerId].remove();
    }
    container.innerHTML = "";
    var map = window.L.map(container, { zoomControl: true, attributionControl: true });
    leafletMaps[containerId] = map;
    window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "© OpenStreetMap contributors"
    }).addTo(map);
    var layer = window.L.geoJSON(featureCollection, {
      style: { color: "#bc7a1e", weight: 2, fillColor: "#d8b14d", fillOpacity: 0.28 },
      pointToLayer: function (_feature, latlng) {
        return window.L.circleMarker(latlng, {
          radius: 7, color: "#173f2c", weight: 2, fillColor: "#d7aa3f", fillOpacity: 0.95
        });
      },
      onEachFeature: function (feature, featureLayer) {
        featureLayer.bindTooltip(mapPopup(feature), { sticky: true });
      }
    }).addTo(map);
    var bounds = layer.getBounds();
    if (bounds.isValid()) {
      map.fitBounds(bounds.pad(0.3), { maxZoom: 13 });
    }
  }

  function renderFortuneMap(featureCollection) {
    currentFortuneMap = featureCollection || { type: "FeatureCollection", features: [] };
    var features = currentFortuneMap.features || [];
    var count = features.length;
    element("home-map-status").textContent = sampleMode ? "Sample · North Block" :
      (count ? formatCount(count) + " reviewed field" + (count === 1 ? "" : "s") : "No reviewed geometry");
    element("home-map-note").textContent = sampleMode ? "Sample geometry" : (count ?
      "Map detail comes only from the latest published, reviewed farm manifest." :
      "Only manager-reviewed points and boundaries appear here. Programme coverage never becomes a farm pin.");
    element("farm-map-note").textContent = sampleMode ? "Sample geometry" : (count ?
      "The map is the same reviewed farm geometry used in Today." :
      "Only reviewed field geometry is shown. No source village is treated as a farm point.");
    renderMapCanvas("home-map-canvas", currentFortuneMap);
    renderMapCanvas("farm-map-canvas", currentFortuneMap);
  }

  function renderFortuneMapUnavailable() {
    if (sampleMode) {
      renderFortuneMap(sampleMap());
      return;
    }
    currentFortuneMap = { type: "FeatureCollection", features: [] };
    element("home-map-status").textContent = managerSessionAuthenticated ? "Map unavailable" : "Unlock to reveal map";
    element("home-map-note").textContent = managerSessionAuthenticated ?
      "Reviewed field geometry could not be loaded right now." :
      "Manager access is required before private reviewed field geometry can be shown.";
    element("farm-map-note").textContent = element("home-map-note").textContent;
    clearLeafletMap("home-map-canvas", element("home-map-note").textContent);
    clearLeafletMap("farm-map-canvas", element("farm-map-note").textContent);
  }

  function loadFortuneMap() {
    if (!managerSessionAuthenticated) {
      renderFortuneMapUnavailable();
      return Promise.resolve();
    }
    return fetch(fortuneMapUrl, { credentials: "same-origin" })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("Reviewed field geometry is unavailable.");
        }
        return response.json();
      })
      .then(renderFortuneMap)
      .catch(renderFortuneMapUnavailable);
  }

  function personFor(personId) {
    var people = currentRuntime && Array.isArray(currentRuntime.people) ? currentRuntime.people : [];
    return people.filter(function (person) { return person.id === personId; })[0] || null;
  }

  function personName(personId) {
    var person = personFor(personId);
    return person ? person.name : "Unassigned";
  }

  function workFor(workId) {
    var workItems = currentRuntime && Array.isArray(currentRuntime.work_items) ? currentRuntime.work_items : [];
    return workItems.filter(function (item) { return item.id === workId; })[0] || null;
  }

  function allocationFor(allocationId) {
    var allocations = currentRuntime && Array.isArray(currentRuntime.allocations) ? currentRuntime.allocations : [];
    return allocations.filter(function (allocation) { return allocation.id === allocationId; })[0] || null;
  }

  function fieldNameFor(allocationId) {
    var allocation = allocationFor(allocationId);
    return allocation && allocation.operational_block_name ? allocation.operational_block_name : "Field";
  }

  function exceptionFor(exceptionId) {
    var exceptions = currentRuntime && Array.isArray(currentRuntime.exceptions) ? currentRuntime.exceptions : [];
    return exceptions.filter(function (item) { return item.id === exceptionId; })[0] || null;
  }

  function setFocusAction(label, targetView, exceptionId) {
    focusTargetView = targetView;
    focusExceptionId = exceptionId || null;
    element("focus-action-label").textContent = label;
  }

  function isFarmer(person) {
    return person && ["grower", "landholder", "lessee"].indexOf(person.role) !== -1;
  }

  function isFieldWorker(person) {
    return person && ["field_operator", "agronomist"].indexOf(person.role) !== -1;
  }

  function personDirectoryData(person, runtime, relationships, relationshipAvailability) {
    var workItems = Array.isArray(runtime.work_items) ? runtime.work_items : [];
    var assignedItems = workItems.filter(function (item) {
      return item.owner_id === person.id && isOpenWork(item);
    });
    var fields = assignedItems.map(function (item) { return fieldNameFor(item.allocation_id); })
      .filter(function (value, index, values) { return values.indexOf(value) === index; });
    var assignments = relationships.filter(function (relationship) {
      return relationship.person_id === person.id;
    });
    var assignmentCopy = assignments.length ? assignments.map(function (relationship) {
      return readable(relationship.role) + (relationship.scope_name ? " · " + relationship.scope_name : "");
    }).join(" · ") : (relationshipAvailability === "available" ? "No field relationship recorded." :
      (relationshipAvailability === "not_configured" ? "Field relationship setup is pending." : "Field relationship summary unavailable."));
    return {
      name: person.name,
      role: readable(person.role),
      scope: assignmentCopy,
      openWork: assignedItems.length,
      fields: fields
    };
  }

  function personCardMarkup(personData) {
    return '<article class="directory-card person-card"><h3>' + escapeHtml(personData.name) + '</h3>' +
      '<p class="person-role">' + escapeHtml(personData.role) + '</p>' +
      '<p class="person-assignment">' + escapeHtml(personData.scope) + '</p>' +
      '<p class="person-work">' + personData.openWork + (personData.openWork === 1 ? ' open item' : ' open items') +
      (personData.fields.length ? ' · ' + escapeHtml(personData.fields.join(", ")) : '') + '</p></article>';
  }

  function peopleTableMarkup(people) {
    if (!people.length) {
      return '<tr><td colspan="4" class="table-empty">No reviewed people records are available yet.</td></tr>';
    }
    return people.map(function (person) {
      return '<tr><th scope="row">' + escapeHtml(person.name) + '</th><td>' + escapeHtml(person.role) +
        '</td><td>' + escapeHtml(person.scope) + '</td><td>' + escapeHtml(person.openWork + (person.openWork === 1 ? " item" : " items")) +
        '</td></tr>';
    }).join("");
  }

  function renderPeople(runtime) {
    var people = Array.isArray(runtime.people) ? runtime.people : [];
    var relationshipSummary = runtime.person_operating_relationships || {};
    var relationships = Array.isArray(relationshipSummary.items) ? relationshipSummary.items : [];
    var relationshipAvailability = relationshipSummary.availability || "not_configured";
    var farmers = people.filter(isFarmer).map(function (person) {
      return personDirectoryData(person, runtime, relationships, relationshipAvailability);
    });
    var workers = people.filter(isFieldWorker).map(function (person) {
      return personDirectoryData(person, runtime, relationships, relationshipAvailability);
    });
    setHtml("farmer-list", farmers.length ? farmers.map(personCardMarkup).join("") :
      '<p class="empty-state">No reviewed farmer record is available yet. Programme coverage stays separate.</p>');
    setHtml("worker-list", workers.length ? workers.map(personCardMarkup).join("") :
      '<p class="empty-state">No reviewed field worker record is available yet. Daily source activity stays aggregate until reviewed.</p>');
    setHtml("farmer-table-body", peopleTableMarkup(farmers));
    setHtml("worker-table-body", peopleTableMarkup(workers));
  }

  function renderInboxWork(runtime) {
    var workItems = runtime && Array.isArray(runtime.work_items) ? runtime.work_items : [];
    var openItems = workItems.filter(isOpenWork);
    var selectedOwner = inboxOwnerId ? personFor(inboxOwnerId) : null;
    if (inboxOwnerId) {
      openItems = openItems.filter(function (item) { return item.owner_id === inboxOwnerId; });
    }
    element("inbox-clear-filter").hidden = !inboxOwnerId;
    element("inbox-clear-filter").textContent = selectedOwner ? "Show all work" : "Clear worker filter";
    if (!openItems.length) {
      setHtml("inbox-work-list", '<p class="empty-state">' + (selectedOwner ?
        escapeHtml(selectedOwner.name) + ' has no open reviewed work.' : "No open reviewed work is recorded.") + "</p>");
      return;
    }
    setHtml("inbox-work-list", openItems.slice(0, 8).map(function (item) {
      var owner = item.owner_id ? personName(item.owner_id) : "No owner";
      return '<article class="inbox-work-item"><div class="item-title"><h4>' + escapeHtml(item.title) + '</h4><span class="status">' +
        escapeHtml(readable(item.status)) + '</span></div><p class="work-field">' + escapeHtml(fieldNameFor(item.allocation_id)) +
        '</p><p class="today-item-detail">Owner · ' + escapeHtml(owner) + ' · due ' + escapeHtml(formatTime(item.due_at)) + '</p></article>';
    }).join(""));
  }

  function latestFieldUpdate(runtime) {
    return runtime && runtime.latest_field_update && typeof runtime.latest_field_update === "object" ?
      runtime.latest_field_update : null;
  }

  function setDailyDirection(status, title, note, officerActivity, visitGap, nextMove, confidence, targetView) {
    element("field-title").textContent = title;
    element("field-note").textContent = note;
    element("field-status").textContent = status;
    element("field-status").className = status === "attention" ? "severity severity-high" : "status";
    var labels = {
      farms: "Open farms",
      farmers: "Open farmers",
      workers: "Open field workers",
      inbox: "Open inbox",
      settings: "Open settings"
    };
    setFocusAction(labels[targetView] || "Open today", targetView, null);
  }

  function renderDailyDirection() {
    var programme = currentProgramme && currentProgramme.metrics ? currentProgramme.metrics : null;
    if (!programme) {
      setDailyDirection(
        "reading", "Reading today’s operation.",
        "The field picture is loading.",
        "Daily activity loading", "Coverage loading", "Open field workers", "Awaiting today’s signal", "workers"
      );
      return;
    }
    var visits = programme.visits || {};
    var coverage = programme.coverage || {};
    var issues = programme.issues || {};
    var freshness = programme.freshness || {};
    var issueRows = Array.isArray(issues.by_issue) ? issues.by_issue : [];
    var officersWithoutVisit = Number(visits.active_officers_without_filed_visit) || 0;
    var activeOfficers = Number(visits.active_officers) || 0;
    var filedToday = Number(visits.filed_on_reporting_day) || 0;
    var filingOfficers = Number(visits.filing_officers) || 0;
    var overdue = Number(coverage.overdue) || 0;
    var neverVisited = Number(coverage.never_visited) || 0;
    var urgentIssue = issueRows.filter(function (issue) {
      return ["critical", "high"].indexOf(issue.highest_severity) !== -1;
    })[0] || null;
    var confidence = freshness.status === "available" ?
      "Published source · " + formatAgeHours(freshness.age_hours) + " old" : "No published source timestamp";

    if (officersWithoutVisit > 0) {
      setDailyDirection(
        "attention", formatCount(officersWithoutVisit) + " officers filed no visit today.",
        formatCount(filedToday) + " visits were filed by " + formatCount(filingOfficers) + " of " + formatCount(activeOfficers) + " active officers. Start with the coverage gap, then follow up with the field team.",
        formatCount(filingOfficers) + " / " + formatCount(activeOfficers) + " officers filed", formatCount(overdue) + " farmers overdue",
        "Review worker follow-up", confidence, "workers"
      );
      return;
    }
    if (urgentIssue) {
      setDailyDirection(
        "attention", readable(urgentIssue.issue_code) + " is the lead field signal.",
        formatCount(urgentIssue.count) + " dated observations in the last " + formatCount(issues.window_days || 7) + " days. Detection shows where to look, not a diagnosis or prevalence rate.",
        formatCount(filedToday) + " visits filed today", formatCount(overdue) + " farmers overdue",
        "Review the decision queue", confidence, "inbox"
      );
      return;
    }
    setDailyDirection(
      overdue ? "attention" : "recorded", overdue ? formatCount(overdue) + " farmers are overdue for a visit." : "Farmer coverage is current.",
      overdue ? "Start with the farmer groups carrying the largest overdue gap. Never visited remains a separate acquisition and record-quality gap." :
        "No overdue visit gap is reported in the published farmer aggregate.",
      formatCount(filedToday) + " visits filed today", formatCount(neverVisited) + " never visited",
      overdue ? "Review farmer coverage" : "Review farmer coverage", confidence, "farmers"
    );
  }

  function renderMorningBrief(brief) {
    var attention = brief && Array.isArray(brief.attention) ? brief.attention : [];
    renderToday(attention);
  }

  function todayDetail(item) {
    var entity = item && item.entity ? item.entity : {};
    var exception = entity.type === "exception_record" ? exceptionFor(entity.id) : null;
    var work = entity.type === "work_item" ? workFor(entity.id) : null;
    if (exception) {
      return "Owner · " + personName(exception.owner_id) + " · " + readable(exception.status);
    }
    if (work) {
      return fieldNameFor(work.allocation_id) + " · " + personName(work.owner_id) + " · due " + formatTime(work.due_at);
    }
    if (entity.type === "crop_stage_checkpoint") {
      return "Field check due.";
    }
    if (entity.type === "field_information_request") {
      var requestOwner = item.owner_id ? personName(item.owner_id) : t("noFieldPerson");
      var requestDue = item.due_at ? " · " + t("due") + " " + formatTime(item.due_at) : "";
      var proof = item.proof_required ? " · " + t("fieldProofRequired") : " · " + t("fieldUpdateRequested");
      return t("fieldAsk") + " · " + requestOwner + requestDue + proof;
    }
    if (entity.type === "regional_signal" || entity.type === "source_registry") {
      return "District context only. Check it against the field.";
    }
    return item && item.detail ? item.detail : "Needs a manager check.";
  }

  function todayNext(item) {
    var entity = item && item.entity ? item.entity : {};
    if (entity.type === "exception_record") {
      return "Review and assign the next step.";
    }
    if (entity.type === "work_item") {
      return "Complete it, replan it, or record why it is blocked.";
    }
    if (entity.type === "crop_stage_checkpoint") {
      return "Confirm the stage in the field.";
    }
    if (entity.type === "field_information_request") {
      return entity && item.action === "review_delivery_eligibility" ?
        t("checkDelivery") : t("reviewFieldAnswer");
    }
    if (entity.type === "regional_signal" || entity.type === "source_registry") {
      return "Check the source before changing field work.";
    }
    return "Check the farm record.";
  }

  function renderToday(items) {
    var currentItems = Array.isArray(items) ? items.slice(0, 3) : [];
    currentAttention = currentItems;
    element("today-count").textContent = currentItems.length;
    element("today-summary").textContent = currentItems.length ?
      (currentItems.length === 1 ? "One item needs a look." : currentItems.length + " items need a look.") :
      "Nothing needs a look right now.";
    if (!currentItems.length) {
      setHtml("today-list", '<p class="empty-state">No due work or open issue.</p>');
      return;
    }
    setHtml("today-list", currentItems.map(function (item, index) {
      var entity = item.entity || {};
      return '<button class="queue-item today-item today-action" type="button" data-today-index="' + index + '">' +
        '<div class="item-title"><h3>' + escapeHtml(item.title) + '</h3><span class="severity severity-' +
        safeSeverity(item.priority) + '">' + escapeHtml(item.priority) + '</span></div>' +
        '<p class="today-item-detail">' + escapeHtml(todayDetail(item)) + '</p>' +
        '<p class="today-item-next"><strong>Next</strong> ' + escapeHtml(todayNext(item)) + '</p>' +
        '<span class="detail-button">Open</span>' +
        '</button>';
    }).join(""));
  }

  function renderTodayFallback(runtime) {
    var exceptions = (runtime.exceptions || []).filter(isOpenException).map(function (item) {
      return { priority: item.severity === "critical" ? "critical" : "high", title: item.title,
        entity: { type: "exception_record", id: item.id } };
    });
    var work = (runtime.work_items || []).filter(function (item) {
      return item.status === "submitted" || (isOpenWork(item) && isOverdue(item));
    }).map(function (item) {
      return { priority: item.status === "submitted" ? "medium" : "high", title: item.title,
        entity: { type: "work_item", id: item.id } };
    });
    renderToday(exceptions.concat(work));
  }

  function loadMorningBrief(runtime) {
    if (!runtime || !runtime.operating_unit || !runtime.operating_unit.id) {
      return;
    }
    fetch("/api/v1/operating-units/" + encodeURIComponent(runtime.operating_unit.id) + "/morning-brief")
      .then(function (response) {
        if (!response.ok) {
          throw new Error("Unable to load the operating brief.");
        }
        return response.json();
      })
      .then(renderMorningBrief)
      .catch(function () {
        // The Home view remains fully useful from runtime data when the brief
        // cannot be composed. It is a read-only summary, never a source of record.
      });
  }

  function renderWork(runtime) {
    var allocation = activeAllocation(runtime);
    var workItems = runtime && Array.isArray(runtime.work_items) ? runtime.work_items : [];
    var openWork = allocation ? workItems.filter(function (item) {
      return item.allocation_id === allocation.id && isOpenWork(item);
    }) : [];
    element("work-context").textContent = allocation ? allocationLabel(allocation) : "No active crop allocation";
    if (!openWork.length) {
      setHtml("work-list", '<p class="empty-state">' + (allocation ?
        'No open work is linked to this crop allocation.' :
        'No farm work is shown until an active allocation exists.') + '</p>');
      return;
    }
    setHtml("work-list", openWork.map(function (item) {
      var overdue = isOverdue(item);
      return "<article class=\"queue-item\">" +
        "<p class=\"work-field\">" + escapeHtml(fieldNameFor(item.allocation_id)) + "</p>" +
        "<div class=\"item-title\"><h3>" + escapeHtml(item.title) + "</h3>" +
        "<span class=\"status status-" + escapeHtml(item.status) + "\">" + escapeHtml(item.status) + "</span></div>" +
        "<dl class=\"facts\"><div><dt>Owner</dt><dd>" + escapeHtml(personName(item.owner_id)) + "</dd></div>" +
        "<div><dt>Due</dt><dd>" + escapeHtml(formatTime(item.due_at)) + "</dd></div>" +
        "<div><dt>Timing</dt><dd class=\"" + (overdue ? "overdue" : "") + "\">" + (overdue ? "Overdue" : "On schedule") + "</dd></div></dl>" +
        "</article>";
    }).join(""));
  }

  function renderActionAllocationContext(runtime) {
    var allocation = activeAllocation(runtime);
    var context = element("actions-allocation-context");
    if (!allocation) {
      context.hidden = true;
      return;
    }
    context.hidden = false;
    element("actions-allocation-name").textContent = allocationLabel(allocation);
    element("actions-allocation-note").textContent =
      "Only risks and actions explicitly linked to this crop allocation are shown below. Operating-wide context stays in Home.";
  }

  function refreshFocusedAllocationExperience() {
    if (!currentRuntime) {
      return;
    }
    renderCards(currentRuntime);
    renderDailyDirection();
    renderOperationsBoard(currentRuntime);
    renderWork(currentRuntime);
    renderActionAllocationContext(currentRuntime);
    if (currentPortfolio) {
      renderRiskLedger(currentPortfolio);
    }
  }

  function loadAllocationCalendars(runtime) {
    var allocations = Array.isArray(runtime.allocations) ? runtime.allocations : [];
    var requestId = allocationCalendarRequest + 1;
    allocationCalendarRequest = requestId;
    allocationCalendars = {};
    allocations.forEach(function (allocation) {
      allocationCalendars[allocation.id] = { state: "loading" };
    });
    refreshFocusedAllocationExperience();
    if (!allocations.length) {
      return;
    }
    Promise.all(allocations.map(function (allocation) {
      return fetch(allocationCalendarUrl + encodeURIComponent(allocation.id) + "/calendar")
        .then(function (response) {
          if (!response.ok) {
            throw new Error("Unable to load allocation calendar.");
          }
          return response.json();
        })
        .then(function (calendar) {
          allocationCalendars[allocation.id] = { state: "ready", data: calendar };
        })
        .catch(function () {
          allocationCalendars[allocation.id] = { state: "unavailable" };
        });
    })).then(function () {
      if (requestId === allocationCalendarRequest && currentRuntime === runtime) {
        refreshFocusedAllocationExperience();
      }
    });
  }

  function selectAllocation(allocationId) {
    if (!currentRuntime || !allocationFor(allocationId)) {
      return;
    }
    focusedAllocationId = allocationId;
    refreshFocusedAllocationExperience();
  }

  function renderRuntime(runtime) {
    setSampleMode(false);
    currentRuntime = runtime;
    currentOperatingUnitName = runtime.operating_unit ? runtime.operating_unit.name : "Current field operations";
    renderPageIntro();
    renderCards(runtime);
    renderPeople(runtime);
    renderRiskLedger();
    renderDailyDirection();
    renderHomeMetrics();
  }

  function renderRuntimeUnavailable() {
    setSampleMode(true);
    currentRuntime = sampleRuntime();
    currentPortfolio = samplePortfolio();
    currentOperatingUnitName = "Fortune Rice";
    focusedAllocationId = null;
    allocationCalendars = {};
    renderPageIntro();
    renderCards(currentRuntime);
    renderPeople(currentRuntime);
    renderProgramme(sampleProgramme(), { state: "sample" });
    renderRiskLedger();
    renderSampleWeather();
    renderFortuneMap(sampleMap());
    renderHomeMetrics();
  }

  function renderAudit(detail) {
    var audit = detail.audit_events || [];
    var history = audit.length ? "<ol class=\"audit-list\">" + audit.map(function (event) {
      return "<li><strong>" + escapeHtml(event.from_status) + " → " + escapeHtml(event.to_status) + "</strong>" +
        "<span>" + escapeHtml(event.actor_id) + " · " + escapeHtml(formatTime(event.created_at)) + "</span>" +
        "<span>" + escapeHtml(event.reason) + "</span></li>";
    }).join("") + "</ol>" : "<p class=\"empty-state\">No audit events recorded yet.</p>";
    setHtml("exception-detail", "<div class=\"detail-heading\"><h3>" + escapeHtml(detail.title) + "</h3>" +
      "<span class=\"status\">" + escapeHtml(detail.status) + "</span></div>" + history);
  }

  function loadException(exceptionId) {
    element("exception-detail").textContent = "Loading audit history…";
    fetch("/api/v1/exceptions/" + encodeURIComponent(exceptionId))
      .then(function (response) {
        if (!response.ok) {
          throw new Error("Unable to load exception detail.");
        }
        return response.json();
      })
      .then(renderAudit)
      .catch(function (error) {
        element("exception-detail").textContent = error.message;
      });
  }

  function actionDestination(item) {
    var entity = item && item.entity ? item.entity : {};
    if (entity.type === "exception_record") {
      return { view: "farms", exceptionId: entity.id, label: "Open farm issue" };
    }
    if (entity.type === "regional_signal" || entity.type === "source_registry") {
      return { view: "settings", exceptionId: null, label: "Open data connections" };
    }
    if (entity.type === "field_information_request") {
      return { view: "inbox", exceptionId: null, label: t("openFieldAsks") };
    }
    return { view: "farms", exceptionId: null, label: "Open farm work" };
  }

  function openActionDetail(item) {
    if (!item) {
      return;
    }
    pendingAction = actionDestination(item);
    element("action-dialog-title").textContent = text(item.title);
    element("action-dialog-detail").textContent = todayDetail(item);
    element("action-dialog-next").textContent = "Next: " + todayNext(item);
    element("action-go").innerHTML = escapeHtml(pendingAction.label) +
      ' <span class="material-symbols-outlined" aria-hidden="true">arrow_forward</span>';
    var dialog = element("action-dialog");
    if (!dialog.open) {
      dialog.showModal();
    }
  }

  function followActionDetail() {
    if (!pendingAction) {
      return;
    }
    var action = pendingAction;
    element("action-dialog").close();
    showView(action.view);
    if (action.exceptionId) {
      loadException(action.exceptionId);
      element("audit").scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    var target = action.view === "settings" ? element("context-heading") :
      (action.view === "inbox" ? element("inbox-work-heading") : element("work-heading"));
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  function loadActionCentre() {
    element("load-status").textContent = "Loading…";
    element("portfolio-status").textContent = "Loading actions…";
    renderTodayClock();
    loadProgramme();
    fetch(dataLanesUrl, { credentials: "same-origin" })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("Weather context is unavailable.");
        }
        return response.json();
      })
      .then(renderWeatherContext)
      .catch(renderWeatherUnavailable);
    loadFortuneMap();
    fetch(runtimeUrl)
      .then(function (response) {
        if (!response.ok) {
          throw new Error("Unable to load the current runtime.");
        }
        return response.json();
      })
      .then(function (runtime) {
        renderRuntime(runtime);
        element("load-status").textContent = "Updated just now.";
      })
      .catch(function () {
        renderRuntimeUnavailable();
        element("load-status").textContent = "Showing sample operation.";
      });

    fetch(portfolioUrl)
      .then(function (response) {
        if (!response.ok) {
          throw new Error("Unable to load portfolio context.");
        }
        return response.json();
      })
      .then(renderPortfolio)
      .catch(renderPortfolioUnavailable);

  }

  Array.prototype.forEach.call(document.querySelectorAll(".command-tab"), function (tab) {
    tab.addEventListener("click", activateView);
    tab.addEventListener("keydown", moveTab);
  });
  Array.prototype.forEach.call(document.querySelectorAll("[data-farm-view]"), function (button) {
    button.addEventListener("click", function () { setDirectoryView("farm", button.getAttribute("data-farm-view")); });
  });
  Array.prototype.forEach.call(document.querySelectorAll("[data-farmer-view]"), function (button) {
    button.addEventListener("click", function () { setDirectoryView("farmer", button.getAttribute("data-farmer-view")); });
  });
  Array.prototype.forEach.call(document.querySelectorAll("[data-worker-view]"), function (button) {
    button.addEventListener("click", function () { setDirectoryView("worker", button.getAttribute("data-worker-view")); });
  });
  Array.prototype.forEach.call(document.querySelectorAll("[data-inbox-mode]"), function (button) {
    button.addEventListener("click", function () { setInboxMode(button.getAttribute("data-inbox-mode")); });
  });
  element("language-toggle").addEventListener("click", function () {
    setLocale(interfaceLocale === "en" ? "hi" : "en");
  });
  Array.prototype.forEach.call(document.querySelectorAll("[data-locale]"), function (button) {
    button.addEventListener("click", function () {
      setLocale(button.getAttribute("data-locale"));
    });
  });
  element("refresh").addEventListener("click", loadActionCentre);
  element("manager-session-action").addEventListener("click", toggleManagerSession);
  element("close-manager-session").addEventListener("click", function () {
    element("manager-session-dialog").close();
    element("manager-session-form").reset();
    setManagerSessionFeedback("");
  });
  element("manager-session-dialog").addEventListener("cancel", function () {
    element("manager-session-form").reset();
    setManagerSessionFeedback("");
  });
  element("manager-session-form").addEventListener("submit", submitManagerSession);
  element("review-focus").addEventListener("click", function () {
    showView(focusTargetView);
    if (focusTargetView === "farms") {
      element("allocations-heading").scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    if (focusTargetView === "farmers") {
      element("farmer-directory-heading").scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    if (focusTargetView === "workers") {
      element("worker-directory-heading").scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    if (focusTargetView === "inbox") {
      element("ledger-heading").scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    if (focusTargetView === "settings") {
      element("settings-heading").scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });
  applyLanguage();
  renderTodayClock();
  window.setInterval(renderTodayClock, 60000);
  loadManagerSessionStatus().then(loadActionCentre);
}());
