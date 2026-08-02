(function () {
  "use strict";

  var runtimeUrl = "/api/v1/runtime";
  var portfolioUrl = "/api/v1/portfolio";
  var pilotReadinessUrl = "/api/v1/pilot/readiness";
  var pilotValidationUrl = "/api/v1/pilot/setup/validate";
  var currentRuntime = null;
  var focusExceptionId = null;
  var focusTargetView = "fields";

  function element(id) {
    return document.getElementById(id);
  }

  function text(value) {
    return value === null || value === undefined || value === "" ? "Not assigned" : String(value);
  }

  function formatTime(value) {
    if (!value) {
      return "Not scheduled";
    }
    var date = new Date(value);
    return isNaN(date.getTime()) ? value : date.toLocaleString();
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

  function nextAction(exceptionRecord) {
    var actions = {
      reported: "Triage the exception and record the assessment.",
      triaged: "Assign an accountable owner or accept the risk.",
      owned: "Owner to mitigate the exception and record progress.",
      mitigated: "Start monitoring to verify the mitigation.",
      monitoring: "Verify the outcome and resolve, or reopen if it recurs.",
      resolved: "Review the outcome; reopen if conditions recur.",
      accepted_risk: "Review the accepted risk; reopen if conditions change.",
      reopened: "Return the exception to triage and reassess ownership."
    };
    return Object.prototype.hasOwnProperty.call(actions, exceptionRecord.status) ?
      actions[exceptionRecord.status] : "";
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

  function totalCount(summary) {
    return summary && typeof summary.total_count === "number" ? summary.total_count : 0;
  }

  function safeSeverity(value) {
    return ["critical", "high", "medium", "low", "info"].indexOf(value) === -1 ? "medium" : value;
  }

  function formValue(form, name) {
    return String(new FormData(form).get(name) || "").trim();
  }

  function localTimestamp(value) {
    var date = new Date(value);
    if (!value || isNaN(date.getTime())) {
      return "";
    }
    var offset = -date.getTimezoneOffset();
    var sign = offset >= 0 ? "+" : "-";
    var absolute = Math.abs(offset);
    var hours = String(Math.floor(absolute / 60)).padStart(2, "0");
    var minutes = String(absolute % 60).padStart(2, "0");
    return (value.length === 16 ? value + ":00" : value) + sign + hours + ":" + minutes;
  }

  function districtContextKey(districtName) {
    var slug = districtName.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
    return slug ? "up:" + slug : "";
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
    element("portfolio-status").textContent = "Tools are unavailable. Home is still usable.";
    setHtml("portfolio-ledger", '<p class="empty-state portfolio-unavailable">Risk and action context is unavailable right now.</p>');
    setHtml("portfolio-context", '<p class="empty-state portfolio-unavailable">Source and import context is unavailable right now.</p>');
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

  function renderSourceHealth(sources) {
    var availability = sources && sources.availability ? readable(sources.availability) : "unavailable";
    var configuredCount = sources && typeof sources.configured_count === "number" ? sources.configured_count : 0;
    var attention = totalCount(sources && sources.attention);
    if (availability === "not configured") {
      return '<p class="empty-state">No approved external source is configured yet.</p>';
    }
    if (availability !== "available") {
      return '<p class="empty-state portfolio-unavailable">Source health is ' + escapeHtml(availability) + '.</p>';
    }
    return '<dl class="portfolio-counts"><div><dt>Configured sources</dt><dd>' + configuredCount +
      '</dd></div><div><dt>Sources needing attention</dt><dd>' + attention + '</dd></div></dl>';
  }

  function renderImportReview(imports) {
    var availability = imports && imports.availability ? readable(imports.availability) : "unavailable";
    if (availability !== "available") {
      return '<p class="empty-state portfolio-unavailable">Import review is ' + escapeHtml(availability) + '.</p>';
    }
    return '<dl class="portfolio-counts"><div><dt>Imports awaiting review</dt><dd>' +
      totalCount(imports.review_required) + '</dd></div></dl>';
  }

  function renderDataContext(portfolio) {
    setHtml("portfolio-context", '<div class="portfolio-item"><h4>Source health</h4>' +
      renderSourceHealth(portfolio.sources) + '</div><div class="portfolio-item"><h4>Import review</h4>' +
      renderImportReview(portfolio.imports) + '</div>');
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
    renderDataContext(portfolio);
    renderLearning(portfolio);
    element("portfolio-status").textContent = "Tools updated just now.";
  }

  function renderPilotReadiness(readiness) {
    var progress = readiness && readiness.progress ? readiness.progress : { completed: 0, total: 6 };
    var stages = readiness && Array.isArray(readiness.stages) ? readiness.stages : [];
    var nextStage = readiness && readiness.next_stage ? readiness.next_stage : null;
    element("today-heading").textContent = "First farm";
    element("exception-count").textContent = progress.completed + "/" + progress.total;
    element("exception-summary").textContent = nextStage ?
      "Start with " + nextStage.title.toLowerCase() + "." :
      "The minimum field loop is ready.";
    setHtml("exception-list", stages.slice(0, 3).map(function (stage) {
      var ready = stage.status === "ready";
      return '<article class="queue-item foundation-item"><div class="item-title"><h3>' +
        escapeHtml(stage.title) + '</h3><span class="status">' +
        (ready ? "ready" : "next") + '</span></div><p>' +
        escapeHtml(ready ? "Recorded and ready for the field loop." : stage.next_action) +
        '</p></article>';
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
        element("today-heading").textContent = "First farm";
        element("exception-count").textContent = "0/6";
        element("exception-summary").textContent = "Prepare one real farm before external data can help.";
        setHtml("exception-list", '<p class="empty-state">Farm, field, people, place, soil report, then the first work loop.</p>');
      });
  }

  function renderCards(runtime) {
    var allocations = runtime.allocations || [];
    var workItems = runtime.work_items || [];
    var exceptions = (runtime.exceptions || []).filter(isOpenException);
    var activeWork = workItems.filter(function (item) {
      return item.status === "planned" || item.status === "in_progress";
    });
    var submitted = workItems.filter(function (item) {
      return item.status === "submitted";
    });

    element("allocation-count").textContent = allocations.length;
    setHtml("allocation-list", allocations.length ? allocations.map(function (allocation) {
      return "<span>" + escapeHtml(allocation.crop_name) +
        (allocation.cultivar ? " · " + escapeHtml(allocation.cultivar) : "") + "</span>";
    }).join("") : "<span>No active allocation.</span>");
    element("active-work-count").textContent = activeWork.length;
    setHtml("active-work-summary", "<span>" + activeWork.filter(isOverdue).length + " overdue</span>");
    element("submitted-work-count").textContent = submitted.length;
    setHtml("submitted-work-summary", "<span>Requires manager review</span>");
    element("exception-count").textContent = exceptions.length;
    element("exception-summary").textContent = exceptions.length ?
      exceptions.length + (exceptions.length === 1 ? " open field signal needs a decision." : " open field signals need decisions.") :
      "No open field signals. Keep the evidence loop moving.";
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

  function exceptionFor(exceptionId) {
    var exceptions = currentRuntime && Array.isArray(currentRuntime.exceptions) ? currentRuntime.exceptions : [];
    return exceptions.filter(function (item) { return item.id === exceptionId; })[0] || null;
  }

  function setFocusAction(label, targetView, exceptionId, ownerId) {
    focusTargetView = targetView;
    focusExceptionId = exceptionId || null;
    element("focus-action-label").textContent = label;
    element("focus-owner").textContent = ownerId ? "Owner · " + personName(ownerId) : "";
  }

  function renderPeople(runtime) {
    var people = Array.isArray(runtime.people) ? runtime.people : [];
    var workItems = Array.isArray(runtime.work_items) ? runtime.work_items : [];
    if (!people.length) {
      setHtml("people-list", '<p class="empty-state">No farm team is recorded yet.</p>');
      return;
    }
    setHtml("people-list", people.map(function (person) {
      var assigned = workItems.filter(function (item) {
        return item.owner_id === person.id && isOpenWork(item);
      }).length;
      return '<article class="command-card person-card"><h3>' + escapeHtml(person.name) + '</h3>' +
        '<p class="person-role">' + escapeHtml(readable(person.role)) + '</p>' +
        '<p class="person-work">' + assigned + (assigned === 1 ? ' open item' : ' open items') + '</p></article>';
    }).join(""));
  }

  function renderFieldFocus(runtime) {
    var allocations = runtime.allocations || [];
    var exceptions = (runtime.exceptions || []).filter(isOpenException);
    var focus = exceptions[0] || null;
    var allocation = allocations[0] || null;
    var crop = allocation ? allocation.crop_name + (allocation.cultivar ? " · " + allocation.cultivar : "") : "Field ledger";

    element("focus-kicker").textContent = "Field focus";
    element("focus-crop").textContent = crop;
    if (focus) {
      element("focus-title").textContent = focus.title;
      element("focus-note").textContent = nextAction(focus) || "Review the field signal with its linked evidence.";
      element("focus-severity").textContent = focus.severity;
      element("focus-severity").className = "severity severity-" + safeSeverity(focus.severity);
      setFocusAction("Review signal", "fields", focus.id, focus.owner_id);
      return;
    }
    element("focus-title").textContent = allocation ? "Keep the next pass close." : "The field is ready for its first allocation.";
    element("focus-note").textContent = allocation ? "No open exception is blocking this allocation right now." : "Add a crop allocation to begin the evidence ledger.";
    element("focus-severity").textContent = "Clear";
    element("focus-severity").className = "severity severity-low";
    setFocusAction("Open field work", "fields", null, null);
  }

  function renderMorningBrief(brief) {
    var attention = brief && Array.isArray(brief.attention) ? brief.attention : [];
    var item = attention[0];
    if (!item || !item.entity) {
      return;
    }
    var entityType = item.entity.type;
    var entityId = item.entity.id;
    var contextLabels = {
      operating_unit: "Farm context",
      soil_baseline: "Soil baseline",
      source_registry: "Data source",
      regional_signal: "District context",
      crop_stage_checkpoint: "Field checkpoint"
    };
    var ownerId = null;
    var targetView = "tools";
    var actionLabel = "Open tools";
    var exception = entityType === "exception_record" ? exceptionFor(entityId) : null;
    var work = entityType === "work_item" ? workFor(entityId) : null;
    if (exception) {
      ownerId = exception.owner_id;
      targetView = "fields";
      actionLabel = "Review signal";
    } else if (work) {
      ownerId = work.owner_id;
      targetView = "fields";
      actionLabel = "Open field work";
    }
    element("focus-kicker").textContent = "Next move · " + readable(item.priority);
    if (Object.prototype.hasOwnProperty.call(contextLabels, entityType)) {
      element("focus-crop").textContent = contextLabels[entityType];
    }
    element("focus-title").textContent = item.title;
    element("focus-note").textContent = item.detail;
    element("focus-severity").textContent = item.priority;
    element("focus-severity").className = "severity severity-" + safeSeverity(item.priority);
    setFocusAction(actionLabel, targetView, exception ? exception.id : null, ownerId);
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
        // cannot be composed. It is a decision aid, never a source of record.
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
        "<div class=\"item-title\"><h3>" + escapeHtml(item.title) + "</h3>" +
        "<span class=\"status status-" + escapeHtml(item.status) + "\">" + escapeHtml(item.status) + "</span></div>" +
        "<dl class=\"facts\"><div><dt>Owner</dt><dd>" + escapeHtml(personName(item.owner_id)) + "</dd></div>" +
        "<div><dt>Due</dt><dd>" + escapeHtml(formatTime(item.due_at)) + "</dd></div>" +
        "<div><dt>Timing</dt><dd class=\"" + (overdue ? "overdue" : "") + "\">" + (overdue ? "Overdue" : "On schedule") + "</dd></div></dl>" +
        "</article>";
    }).join(""));
  }

  function renderExceptions(exceptions) {
    var openExceptions = exceptions.filter(isOpenException);
    if (!openExceptions.length) {
      setHtml("exception-list", '<p class="empty-state">No open exceptions.</p>');
      return;
    }
    setHtml("exception-list", openExceptions.map(function (item) {
      var action = nextAction(item);
      var state = action ? escapeHtml(item.status) : "Unsupported exception state";
      return "<article class=\"queue-item exception-item\">" +
        "<div class=\"item-title\"><h3>" + escapeHtml(item.title) + "</h3>" +
        "<span class=\"severity severity-" + escapeHtml(item.severity) + "\">" + escapeHtml(item.severity) + "</span></div>" +
        "<dl class=\"facts\"><div><dt>Owner</dt><dd>" + escapeHtml(personName(item.owner_id)) + "</dd></div>" +
        "<div><dt>Fallback owner</dt><dd>" + escapeHtml(personName(item.fallback_owner_id)) + "</dd></div>" +
        "<div><dt>Observed</dt><dd>" + escapeHtml(formatTime(item.observed_at)) + "</dd></div>" +
        "<div><dt>Current state</dt><dd>" + state + "</dd></div>" +
        "<div><dt>Next action</dt><dd>" + escapeHtml(action) + "</dd></div></dl>" +
        "<button class=\"detail-button\" type=\"button\" data-exception-id=\"" + escapeHtml(item.id) + "\">View audit history</button>" +
        "</article>";
    }).join(""));
  }

  function renderRuntime(runtime) {
    currentRuntime = runtime;
    element("today-heading").textContent = "Today";
    element("operating-unit").textContent = runtime.operating_unit ? runtime.operating_unit.name : "Current field operations";
    renderCards(runtime);
    renderPeople(runtime);
    renderFieldFocus(runtime);
    renderWork(runtime.work_items || []);
    renderExceptions(runtime.exceptions || []);
    loadMorningBrief(runtime);
  }

  function renderRuntimeUnavailable() {
    element("operating-unit").textContent = "No farm has been set up yet.";
    element("allocation-count").textContent = "0";
    element("focus-crop").textContent = "Farm setup";
    element("focus-kicker").textContent = "Farm setup";
    element("focus-title").textContent = "Make the first field real.";
    element("focus-note").textContent = "One farm, one live field, named people, and the next proof. Nothing invented.";
    element("focus-severity").textContent = "Set up";
    element("focus-severity").className = "severity severity-medium";
    setFocusAction("Prepare first farm", "setup", null, null);
    element("exception-count").textContent = "0";
    element("exception-summary").textContent = "Reading the real setup requirements…";
    setHtml("allocation-list", "<span>No active allocation.</span>");
    setHtml("people-list", '<p class="empty-state">No farm team is recorded yet.</p>');
    setHtml("work-list", '<p class="empty-state">No farm work is shown until an active allocation exists.</p>');
    setHtml("exception-list", '<p class="empty-state">Reading the first-farm setup…</p>');
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

  function buildSetupProposal(form) {
    var districtName = formValue(form, "district_name");
    var area = Number(formValue(form, "area_hectares"));
    var verifiedAt = localTimestamp(formValue(form, "verified_at"));
    var workDueAt = localTimestamp(formValue(form, "first_work_due_at"));
    if (!districtContextKey(districtName)) {
      throw new Error("Enter the district in English so its reviewed UP source context can be matched.");
    }
    if (!isFinite(area) || area <= 0) {
      throw new Error("Usable hectares must be a positive number.");
    }
    if (!verifiedAt || !workDueAt) {
      throw new Error("Location verification time and first work due time are both required.");
    }
    var location = {
      state_name: "Uttar Pradesh",
      district_name: districtName,
      district_context_key: districtContextKey(districtName),
      verified_at: verifiedAt
    };
    var village = formValue(form, "village_name");
    var pincode = formValue(form, "pincode");
    if (village) {
      location.village_name = village;
    }
    if (pincode) {
      location.pincode = pincode;
    }
    return {
      farm_name: formValue(form, "farm_name"),
      people: [
        { reference: "manager", name: formValue(form, "manager_name"), role: "farm_manager" },
        { reference: "field", name: formValue(form, "operator_name"), role: "field_operator" }
      ],
      parcels: [{
        reference: "first-parcel", name: formValue(form, "parcel_name"), area_hectares: area,
        right_type: formValue(form, "right_type"),
        right_starts_on: formValue(form, "right_starts_on"), right_ends_on: formValue(form, "right_ends_on")
      }],
      blocks: [{
        reference: "first-block", name: formValue(form, "block_name"), area_hectares: area,
        parcel_references: ["first-parcel"]
      }],
      season: {
        name: formValue(form, "season_name"),
        starts_on: formValue(form, "season_starts_on"), ends_on: formValue(form, "season_ends_on")
      },
      allocations: [{
        reference: "first-allocation", block_reference: "first-block", crop_name: formValue(form, "crop_name"),
        cultivar: formValue(form, "cultivar") || null, area_hectares: area
      }],
      location: location,
      first_work: {
        title: formValue(form, "first_work_title"), owner_reference: "field",
        allocation_reference: "first-allocation", due_at: workDueAt,
        required_evidence: [formValue(form, "required_evidence")]
      }
    };
  }

  function renderPreparedSetup(result) {
    var required = Array.isArray(result.required_before_acceptance) ? result.required_before_acceptance : [];
    element("setup-result").innerHTML = '<h3>Ready for a named manager to accept.</h3><p>' +
      escapeHtml(result.farm.name) + ' · ' + escapeHtml(result.location.district_name) + ' · ' +
      escapeHtml(result.allocations[0].crop_name) + '</p><ul>' + required.map(function (item) {
        return '<li>' + escapeHtml(item) + '</li>';
      }).join("") + '</ul><p>This screen only checked the pack. It did not create a farm, people, land, or work.</p>';
    element("setup-result").hidden = false;
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
      proposal = buildSetupProposal(form);
    } catch (error) {
      showSetupError(error.message || "Complete the first farm details.");
      return;
    }
    var submit = element("validate-setup");
    submit.disabled = true;
    submit.textContent = "Checking…";
    fetch(pilotValidationUrl, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(proposal)
    })
      .then(function (response) {
        return response.json().then(function (body) {
          if (!response.ok) {
            throw new Error(body.detail || "The farm pack could not be checked.");
          }
          return body;
        });
      })
      .then(renderPreparedSetup)
      .catch(function (error) {
        showSetupError(error.message || "The farm pack could not be checked.");
      })
      .finally(function () {
        submit.disabled = false;
        submit.innerHTML = 'Check this farm pack <span class="material-symbols-outlined" aria-hidden="true">arrow_forward</span>';
      });
  }

  function loadActionCentre() {
    element("load-status").textContent = "Loading…";
    element("portfolio-status").textContent = "Loading tools…";
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
  element("exception-list").addEventListener("click", function (event) {
    var button = event.target.closest("[data-exception-id]");
    if (button) {
      showView("fields");
      loadException(button.getAttribute("data-exception-id"));
    }
  });
  loadActionCentre();
}());
