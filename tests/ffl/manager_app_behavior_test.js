"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

class StubClassList {
  constructor() { this.values = new Set(); }
  add(value) { this.values.add(value); }
  remove(value) { this.values.delete(value); }
  toggle(value, enabled) {
    if (enabled === undefined ? !this.values.has(value) : enabled) {
      this.values.add(value);
      return true;
    }
    this.values.delete(value);
    return false;
  }
  contains(value) { return this.values.has(value); }
}

class StubElement {
  constructor(id) {
    this.id = id;
    this.textContent = "";
    this.innerHTML = "";
    this.hidden = false;
    this.open = false;
    this.value = "";
    this.disabled = false;
    this.attributes = {};
    this.listeners = {};
    this.classList = new StubClassList();
    this.elements = new Proxy({}, {
      get: (target, name) => {
        if (!target[name]) { target[name] = { value: "" }; }
        return target[name];
      }
    });
  }
  addEventListener(name, listener) { this.listeners[name] = listener; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name] || null; }
  showModal() { this.open = true; }
  close() { this.open = false; }
  focus() {}
  reset() {
    Object.keys(this.elements).forEach((name) => { this.elements[name].value = ""; });
  }
  reportValidity() { return true; }
  scrollIntoView() {}
}

const elements = new Map();
function getElement(id) {
  if (!elements.has(id)) { elements.set(id, new StubElement(id)); }
  return elements.get(id);
}

const document = {
  title: "",
  documentElement: { lang: "en" },
  getElementById: getElement,
  querySelectorAll: () => [],
  addEventListener: () => {}
};
const fetchCalls = [];
let heldFetch = null;
function successfulResponse(body) {
  return { ok: true, json: () => Promise.resolve(body) };
}
function holdNextFetch(predicate, onClaim) {
  const hold = { predicate, onClaim, claimed: false };
  hold.promise = new Promise((resolve, reject) => {
    hold.resolve = (body) => resolve(successfulResponse(body));
    hold.reject = reject;
  });
  heldFetch = hold;
  return hold;
}
function fetchStub(url, options) {
  const request = { url: String(url), options: options || {} };
  fetchCalls.push(request);
  if (heldFetch && !heldFetch.claimed && heldFetch.predicate(request)) {
    heldFetch.claimed = true;
    if (heldFetch.onClaim) { heldFetch.onClaim(request); }
    return heldFetch.promise;
  }
  return Promise.resolve(successfulResponse([]));
}
const window = {
  document,
  localStorage: { getItem: () => null, setItem: () => {} },
  location: { pathname: "/manager", search: "" },
  history: { replaceState: (_state, _title, path) => {
    window.location.search = path.includes("?") ? "?" + path.split("?")[1] : "";
  } },
  addEventListener: () => {},
  scrollTo: () => {},
  setTimeout: (callback) => callback(),
  setInterval: () => 0,
  clearInterval: () => {},
  L: null
};
window.window = window;

const appPath = path.resolve(__dirname, "../../ffl/static/manager/app.js");
let source = fs.readFileSync(appPath, "utf8");
const startup = [
  "  applyLanguage();",
  "  renderTodayClock();",
  "  window.setInterval(renderTodayClock, 60000);",
  "  loadManagerSessionStatus().then(loadActionCentre);"
].join("\n");
assert.ok(source.includes(startup), "manager app startup marker changed");
source = source.replace(startup, `  window.__managerTest = {
    setState: function (values) {
      if (Object.prototype.hasOwnProperty.call(values, "currentPortfolio")) { currentPortfolio = values.currentPortfolio; }
      if (Object.prototype.hasOwnProperty.call(values, "currentRuntime")) { currentRuntime = values.currentRuntime; }
      if (Object.prototype.hasOwnProperty.call(values, "currentFortuneMap")) { currentFortuneMap = values.currentFortuneMap; }
      if (Object.prototype.hasOwnProperty.call(values, "managerSessionAuthenticated")) { managerSessionAuthenticated = values.managerSessionAuthenticated; }
      if (Object.prototype.hasOwnProperty.call(values, "farmTruthReviewContexts")) { farmTruthReviewContexts = values.farmTruthReviewContexts; }
      if (Object.prototype.hasOwnProperty.call(values, "selectedFarmTruthContextKey")) { selectedFarmTruthContextKey = values.selectedFarmTruthContextKey; }
      if (Object.prototype.hasOwnProperty.call(values, "farmTruthCases")) { farmTruthCases = values.farmTruthCases; }
      if (Object.prototype.hasOwnProperty.call(values, "farmTruthInboxCases")) { farmTruthInboxCases = values.farmTruthInboxCases; }
      if (Object.prototype.hasOwnProperty.call(values, "currentFarmTruthCase")) { currentFarmTruthCase = values.currentFarmTruthCase; }
      if (Object.prototype.hasOwnProperty.call(values, "farmTruthOpenPending")) { farmTruthOpenPending = values.farmTruthOpenPending; }
      if (Object.prototype.hasOwnProperty.call(values, "interfaceLocale")) { interfaceLocale = values.interfaceLocale; }
    },
    state: function () {
      return {
        selectedFarmTruthContextKey: selectedFarmTruthContextKey,
        farmTruthCases: farmTruthCases,
        farmTruthInboxCases: farmTruthInboxCases,
        currentFarmTruthCase: currentFarmTruthCase,
        farmTruthOpenPending: farmTruthOpenPending,
        farmTruthContextGeneration: farmTruthContextGeneration,
        farmTruthInboxGeneration: farmTruthInboxGeneration,
        farmTruthReviewContexts: farmTruthReviewContexts,
        managerSessionAuthenticated: managerSessionAuthenticated
      };
    },
    farmTruthContexts: farmTruthContexts,
    openFarmTruthReview: openFarmTruthReview,
    consumeFarmTruthReviewRequest: consumeFarmTruthReviewRequest,
    closeManagerSessionDialog: closeManagerSessionDialog,
    renderPortfolio: renderPortfolio,
    renderFarmTruthDetail: renderFarmTruthDetail,
    renderFarmTruthUnavailable: renderFarmTruthUnavailable,
    refreshFarmTruthCases: refreshFarmTruthCases,
    loadFarmTruthReviewContexts: loadFarmTruthReviewContexts,
    loadFarmTruthInboxCases: loadFarmTruthInboxCases,
    loadFarmTruthCases: loadFarmTruthCases,
    loadFarmTruthCaseDetail: loadFarmTruthCaseDetail,
    submitFarmTruthDecision: submitFarmTruthDecision,
    farmTruthDecisionResponse: farmTruthDecisionResponse,
    showFarmTruthDecisionSuccess: showFarmTruthDecisionSuccess,
    toggleManagerSession: toggleManagerSession,
    renderBestMap: renderBestMap,
    renderFortuneMapUnavailable: renderFortuneMapUnavailable,
    translate: t
  };`);

const sandbox = {
  window,
  document,
  fetch: fetchStub,
  FormData: class { get() { return ""; } },
  URLSearchParams,
  Intl,
  Date,
  Math,
  Number,
  String,
  Boolean,
  Array,
  Object,
  JSON,
  Promise,
  isFinite,
  encodeURIComponent,
  console
};
vm.createContext(sandbox);
vm.runInContext(source, sandbox, { filename: appPath });
const api = window.__managerTest;

function portfolio(units, allocations) {
  return {
    scope: {
      availability: "available",
      active_farms: { count: units.length, items: units },
      active_allocations: { count: allocations.length, items: allocations }
    },
    risk_action_ledger: { items: [] }
  };
}

function reviewSurface() {
  return {
    generation: api.state().farmTruthContextGeneration,
    selectedContext: api.state().selectedFarmTruthContextKey,
    cases: Array.from(api.state().farmTruthCases),
    inboxCases: Array.from(api.state().farmTruthInboxCases),
    currentCase: api.state().currentFarmTruthCase,
    list: getElement("farm-truth-list").innerHTML,
    detail: getElement("farm-truth-detail").innerHTML,
    actionsHidden: getElement("farm-truth-decision-panel").hidden,
    feedback: getElement("farm-truth-feedback").textContent,
    feedbackHidden: getElement("farm-truth-feedback").hidden,
    refreshDisabled: getElement("farm-truth-refresh").disabled
  };
}

function farmTruthFetches() {
  return fetchCalls.filter((call) => call.url.includes("/api/v1/farm-truth/"));
}

function farmTruthPosts() {
  return farmTruthFetches().filter((call) => call.options.method === "POST");
}

async function flushPromises() {
  await new Promise((resolve) => setImmediate(resolve));
}

async function main() {
  const oldCase = {
    id: "case-old", status: "open",
    place: { village: "Old village", block: "Old block", district: "Old district" },
    area: {}, registration: {}, crop_timing: {},
    people: { farmer_display_name: "Old farmer", field_worker_display_names: [] },
    evidence: {
      reason_codes: ["registration", "recent_visits", "open_follow_ups"],
      task_label_codes: ["farmer_visit", "open_follow_up"],
      recent_visits: 2,
      open_follow_ups: 1
    }
  };
  const reviewContexts = [
    { operating_unit_id: "unit-old", operating_unit_name: "Old Unit", season_id: "season-old", season_name: "Rabi", starts_on: "2025-11-01", ends_on: "2026-04-30" },
    { operating_unit_id: "unit-new", operating_unit_name: "New Unit", season_id: "season-new", season_name: "Kharif", starts_on: "2026-06-01", ends_on: "2026-10-31" }
  ];

  api.setState({
    currentPortfolio: portfolio([], []),
    farmTruthReviewContexts: reviewContexts,
    managerSessionAuthenticated: true,
    selectedFarmTruthContextKey: ""
  });
  assert.deepEqual(
    Array.from(api.farmTruthContexts()).map((context) => context.key),
    ["unit-old\u001fseason-old", "unit-new\u001fseason-new"],
    "review contexts must not depend on active allocations"
  );

  window.location.search = "?review=farm-truth&field=field-1";
  assert.equal(api.consumeFarmTruthReviewRequest(), true, "review entry must be consumed once");
  assert.equal(window.location.search, "?field=field-1", "review entry must not leave a replaying URL flag");
  assert.equal(api.consumeFarmTruthReviewRequest(), false, "consumed review entry must not reopen the dialog");

  const staleContextFetch = holdNextFetch((request) => request.url.endsWith("/api/v1/farm-truth/contexts"));
  const staleContextRequest = api.loadFarmTruthReviewContexts();
  assert.equal(staleContextFetch.claimed, true, "context bootstrap must use the dedicated endpoint");
  await api.loadFarmTruthReviewContexts();
  staleContextFetch.resolve(reviewContexts);
  await staleContextRequest;
  assert.deepEqual(Array.from(api.state().farmTruthReviewContexts), [], "an older context response must not replace newer state");

  getElement("farm-truth-dialog").open = true;
  getElement("farm-truth-decision-panel").hidden = false;
  getElement("farm-truth-list").innerHTML = "stale card";
  api.setState({
    farmTruthReviewContexts: reviewContexts,
    selectedFarmTruthContextKey: "unit-old\u001fseason-old",
    farmTruthCases: [oldCase],
    currentFarmTruthCase: oldCase
  });
  const oldListFetch = holdNextFetch((request) => request.url.includes("status=open"));
  const oldListRequest = api.loadFarmTruthCases();
  assert.equal(oldListFetch.claimed, true, "old-context list request must be held");
  const selector = getElement("farm-truth-context");
  selector.value = "unit-new\u001fseason-new";
  selector.listeners.change({ currentTarget: selector });
  getElement("farm-truth-feedback").textContent = "new context feedback";
  getElement("farm-truth-feedback").hidden = false;
  oldListFetch.resolve([oldCase]);
  await oldListRequest;
  assert.equal(api.state().currentFarmTruthCase, null, "late list response must not select an old case");
  assert.deepEqual(Array.from(api.state().farmTruthCases), [], "late list response must not restore old cards");
  assert.equal(getElement("farm-truth-decision-panel").hidden, true, "late list response must not restore actions");
  assert.equal(getElement("farm-truth-list").innerHTML.includes("Old farmer"), false, "late list response must not render an old card");
  assert.equal(getElement("farm-truth-feedback").textContent, "new context feedback", "late list response must not clear new feedback");

  api.setState({ selectedFarmTruthContextKey: "unit-old\u001fseason-old", farmTruthCases: [oldCase], currentFarmTruthCase: null });
  getElement("farm-truth-dialog").open = true;
  const oldDetailFetch = holdNextFetch((request) => request.url.includes("/cases/case-old?"));
  const oldDetailRequest = api.loadFarmTruthCaseDetail("case-old");
  assert.equal(oldDetailFetch.claimed, true, "old-context detail request must be held");
  getElement("close-farm-truth").listeners.click();
  assert.equal(getElement("farm-truth-dialog").open, false, "dialog close must remove review intent");
  getElement("farm-truth-feedback").textContent = "replacement feedback";
  getElement("farm-truth-feedback").hidden = false;
  oldDetailFetch.resolve(oldCase);
  await oldDetailRequest;
  assert.equal(api.state().currentFarmTruthCase, null, "late detail response must not restore an old case");
  assert.deepEqual(Array.from(api.state().farmTruthCases), [], "dialog invalidation must retain an empty list");
  assert.equal(getElement("farm-truth-decision-panel").hidden, true, "late detail response must not restore actions");
  assert.equal(getElement("farm-truth-detail").innerHTML.includes("Old farmer"), false, "late detail response must not render old facts");
  assert.equal(getElement("farm-truth-feedback").textContent, "replacement feedback", "late detail response must not clear feedback");
  api.submitFarmTruthDecision({ preventDefault: () => {}, currentTarget: getElement("farm-truth-accept-form") }, "accept");
  assert.equal(fetchCalls.some((call) => call.options.method === "POST"), false, "stale async work must never enable a decision POST");

  getElement("farm-truth-dialog").open = true;
  api.setState({
    selectedFarmTruthContextKey: "unit-old\u001fseason-old",
    farmTruthCases: [],
    currentFarmTruthCase: null
  });
  const oldFailureFetch = holdNextFetch((request) => request.url.includes("status=open"));
  const oldFailureRequest = api.loadFarmTruthCases();
  selector.value = "unit-new\u001fseason-new";
  selector.listeners.change({ currentTarget: selector });
  getElement("farm-truth-feedback").textContent = "newer feedback";
  getElement("farm-truth-feedback").hidden = false;
  oldFailureFetch.reject(new Error("stale request failed"));
  await oldFailureRequest;
  assert.equal(getElement("farm-truth-feedback").textContent, "newer feedback", "late list failure must not show or clear feedback");

  api.setState({ managerSessionAuthenticated: true, farmTruthInboxCases: [] });
  const inboxFetch = holdNextFetch((request) => request.url.endsWith("/api/v1/farm-truth/inbox"));
  const inboxRequest = api.loadFarmTruthInboxCases();
  assert.equal(inboxFetch.claimed, true, "owner Inbox must use its dedicated endpoint");
  const inboxContextGeneration = api.state().farmTruthContextGeneration;
  api.renderFarmTruthUnavailable();
  assert.ok(api.state().farmTruthContextGeneration > inboxContextGeneration, "context changes must invalidate Inbox request origins");
  inboxFetch.resolve([{ id: "stale-inbox", status: "needs_evidence", reason_code: "confirm_plot_area" }]);
  await inboxRequest;
  assert.deepEqual(Array.from(api.state().farmTruthInboxCases), [], "late owner Inbox data must not restore stale rows");

  api.setState({
    managerSessionAuthenticated: false,
    farmTruthInboxCases: []
  });
  fetchCalls.length = 0;
  await api.loadFarmTruthInboxCases();
  assert.equal(farmTruthFetches().length, 0, "locked sessions must not request the owner Inbox");

  getElement("manager-session-dialog").open = true;
  api.setState({ farmTruthOpenPending: true });
  api.closeManagerSessionDialog();
  assert.equal(api.state().farmTruthOpenPending, false, "cancel must clear pending review intent");
  assert.equal(getElement("manager-session-dialog").open, false, "cancel must close unlock dialog");

  api.setState({ interfaceLocale: "en", farmTruthCases: [oldCase], currentFarmTruthCase: oldCase });
  api.showFarmTruthDecisionSuccess(true);
  const successText = getElement("farm-truth-feedback").textContent;
  api.renderFarmTruthDetail();
  assert.equal(getElement("farm-truth-feedback").hidden, false, "success feedback must remain visible");
  assert.equal(getElement("farm-truth-feedback").textContent, successText, "next-card render must retain success feedback");
  assert.ok(successText.includes(api.translate("reviewSaved")) && successText.includes(api.translate("reviewNext")));

  api.setState({ interfaceLocale: "hi" });
  api.renderFarmTruthDetail();
  assert.ok(getElement("farm-truth-detail").innerHTML.includes("पंजीकरण"), "stable evidence codes must localize in Hindi");
  assert.ok(getElement("farm-truth-detail").innerHTML.includes("किसान मुलाक़ात"), "stable task codes must localize in Hindi");
  api.renderFarmTruthUnavailable(new Error("Network request failed"));
  assert.ok(getElement("farm-truth-detail").innerHTML.includes(api.translate("farmTruthUnavailable")));
  assert.equal(getElement("farm-truth-detail").innerHTML.includes("Network request failed"), false, "raw English error must not render");
  await assert.rejects(
    api.farmTruthDecisionResponse({ ok: false, json: () => Promise.resolve({ detail: "Server English" }) }),
    (error) => error.message === api.translate("reviewFailed") && !error.message.includes("Server English")
  );

  api.setState({ currentFortuneMap: { type: "FeatureCollection", features: [] } });
  api.renderBestMap();
  assert.equal(getElement("home-map-status").textContent, api.translate("noReviewedGeometry"));
  assert.equal(getElement("home-map-status").textContent.includes("Dargava"), false, "sample location must not become map state");
  api.renderFortuneMapUnavailable();
  assert.equal(getElement("home-map-status").textContent, api.translate("noReviewedGeometry"));

  process.stdout.write("manager Farm Truth behavior harness passed\n");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
