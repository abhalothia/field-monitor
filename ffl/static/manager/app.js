(function () {
  "use strict";

  var runtimeUrl = "/api/v1/runtime";
  var portfolioUrl = "/api/v1/portfolio";
  var currentRuntime = null;
  var focusExceptionId = null;

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

  function renderPortfolioUnavailable() {
    element("portfolio-status").textContent = "Portfolio context is unavailable. Current action centre data is still usable.";
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
    element("portfolio-status").textContent = "Portfolio context updated with the action centre.";
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

  function renderFieldFocus(runtime) {
    var allocations = runtime.allocations || [];
    var exceptions = (runtime.exceptions || []).filter(isOpenException);
    var focus = exceptions[0] || null;
    var allocation = allocations[0] || null;
    var crop = allocation ? allocation.crop_name + (allocation.cultivar ? " · " + allocation.cultivar : "") : "Field ledger";

    element("focus-crop").textContent = crop;
    focusExceptionId = focus ? focus.id : null;
    if (focus) {
      element("focus-title").textContent = focus.title;
      element("focus-note").textContent = nextAction(focus) || "Review the field signal with its linked evidence.";
      element("focus-severity").textContent = focus.severity;
      element("focus-severity").className = "severity severity-" + safeSeverity(focus.severity);
      return;
    }
    element("focus-title").textContent = allocation ? "Keep the next pass close." : "The field is ready for its first allocation.";
    element("focus-note").textContent = allocation ? "No open exception is blocking this allocation right now." : "Add a crop allocation to begin the evidence ledger.";
    element("focus-severity").textContent = "Clear";
    element("focus-severity").className = "severity severity-low";
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
        "<dl class=\"facts\"><div><dt>Owner</dt><dd>" + escapeHtml(item.owner_id) + "</dd></div>" +
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
        "<dl class=\"facts\"><div><dt>Owner</dt><dd>" + escapeHtml(item.owner_id) + "</dd></div>" +
        "<div><dt>Fallback owner</dt><dd>" + escapeHtml(item.fallback_owner_id) + "</dd></div>" +
        "<div><dt>Observed</dt><dd>" + escapeHtml(formatTime(item.observed_at)) + "</dd></div>" +
        "<div><dt>Current state</dt><dd>" + state + "</dd></div>" +
        "<div><dt>Next action</dt><dd>" + escapeHtml(action) + "</dd></div></dl>" +
        "<button class=\"detail-button\" type=\"button\" data-exception-id=\"" + escapeHtml(item.id) + "\">View audit history</button>" +
        "</article>";
    }).join(""));
  }

  function renderRuntime(runtime) {
    currentRuntime = runtime;
    element("operating-unit").textContent = runtime.operating_unit ? runtime.operating_unit.name : "Current field operations";
    renderCards(runtime);
    renderFieldFocus(runtime);
    renderWork(runtime.work_items || []);
    renderExceptions(runtime.exceptions || []);
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

  function loadActionCentre() {
    element("load-status").textContent = "Loading action centre…";
    element("portfolio-status").textContent = "Loading portfolio context…";
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
      .catch(function (error) {
        element("load-status").textContent = error.message;
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

  element("refresh").addEventListener("click", loadActionCentre);
  element("review-focus").addEventListener("click", function () {
    if (focusExceptionId) {
      loadException(focusExceptionId);
      element("audit").scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    element("work-heading").scrollIntoView({ behavior: "smooth", block: "start" });
  });
  element("exception-list").addEventListener("click", function (event) {
    var button = event.target.closest("[data-exception-id]");
    if (button) {
      loadException(button.getAttribute("data-exception-id"));
    }
  });
  loadActionCentre();
}());
