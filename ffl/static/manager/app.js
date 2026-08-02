(function () {
  "use strict";

  var runtimeUrl = "/api/v1/runtime";
  var portfolioUrl = "/api/v1/portfolio";
  var dataLanesUrl = "/api/v1/data-lanes";
  var operatingProfileUrl = "/api/v1/operating-profile";
  var pilotReadinessUrl = "/api/v1/pilot/readiness";
  var quickStartValidationUrl = "/api/v1/pilot/quick-start/validate";
  var currentRuntime = null;
  var currentAttention = [];
  var pendingAction = null;
  var focusExceptionId = null;
  var focusTargetView = "fields";
  var localeStorageKey = "ffl.manager.interface-locale";
  var interfaceLocale = window.localStorage.getItem(localeStorageKey) === "hi" ? "hi" : "en";
  var copy = {
    en: {
      navHome: "Home", navFields: "Fields", navFarmers: "Farmers", navActions: "Actions", navSettings: "Settings",
      refresh: "Refresh", pageTitle: "Today.", fieldPulse: "Field pulse", lastUpdate: "Last update", from: "From",
      openFieldWork: "Open field work", today: "Today", openWork: "Open work", awaitingReview: "Awaiting review",
      currentFields: "Current fields", work: "Work", selectedSignal: "Selected signal", review: "Review",
      priority: "Priority", riskAction: "Risk & action", learning: "Learning", trialsPlaybooks: "Trials & playbooks",
      operatingProfile: "Operating profile", coverage: "Coverage", interface: "Interface", language: "Language",
      languageHelp: "Choose Hindi or English for the interface. Farm records remain exactly as entered.",
      dataConnections: "Data connections", fiveDataLanes: "Five data lanes",
      lanesIntro: "What is usable now, what is missing, and the next safe move.", nextMove: "Next move"
    },
    hi: {
      navHome: "होम", navFields: "खेत", navFarmers: "किसान", navActions: "काम", navSettings: "सेटिंग्स",
      refresh: "ताज़ा करें", pageTitle: "आज।", fieldPulse: "खेत की स्थिति", lastUpdate: "आख़िरी अपडेट", from: "किससे",
      openFieldWork: "खेत का काम खोलें", today: "आज", openWork: "खुला काम", awaitingReview: "समीक्षा के लिए",
      currentFields: "मौजूदा खेत", work: "काम", selectedSignal: "चुना हुआ संकेत", review: "समीक्षा",
      priority: "प्राथमिकता", riskAction: "जोखिम और अगला काम", learning: "सीख", trialsPlaybooks: "परीक्षण और तरीके",
      operatingProfile: "ऑपरेटिंग प्रोफ़ाइल", coverage: "कवरेज", interface: "इंटरफ़ेस", language: "भाषा",
      languageHelp: "इंटरफ़ेस के लिए हिंदी या अंग्रेज़ी चुनें। खेत के रिकॉर्ड जैसे दर्ज किए गए हैं वैसे ही रहेंगे।",
      dataConnections: "डेटा कनेक्शन", fiveDataLanes: "पांच डेटा लेन",
      lanesIntro: "क्या उपयोगी है, क्या नहीं है, और अगला सुरक्षित कदम।", nextMove: "अगला कदम"
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
  }

  function formatTime(value) {
    if (!value) {
      return "Not scheduled";
    }
    var date = new Date(value);
    return isNaN(date.getTime()) ? value : date.toLocaleString(interfaceLocale === "hi" ? "hi-IN" : "en-IN");
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
    element("portfolio-status").textContent = "Actions are unavailable. Home is still usable.";
    setHtml("portfolio-ledger", '<p class="empty-state portfolio-unavailable">Risk and action context is unavailable right now.</p>');
    setHtml("portfolio-learning", '<p class="empty-state portfolio-unavailable">Trial and playbook context is unavailable right now.</p>');
  }

  function renderRiskLedger(portfolio) {
    var ledger = listedItems(portfolio.risk_action_ledger);
    if (!ledger.length) {
      setHtml("portfolio-ledger", '<p class="empty-state">No portfolio risks currently need action.</p>');
      return;
    }
    setHtml("portfolio-ledger", ledger.slice(0, 6).map(function (item) {
      var severity = safeSeverity(item.severity);
      return '<article class="portfolio-item">' +
        '<h4>' + escapeHtml(item.title) + '</h4>' +
        '<p>' + escapeHtml(readable(item.action)) + '</p>' +
        '<div class="portfolio-meta"><span class="severity severity-' + severity + '">' +
        escapeHtml(severity) + '</span><span class="status">' + escapeHtml(readable(item.status)) +
        '</span></div></article>';
    }).join(""));
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
      return;
    }
    element("home-coverage-note").textContent = profile.network_summary
      ? "Public coverage, stated network scale, and hub only — no partner farms or field boundaries."
      : "Public network coverage and hub only — no partner farms or field boundaries.";
    setHtml("home-coverage-map", '<iframe title="Approved public operating coverage" loading="lazy" referrerpolicy="no-referrer" src="' +
      escapeHtml(profile.map_embed_url) + '"></iframe>');
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

  function renderCards(runtime) {
    var allocations = runtime.allocations || [];
    var workItems = runtime.work_items || [];
    var activeWork = workItems.filter(function (item) {
      return item.status === "planned" || item.status === "in_progress";
    });
    var submitted = workItems.filter(function (item) {
      return item.status === "submitted";
    });

    setHtml("allocation-list", allocations.length ? allocations.map(function (allocation) {
      return "<span>" + escapeHtml(allocation.operational_block_name || "Field") + " · " + escapeHtml(allocation.crop_name) +
        (allocation.cultivar ? " · " + escapeHtml(allocation.cultivar) : "") + "</span>";
    }).join("") : "<span>No active allocation.</span>");
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
      return '<article class="command-card person-card"><h3>' + escapeHtml(person.name) + '</h3>' +
        '<p class="person-role">' + escapeHtml(readable(person.role)) + '</p>' +
        '<p class="person-work">' + assignedItems.length + (assignedItems.length === 1 ? ' open item' : ' open items') +
        (fields.length ? ' · ' + escapeHtml(fields.join(", ")) : '') + '</p></article>';
    }).join(""));
  }

  function latestFieldUpdate(runtime) {
    return runtime && runtime.latest_field_update && typeof runtime.latest_field_update === "object" ?
      runtime.latest_field_update : null;
  }

  function renderFieldPulse(runtime) {
    var allocations = runtime.allocations || [];
    var exceptions = (runtime.exceptions || []).filter(isOpenException);
    var focus = exceptions[0] || null;
    var allocation = allocations[0] || null;
    var update = latestFieldUpdate(runtime);
    var crop = allocation ? allocation.crop_name + (allocation.cultivar ? " · " + allocation.cultivar : "") : "No active crop";

    element("field-crop").textContent = crop;
    element("field-update").textContent = update ? formatTime(update.observed_at) : "No field update recorded.";
    element("field-reporter").textContent = update ? update.submitted_by : "—";
    if (focus) {
      element("field-title").textContent = fieldNameFor(focus.allocation_id);
      element("field-note").textContent = focus.title;
      element("field-status").textContent = focus.severity;
      element("field-status").className = "severity severity-" + safeSeverity(focus.severity);
      setFocusAction("Open issue", "fields", focus.id);
      return;
    }
    element("field-title").textContent = allocation ? (allocation.operational_block_name || "Field") : "First field";
    element("field-note").textContent = update ? "Latest update is recorded." :
      (allocation ? "Waiting for the first field update." : "Add the first crop allocation to begin.");
    element("field-status").textContent = update ? readable(update.status) : "waiting";
    element("field-status").className = "status";
    setFocusAction("Open field work", "fields", null);
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

  function renderWork(workItems) {
    var openWork = workItems.filter(isOpenWork);
    if (!openWork.length) {
      setHtml("work-list", '<p class="empty-state">No open work requires attention.</p>');
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

  function renderRuntime(runtime) {
    currentRuntime = runtime;
    element("today-heading").textContent = t("today");
    element("operating-unit").textContent = runtime.operating_unit ? runtime.operating_unit.name : "Current field operations";
    renderCards(runtime);
    renderPeople(runtime);
    renderFieldPulse(runtime);
    renderWork(runtime.work_items || []);
    renderTodayFallback(runtime);
    loadMorningBrief(runtime);
  }

  function renderRuntimeUnavailable() {
    element("operating-unit").textContent = "No farm has been set up yet.";
    element("field-crop").textContent = "Farm setup";
    element("field-title").textContent = "First field";
    element("field-note").textContent = "Add one farm, one live field, and the people who run it.";
    element("field-update").textContent = "No field update recorded.";
    element("field-reporter").textContent = "—";
    element("field-status").textContent = "set up";
    element("field-status").className = "status";
    setFocusAction("Prepare first farm", "setup", null);
    element("today-count").textContent = "0";
    element("today-summary").textContent = "Reading the first-farm checklist…";
    setHtml("allocation-list", "<span>No active allocation.</span>");
    setHtml("people-list", '<p class="empty-state">No farm team is recorded yet.</p>');
    setHtml("work-list", '<p class="empty-state">No farm work is shown until an active allocation exists.</p>');
    setHtml("today-list", '<p class="empty-state">Reading the first-farm checklist…</p>');
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
    var target = action.view === "settings" ? element("context-heading") : element("work-heading");
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
    if (!isFinite(area) || area <= 0) {
      throw new Error("Area must be a positive number.");
    }
    return {
      farm_name: formValue(form, "farm_name"),
      manager_name: formValue(form, "manager_name"),
      field_name: formValue(form, "field_name"),
      crop_name: formValue(form, "crop_name"),
      area_hectares: area,
      state_name: formValue(form, "state_name"),
      district_name: formValue(form, "district_name"),
      village_name: formValue(form, "village_name") || null,
      pincode: formValue(form, "pincode") || null
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
  loadActionCentre();
}());
