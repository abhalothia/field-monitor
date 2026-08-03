(function () {
  "use strict";

  var runtimeUrl = "/api/v1/runtime";
  var portfolioUrl = "/api/v1/portfolio";
  var allocationCalendarUrl = "/api/v1/allocations/";
  var dataLanesUrl = "/api/v1/data-lanes";
  var operatingProfileUrl = "/api/v1/operating-profile";
  var pilotReadinessUrl = "/api/v1/pilot/readiness";
  var quickStartValidationUrl = "/api/v1/pilot/quick-start/validate";
  var managerSessionStatusUrl = "/api/v1/manager-session/status";
  var managerSessionLoginUrl = "/api/v1/manager-session/login";
  var managerSessionLogoutUrl = "/api/v1/manager-session/logout";
  var trackolapMetricsUrl = "/api/v1/trackolap/metrics";
  var trackolapHealthUrl = "/api/v1/trackolap/health";
  var currentRuntime = null;
  var currentPortfolio = null;
  var currentProgramme = null;
  var allocationCalendars = {};
  var focusedAllocationId = null;
  var allocationCalendarRequest = 0;
  var currentAttention = [];
  var pendingAction = null;
  var focusExceptionId = null;
  var focusTargetView = "fields";
  var managerSessionAuthenticated = false;
  var localeStorageKey = "ffl.manager.interface-locale";
  var interfaceLocale = window.localStorage.getItem(localeStorageKey) === "hi" ? "hi" : "en";
  var copy = {
    en: {
      navHome: "Today", navProgramme: "Programme", navMap: "Territory",
      refresh: "Refresh", openMap: "Open territory", pageTitle: "Today.", fieldPulse: "Daily direction", lastUpdate: "Last update", from: "From",
      openFieldWork: "Open programme", today: "Today", openWork: "Open work", awaitingReview: "Awaiting review",
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
      navHome: "आज", navProgramme: "कार्यक्रम", navMap: "क्षेत्र",
      refresh: "ताज़ा करें", openMap: "क्षेत्र खोलें", pageTitle: "आज।", fieldPulse: "आज की दिशा", lastUpdate: "आख़िरी अपडेट", from: "किससे",
      openFieldWork: "कार्यक्रम खोलें", today: "आज", openWork: "खुला काम", awaitingReview: "समीक्षा के लिए",
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
    if (currentAttention.length) {
      renderToday(currentAttention);
    }
    if (currentProgramme) {
      renderProgramme(currentProgramme.metrics, currentProgramme.health);
    }
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

  function programmeWarningCopy(code) {
    if (code === "low_observation_confidence") {
      return "Observation confidence is low. Fewer detections do not mean risk has fallen.";
    }
    return "Review source limitation: " + readable(code) + ".";
  }

  function renderProgrammeLocked() {
    currentProgramme = null;
    element("programme-source-state").textContent = "locked";
    element("programme-boundary").textContent = "Open System controls to unlock Fortune programme context on this browser.";
    setHtml("programme-coverage", '<p class="empty-state">Programme aggregates stay private until manager access is unlocked.</p>');
    setHtml("programme-observations", '<p class="empty-state">No source observations are shown while manager access is locked.</p>');
    setHtml("programme-inputs", '<p class="empty-state">No source input signals are shown while manager access is locked.</p>');
    setHtml("programme-freshness", '<p class="empty-state">Source freshness is private manager context.</p>');
    renderDailyDirection();
    if (currentRuntime) {
      renderOperationsBoard(currentRuntime);
    }
  }

  function renderProgrammeUnavailable() {
    currentProgramme = null;
    element("programme-source-state").textContent = "unavailable";
    element("programme-boundary").textContent = "Programme metrics are unavailable. Review the source state before taking action from this gap.";
    setHtml("programme-coverage", '<p class="empty-state portfolio-unavailable">No published programme aggregate is available right now.</p>');
    setHtml("programme-observations", '<p class="empty-state portfolio-unavailable">Observation context is unavailable; absence is not evidence of absence.</p>');
    setHtml("programme-inputs", '<p class="empty-state portfolio-unavailable">Input review cues are unavailable.</p>');
    setHtml("programme-freshness", '<p class="empty-state portfolio-unavailable">Source state could not be checked.</p>');
    renderDailyDirection();
    if (currentRuntime) {
      renderOperationsBoard(currentRuntime);
    }
  }

  function renderProgramme(metrics, health) {
    var coverage = metrics && metrics.coverage ? metrics.coverage : {};
    var issues = metrics && metrics.issues ? metrics.issues : {};
    var pesticides = metrics && metrics.pesticides ? metrics.pesticides : {};
    var freshness = metrics && metrics.freshness ? metrics.freshness : {};
    var warningCodes = metrics && Array.isArray(metrics.warnings) ? metrics.warnings : [];
    var sourceState = health && health.state ? readable(health.state) : "published context";
    var issueWindow = Number(issues.window_days) || 7;
    var issueRows = Array.isArray(issues.by_issue) ? issues.by_issue : [];
    var sourceLabel = freshness.status === "available" ? sourceState : "no published data";
    var policy = pesticides.policy || "review cue only; not an application recommendation or compliance verdict";

    currentProgramme = { metrics: metrics || {}, health: health || {} };
    renderDailyDirection();
    element("programme-source-state").textContent = sourceLabel;
    element("programme-boundary").textContent = "Published programme context. Verified farm and field records remain separate until reviewed.";
    setHtml("programme-coverage",
      programmeFact("Taken kit", coverage.taken_kit) +
      programmeFact("Visited", coverage.visited) +
      programmeFact("Recent · 14 days", coverage.recent) +
      programmeFact("Overdue", coverage.overdue) +
      programmeFact("Never visited", coverage.never_visited)
    );

    var observationSummary = '<p class="programme-number">' + escapeHtml(formatCount(issues.observation_count)) +
      '<span>dated observations · ' + escapeHtml(String(issueWindow)) + ' days</span></p>';
    var observationRows = issueRows.length ? '<ol class="programme-list">' + issueRows.slice(0, 5).map(function (issue) {
      return '<li><div><strong>' + escapeHtml(readable(issue.issue_code)) + '</strong><span>' +
        escapeHtml(formatCount(issue.count)) + ' observations</span></div><span class="severity severity-' +
        escapeHtml(safeSeverity(issue.highest_severity)) + '">' +
        escapeHtml(readable(issue.highest_severity)) + '</span></li>';
    }).join("") + '</ol>' : '<p class="empty-state">No dated observations in this window. This is not proof that no issue exists.</p>';
    var warningRows = warningCodes.length ? '<ul class="programme-warnings">' + warningCodes.map(function (warning) {
      return '<li>' + escapeHtml(programmeWarningCopy(warning)) + '</li>';
    }).join("") + '</ul>' : '';
    setHtml("programme-observations", observationSummary + observationRows + warningRows);

    setHtml("programme-inputs", '<p class="programme-number">' + escapeHtml(formatCount(pesticides.event_count)) +
      '<span>recorded input events</span></p><dl class="programme-mini-facts">' +
      '<div><dt>Off-kit cues</dt><dd>' + escapeHtml(formatCount(pesticides.off_kit_review_cues)) + '</dd></div>' +
      '<div><dt>Timing context</dt><dd>' + escapeHtml(formatCount(pesticides.events_with_timing_context)) + '</dd></div>' +
      '</dl><p class="programme-note">' + escapeHtml(policy) + '.</p>');

    var received = freshness.latest_source_updated_at ? formatTime(freshness.latest_source_updated_at) : "No published timestamp";
    setHtml("programme-freshness", '<dl class="programme-mini-facts">' +
      '<div><dt>Latest received</dt><dd>' + escapeHtml(received) + '</dd></div>' +
      '<div><dt>Age</dt><dd>' + escapeHtml(formatAgeHours(freshness.age_hours)) + '</dd></div>' +
      '<div><dt>Source state</dt><dd>' + escapeHtml(sourceState) + '</dd></div>' +
      '</dl><p class="programme-note">Only published source records contribute here.</p>');
    if (currentRuntime) {
      renderOperationsBoard(currentRuntime);
    }
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

  function showView(viewName) {
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
  }

  function activateView(event) {
    showView(event.currentTarget.getAttribute("data-view"));
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
  }

  function renderPortfolioUnavailable() {
    currentPortfolio = null;
    if (currentRuntime) {
      renderCards(currentRuntime);
      renderDailyDirection();
      renderOperationsBoard(currentRuntime);
    }
    element("portfolio-status").textContent = "Actions are unavailable. Home is still usable.";
    setHtml("portfolio-ledger", '<p class="empty-state portfolio-unavailable">Risk and action context is unavailable right now.</p>');
    setHtml("portfolio-learning", '<p class="empty-state portfolio-unavailable">Trial and playbook context is unavailable right now.</p>');
  }

  function renderRiskLedger(portfolio) {
    var ledger = listedItems(portfolio.risk_action_ledger);
    var allocation = activeAllocation();
    if (allocation) {
      ledger = ledger.filter(function (item) { return item.allocation_id === allocation.id; });
    }
    if (!ledger.length) {
      setHtml("portfolio-ledger", '<p class="empty-state">' + (allocation ?
        'No risk or action is linked to this crop allocation.' :
        'No portfolio risks currently need action.') + '</p>');
      return;
    }
    setHtml("portfolio-ledger", ledger.slice(0, 6).map(function (item) {
      var severity = safeSeverity(item.severity);
      return '<article class="portfolio-item">' +
        '<h4>' + escapeHtml(item.title) + '</h4>' +
        '<p>' + escapeHtml(portfolioActionDetail(item)) + '</p>' +
        '<div class="portfolio-meta"><span class="severity severity-' + severity + '">' +
        escapeHtml(severity) + '</span><span class="status">' + escapeHtml(readable(item.status)) +
        '</span></div></article>';
    }).join(""));
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
      element("home-coverage-note").textContent = "No public operating map is configured. Individual farm locations are never shown by default.";
      setHtml("home-coverage-map", '<p class="map-empty">Add a reviewed public hub or network area to show a map here.</p>');
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
      element("home-coverage-note").textContent = "Public coverage is noted above. No map has been approved yet.";
      setHtml("home-coverage-map", '<p class="map-empty">No public map configured. Partner farms and field boundaries are not displayed here.</p>');
      renderMapExplorer(profile);
      return;
    }
    element("home-coverage-note").textContent = profile.network_summary
      ? "Public coverage, stated network scale, and hub only — no partner farms or field boundaries."
      : "Public network coverage and hub only — no partner farms or field boundaries.";
    setHtml("home-coverage-map", '<iframe title="Approved public operating coverage" loading="lazy" referrerpolicy="no-referrer" src="' +
      escapeHtml(profile.map_embed_url) + '"></iframe>');
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
    currentPortfolio = portfolio;
    if (currentRuntime) {
      renderCards(currentRuntime);
      renderDailyDirection();
      renderOperationsBoard(currentRuntime);
    }
    renderRiskLedger(portfolio);
    renderLearning(portfolio);
    element("portfolio-status").textContent = "Actions updated just now.";
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
    var fieldTeam = people.filter(function (person) {
      return ["field_operator", "agronomist", "farm_manager"].indexOf(person.role) !== -1;
    });
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
      boardPiece("fields", "landscape", "Fields", fieldStatus, fieldNames.length + (fieldNames.length === 1 ? " operating block" : " operating blocks"), fieldDetail, "Open crop work") +
      boardPiece("fields", "agriculture", "Crop", cropStatus, allocations.length + (allocations.length === 1 ? " active allocation" : " active allocations"), cropDetail, "Open crop work") +
      boardPiece("programme", "groups", "Field team", teamStatus, fieldTeam.length + (fieldTeam.length === 1 ? " field role" : " field roles"), teamDetail, "Open programme") +
      boardPiece("programme", "diversity_3", "Farmer programme", farmerStatus, farmerCount, farmerDetail + " Source programme context, not a canonical farmer record.", "Open programme")
    );
  }

  function allocationFact(label, value, missing) {
    return '<div><dt>' + escapeHtml(label) + '</dt><dd' + (missing ? ' class="is-missing"' : '') + '>' +
      escapeHtml(value) + '</dd></div>';
  }

  function renderAllocationCards(runtime) {
    var allocations = Array.isArray(runtime.allocations) ? runtime.allocations : [];
    var focused = activeAllocation(runtime);
    if (!allocations.length) {
      element("allocation-summary").textContent = "No active crop allocation has been recorded yet.";
      setHtml("allocation-list", '<p class="empty-state">Add a verified field and a crop allocation to start the operating loop.</p>');
      return;
    }
    element("allocation-summary").textContent = allocations.length === 1 ?
      "One active crop allocation is in focus. Its stage, work, and field record stay separate from public context." :
      "Choose one active crop allocation. The focused card drives the field pulse and linked actions.";
    setHtml("allocation-list", allocations.map(function (allocation) {
      var snapshot = allocationSnapshot(allocation, runtime);
      var focusedCard = focused && focused.id === allocation.id;
      var needs = snapshot.missing.length ? '<p class="allocation-gap"><strong>Needs:</strong> ' +
        escapeHtml(snapshot.missing.join(" · ")) + '</p>' : '';
      return '<button class="allocation-card' + (focusedCard ? ' is-focused' : '') + '" type="button" data-allocation-id="' +
        escapeHtml(allocation.id) + '" aria-pressed="' + String(Boolean(focusedCard)) + '">' +
        '<div class="allocation-card-heading"><h3>' + escapeHtml(allocation.operational_block_name || "Field") + '</h3>' +
        '<span class="status">' + (focusedCard ? 'in focus' : 'active') + '</span></div>' +
        '<p class="allocation-crop">' + escapeHtml(allocation.crop_name + (allocation.cultivar ? " · " + allocation.cultivar : "")) + '</p>' +
        '<dl class="allocation-facts">' +
        allocationFact("Stage", snapshot.stage, snapshot.stageMissing) +
        allocationFact("Next work", snapshot.nextWork, snapshot.workMissing) +
        allocationFact("Owner", snapshot.owner, snapshot.ownerMissing) +
        allocationFact("Evidence / record", snapshot.fieldRecord, snapshot.fieldRecordMissing) +
        '</dl>' + needs + '<span class="allocation-card-action">' +
        (focusedCard ? 'In focus' : 'Bring into focus') + '</span></button>';
    }).join(""));
  }

  function renderCards(runtime) {
    var workItems = runtime.work_items || [];
    var activeWork = workItems.filter(function (item) {
      return item.status === "planned" || item.status === "in_progress";
    });
    var submitted = workItems.filter(function (item) {
      return item.status === "submitted";
    });

    renderAllocationCards(runtime);
    element("active-work-count").textContent = activeWork.length;
    setHtml("active-work-summary", "<span>" + activeWork.filter(isOverdue).length + " overdue</span>");
    element("submitted-work-count").textContent = submitted.length;
    setHtml("submitted-work-summary", "<span>Requires manager review</span>");
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

  function renderPeople(runtime) {
    var people = Array.isArray(runtime.people) ? runtime.people : [];
    var workItems = Array.isArray(runtime.work_items) ? runtime.work_items : [];
    var relationshipSummary = runtime.person_operating_relationships || {};
    var relationships = Array.isArray(relationshipSummary.items) ? relationshipSummary.items : [];
    var relationshipAvailability = relationshipSummary.availability || "not_configured";
    if (!people.length) {
      setHtml("people-list", '<p class="empty-state">No farm team is recorded yet.</p>');
      return;
    }
    setHtml("people-list", people.map(function (person) {
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
      return '<article class="command-card person-card"><h3>' + escapeHtml(person.name) + '</h3>' +
        '<p class="person-role">' + escapeHtml(readable(person.role)) + '</p>' +
        '<p class="person-assignment">' + escapeHtml(assignmentCopy) + '</p>' +
        '<p class="person-work">' + assignedItems.length + (assignedItems.length === 1 ? ' open item' : ' open items') +
        (fields.length ? ' · ' + escapeHtml(fields.join(", ")) : '') + '</p></article>';
    }).join(""));
  }

  function latestFieldUpdate(runtime) {
    return runtime && runtime.latest_field_update && typeof runtime.latest_field_update === "object" ?
      runtime.latest_field_update : null;
  }

  function setDailyDirection(status, title, note, officerActivity, visitGap, nextMove, confidence, targetView) {
    element("field-crop").textContent = "Fortune paddy programme";
    element("field-title").textContent = title;
    element("field-note").textContent = note;
    element("field-stage").textContent = officerActivity;
    element("field-next-work").textContent = visitGap;
    element("field-owner").textContent = nextMove;
    element("field-update").textContent = confidence;
    element("field-status").textContent = status;
    element("field-status").className = status === "attention" ? "severity severity-high" : "status";
    setFocusAction(targetView === "settings" ? "Open system" : "Open programme", targetView, null);
  }

  function renderDailyDirection() {
    var programme = currentProgramme && currentProgramme.metrics ? currentProgramme.metrics : null;
    if (!programme) {
      if (!managerSessionAuthenticated) {
        setDailyDirection(
          "private", "Unlock today’s programme.",
          "Officer activity, visit gaps, and spreading issues become visible after manager access is unlocked.",
          "Private manager context", "Coverage not yet visible", "Unlock manager actions", "No source aggregate loaded", "settings"
        );
        return;
      }
      setDailyDirection(
        "unavailable", "Programme source is not ready.",
        "There is no published Fortune programme aggregate to steer from yet.",
        "No reporting-day activity", "No coverage denominator", "Review source state", "Published source unavailable", "programme"
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
        formatCount(filedToday) + " visits were filed by " + formatCount(filingOfficers) + " of " + formatCount(activeOfficers) + " active officers. Start with the coverage gap, then follow up by territory.",
        formatCount(filingOfficers) + " / " + formatCount(activeOfficers) + " officers filed", formatCount(overdue) + " programme members overdue",
        "Review territory follow-up", confidence, "programme"
      );
      return;
    }
    if (urgentIssue) {
      setDailyDirection(
        "attention", readable(urgentIssue.issue_code) + " is the lead field signal.",
        formatCount(urgentIssue.count) + " dated observations in the last " + formatCount(issues.window_days || 7) + " days. Detection shows where to look, not a diagnosis or prevalence rate.",
        formatCount(filedToday) + " visits filed today", formatCount(overdue) + " programme members overdue",
        "Review affected territories", confidence, "programme"
      );
      return;
    }
    setDailyDirection(
      overdue ? "attention" : "recorded", overdue ? formatCount(overdue) + " programme members are overdue for a visit." : "Programme coverage is current.",
      overdue ? "Start with the territories carrying the largest overdue gap. Never visited remains a separate acquisition and record-quality gap." :
        "No overdue visit gap is reported in the published programme aggregate.",
      formatCount(filedToday) + " visits filed today", formatCount(neverVisited) + " never visited",
      overdue ? "Review territory follow-up" : "Review programme", confidence, "programme"
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
    currentRuntime = runtime;
    element("today-heading").textContent = t("today");
    element("operating-unit").textContent = runtime.operating_unit ? runtime.operating_unit.name : "Current field operations";
    renderCards(runtime);
    renderPeople(runtime);
    renderDailyDirection();
    renderOperationsBoard(runtime);
    renderWork(runtime);
    renderActionAllocationContext(runtime);
    renderTodayFallback(runtime);
    loadMorningBrief(runtime);
    loadAllocationCalendars(runtime);
  }

  function renderRuntimeUnavailable() {
    currentRuntime = null;
    focusedAllocationId = null;
    allocationCalendars = {};
    element("operating-unit").textContent = "No farm has been set up yet.";
    element("field-crop").textContent = "Farm setup";
    element("field-title").textContent = "First field";
    element("field-note").textContent = "Add one farm, one live field, and the people who run it.";
    element("field-stage").textContent = "No stage plan";
    element("field-next-work").textContent = "No open work planned";
    element("field-owner").textContent = "No work owner set";
    element("field-update").textContent = "No field update recorded";
    element("field-status").textContent = "set up";
    element("field-status").className = "status";
    setFocusAction("Prepare first farm", "setup", null);
    element("today-count").textContent = "0";
    element("today-summary").textContent = "Reading the first-farm checklist…";
    element("allocation-summary").textContent = "No active crop allocation has been recorded yet.";
    setHtml("allocation-list", '<p class="empty-state">Add a verified field and a crop allocation to start the operating loop.</p>');
    setHtml("people-list", '<p class="empty-state">No farm team is recorded yet.</p>');
    setHtml("work-list", '<p class="empty-state">No farm work is shown until an active allocation exists.</p>');
    element("work-context").textContent = "No active crop allocation";
    element("actions-allocation-context").hidden = true;
    setHtml("today-list", '<p class="empty-state">Reading the first-farm checklist…</p>');
    renderOperationsBoard(null);
    loadPilotReadiness();
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
      return { view: "fields", exceptionId: entity.id, label: "Open issue" };
    }
    if (entity.type === "regional_signal" || entity.type === "source_registry") {
      return { view: "settings", exceptionId: null, label: "Open data connections" };
    }
    if (entity.type === "field_information_request") {
      return { view: "actions", exceptionId: null, label: t("openFieldAsks") };
    }
    return { view: "fields", exceptionId: null, label: "Open field work" };
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
      (action.view === "actions" ? element("ledger-heading") : element("work-heading"));
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  function clearSetupFeedback() {
    element("setup-error").hidden = true;
    element("setup-error").textContent = "";
    element("setup-result").hidden = true;
    element("setup-result").innerHTML = "";
  }

  function showSetupError(message) {
    element("setup-error").textContent = message;
    element("setup-error").hidden = false;
  }

  function buildQuickSetup(form) {
    var area = Number(formValue(form, "area_hectares"));
    var locationHint = formValue(form, "location_hint").trim();
    if (!isFinite(area) || area <= 0) {
      throw new Error("Area must be a positive number.");
    }
    if (!locationHint) {
      throw new Error("Add a village or six-digit PIN.");
    }
    return {
      farm_name: formValue(form, "farm_name"),
      manager_name: formValue(form, "manager_name"),
      field_name: formValue(form, "field_name"),
      crop_name: formValue(form, "crop_name"),
      area_hectares: area,
      state_name: formValue(form, "state_name"),
      district_name: formValue(form, "district_name"),
      village_name: /^[0-9]{6}$/.test(locationHint) ? null : locationHint,
      pincode: /^[0-9]{6}$/.test(locationHint) ? locationHint : null
    };
  }

  function renderQuickSetup(result) {
    var remaining = Array.isArray(result.still_needed_before_acceptance) ? result.still_needed_before_acceptance : [];
    element("setup-result").innerHTML = '<h3>Good starting point.</h3><p>' +
      escapeHtml(result.farm.name) + ' · ' + escapeHtml(result.field.name) + ' · ' +
      escapeHtml(result.field.crop_name) + ' · ' + escapeHtml(result.location.district_name) + '</p><ul>' + remaining.map(function (item) {
        return '<li>' + escapeHtml(item) + '</li>';
      }).join("") + '</ul><p>Nothing has been saved, mapped, or assigned from this check.</p>';
    element("setup-result").hidden = false;
  }

  function setSetupMode(mode) {
    var fieldMode = mode !== "file";
    element("setup-field-mode").hidden = !fieldMode;
    element("setup-file-mode").hidden = fieldMode;
    element("validate-setup").hidden = !fieldMode;
    element("setup-footer-copy").textContent = fieldMode
      ? "You will only add land rights, season dates, and the first work after this basic check."
      : "The file stays on this device while we recognize its header. A manager reviews any real import before it is retained.";
    Array.prototype.forEach.call(document.querySelectorAll("[data-setup-mode]"), function (button) {
      var selected = button.getAttribute("data-setup-mode") === (fieldMode ? "field" : "file");
      button.classList.toggle("is-active", selected);
      button.setAttribute("aria-selected", String(selected));
    });
    clearSetupFeedback();
  }

  function csvHeader(source) {
    var cells = [];
    var cell = "";
    var quoted = false;
    var index;
    for (index = 0; index < source.length; index += 1) {
      var character = source.charAt(index);
      if (character === '"') {
        if (quoted && source.charAt(index + 1) === '"') {
          cell += '"';
          index += 1;
        } else {
          quoted = !quoted;
        }
      } else if (character === "," && !quoted) {
        cells.push(cell.trim());
        cell = "";
      } else if ((character === "\n" || character === "\r") && !quoted) {
        if (character === "\r" && source.charAt(index + 1) === "\n") {
          index += 1;
        }
        cells.push(cell.trim());
        return cells;
      } else {
        cell += character;
      }
    }
    cells.push(cell.trim());
    return cells;
  }

  function canonicalCsvHeader(value) {
    return String(value || "").replace(/^\uFEFF/, "").toLowerCase().replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "");
  }

  function setFileResult(html, status) {
    var result = element("setup-file-result");
    result.className = "file-result" + (status ? " is-" + status : "");
    result.innerHTML = html;
  }

  function recognizeCsvFile(file) {
    element("setup-file-name").textContent = file ? file.name : "No file chosen.";
    if (!file) {
      setFileResult("<p>A farm/plot list helps map verified fields. A purchase ledger helps show village and variety history. They stay separate.</p>");
      return;
    }
    if (file.size > 3 * 1024 * 1024) {
      setFileResult("<p>This file is larger than the quick check. Use a CSV under 3 MB, or ask the team to split an export.</p>", "warning");
      return;
    }
    var reader = new FileReader();
    reader.onerror = function () {
      setFileResult("<p>We could not read that file. Please choose a UTF-8 CSV.</p>", "warning");
    };
    reader.onload = function () {
      var headers = csvHeader(String(reader.result || "")).map(canonicalCsvHeader);
      var present = {};
      headers.forEach(function (header) { present[header] = true; });
      var procurement = ["entry_date", "village", "rate_per_qtl", "paddy_quantity_qtl", "variety_type"];
      var manifest = ["source_farm_id", "record_status", "state_name", "district_name", "village_name", "pincode", "source_recorded_at", "source_record_ref"];
      var isProcurement = procurement.every(function (header) { return present[header]; });
      var isManifest = manifest.every(function (header) { return present[header]; });
      if (isProcurement) {
        setFileResult("<h3>Purchase history recognized.</h3><p>We will keep only monthly village, variety, quantity, bag, and rate cohorts—not names, purchase numbers, PO names, or bills. A manager reviews it before retention.</p>", "ready");
      } else if (isManifest) {
        setFileResult("<h3>Farm / plot list recognized.</h3><p>We will check IDs, location hierarchy, and any verified field proof before it can appear on the map. Village and PIN never create a field pin on their own.</p>", "ready");
      } else {
        setFileResult("<h3>We do not recognize this safely yet.</h3><p>Use a farm / plot CSV or the purchase-history format. Nothing from this file has left this device.</p>", "warning");
      }
    };
    reader.readAsText(file.slice(0, 65536));
  }

  function openSetupDialog() {
    clearSetupFeedback();
    var dialog = element("setup-dialog");
    if (!dialog.open) {
      dialog.showModal();
    }
    var firstInput = element("setup-form").querySelector("input[name='farm_name']");
    if (firstInput) {
      firstInput.focus();
    }
  }

  function validateSetup(event) {
    event.preventDefault();
    var form = event.currentTarget;
    clearSetupFeedback();
    if (!form.reportValidity()) {
      return;
    }
    var proposal;
    try {
      proposal = buildQuickSetup(form);
    } catch (error) {
      showSetupError(error.message || "Complete the basic field details.");
      return;
    }
    var submit = element("validate-setup");
    submit.disabled = true;
    submit.textContent = "Checking…";
    fetch(quickStartValidationUrl, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(proposal)
    })
      .then(function (response) {
        return response.json().then(function (body) {
          if (!response.ok) {
            throw new Error(body.detail || "The field could not be checked.");
          }
          return body;
        });
      })
      .then(renderQuickSetup)
      .catch(function (error) {
        showSetupError(error.message || "The field could not be checked.");
      })
      .finally(function () {
        submit.disabled = false;
        submit.innerHTML = 'Check this field <span class="material-symbols-outlined" aria-hidden="true">arrow_forward</span>';
      });
  }

  function loadActionCentre() {
    element("load-status").textContent = "Loading…";
    element("portfolio-status").textContent = "Loading actions…";
    loadProgramme();
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
        element("load-status").textContent = "Set up the farm to begin.";
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

    fetch(dataLanesUrl)
      .then(function (response) {
        if (!response.ok) {
          throw new Error("Unable to load data-lane readiness.");
        }
        return response.json();
      })
      .then(renderDataLanes)
      .catch(renderDataLanesUnavailable);

    fetch(operatingProfileUrl)
      .then(function (response) {
        if (!response.ok) {
          throw new Error("Unable to load operating profile.");
        }
        return response.json();
      })
      .then(renderOperatingProfile)
      .catch(renderOperatingProfileUnavailable);
  }

  Array.prototype.forEach.call(document.querySelectorAll(".command-tab"), function (tab) {
    tab.addEventListener("click", activateView);
    tab.addEventListener("keydown", moveTab);
  });
  element("operations-board").addEventListener("click", function (event) {
    var piece = event.target.closest("[data-board-view]");
    if (!piece) {
      return;
    }
    var view = piece.getAttribute("data-board-view");
    showView(view);
    var target = view === "programme" ? element("programme-coverage-heading") : element("allocations-heading");
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });
  element("allocation-list").addEventListener("click", function (event) {
    var allocationCard = event.target.closest("[data-allocation-id]");
    if (allocationCard) {
      selectAllocation(allocationCard.getAttribute("data-allocation-id"));
    }
  });
  element("open-focused-field").addEventListener("click", function () {
    showView("fields");
    element("allocations-heading").scrollIntoView({ behavior: "smooth", block: "start" });
  });
  element("close-setup").addEventListener("click", function () {
    element("setup-dialog").close();
  });
  element("setup-dialog").addEventListener("cancel", function () {
    clearSetupFeedback();
  });
  element("setup-form").addEventListener("submit", validateSetup);
  Array.prototype.forEach.call(document.querySelectorAll("[data-setup-mode]"), function (button) {
    button.addEventListener("click", function () {
      setSetupMode(button.getAttribute("data-setup-mode"));
    });
  });
  element("setup-file").addEventListener("change", function (event) {
    recognizeCsvFile(event.target.files && event.target.files[0]);
  });
  element("open-map").addEventListener("click", function () {
    showView("map");
    element("map-stage-heading").scrollIntoView({ behavior: "smooth", block: "start" });
  });
  element("open-system").addEventListener("click", function () {
    showView("settings");
    element("settings-heading").scrollIntoView({ behavior: "smooth", block: "start" });
  });
  Array.prototype.forEach.call(document.querySelectorAll("[data-return-view]"), function (button) {
    button.addEventListener("click", function () {
      showView(button.getAttribute("data-return-view"));
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  });
  element("close-action").addEventListener("click", function () {
    element("action-dialog").close();
  });
  element("action-dialog").addEventListener("cancel", function () {
    pendingAction = null;
  });
  element("action-go").addEventListener("click", followActionDetail);
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
    if (focusTargetView === "setup") {
      openSetupDialog();
      return;
    }
    showView(focusTargetView);
    if (focusExceptionId) {
      loadException(focusExceptionId);
      element("audit").scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    if (focusTargetView === "fields") {
      element("work-heading").scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    if (focusTargetView === "programme") {
      element("programme-coverage-heading").scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    if (focusTargetView === "settings") {
      element("settings-heading").scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });
  element("today-list").addEventListener("click", function (event) {
    var firstFarm = event.target.closest("[data-first-farm]");
    if (firstFarm) {
      openSetupDialog();
      return;
    }
    var button = event.target.closest("[data-today-index]");
    if (button) {
      openActionDetail(currentAttention[Number(button.getAttribute("data-today-index"))]);
    }
  });
  applyLanguage();
  loadManagerSessionStatus().then(loadActionCentre);
}());
