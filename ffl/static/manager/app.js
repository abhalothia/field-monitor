(function () {
  "use strict";

  var runtimeUrl = "/api/v1/runtime";
  var currentRuntime = null;

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
    return actions[exceptionRecord.status] || "Review the record and assign the next action.";
  }

  function setHtml(id, markup) {
    element(id).innerHTML = markup;
  }

  function escapeHtml(value) {
    return text(value).replace(/[&<>'"]/g, function (character) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", "\"": "&quot;" }[character];
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
    setHtml("exception-summary", "<span>Needs triage or follow-through</span>");
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
      return "<article class=\"queue-item exception-item\">" +
        "<div class=\"item-title\"><h3>" + escapeHtml(item.title) + "</h3>" +
        "<span class=\"severity severity-" + escapeHtml(item.severity) + "\">" + escapeHtml(item.severity) + "</span></div>" +
        "<dl class=\"facts\"><div><dt>Owner</dt><dd>" + escapeHtml(item.owner_id) + "</dd></div>" +
        "<div><dt>Fallback owner</dt><dd>" + escapeHtml(item.fallback_owner_id) + "</dd></div>" +
        "<div><dt>Observed</dt><dd>" + escapeHtml(formatTime(item.observed_at)) + "</dd></div>" +
        "<div><dt>Current state</dt><dd>" + escapeHtml(item.status) + "</dd></div>" +
        "<div><dt>Next action</dt><dd>" + escapeHtml(nextAction(item)) + "</dd></div></dl>" +
        "<button class=\"detail-button\" type=\"button\" data-exception-id=\"" + escapeHtml(item.id) + "\">View audit history</button>" +
        "</article>";
    }).join(""));
  }

  function renderRuntime(runtime) {
    currentRuntime = runtime;
    element("operating-unit").textContent = runtime.operating_unit ? runtime.operating_unit.name : "Current field operations";
    renderCards(runtime);
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

  function loadRuntime() {
    element("load-status").textContent = "Loading action centre…";
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
  }

  element("refresh").addEventListener("click", loadRuntime);
  element("exception-list").addEventListener("click", function (event) {
    var button = event.target.closest("[data-exception-id]");
    if (button) {
      loadException(button.getAttribute("data-exception-id"));
    }
  });
  loadRuntime();
}());
