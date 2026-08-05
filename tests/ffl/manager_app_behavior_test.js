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
function fetchStub(url, options) {
  fetchCalls.push({ url: String(url), options: options || {} });
  return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
}
const window = {
  document,
  localStorage: { getItem: () => null, setItem: () => {} },
  location: { pathname: "/manager", search: "" },
  history: { replaceState: () => {} },
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
      if (Object.prototype.hasOwnProperty.call(values, "selectedFarmTruthContextKey")) { selectedFarmTruthContextKey = values.selectedFarmTruthContextKey; }
      if (Object.prototype.hasOwnProperty.call(values, "farmTruthCases")) { farmTruthCases = values.farmTruthCases; }
      if (Object.prototype.hasOwnProperty.call(values, "currentFarmTruthCase")) { currentFarmTruthCase = values.currentFarmTruthCase; }
      if (Object.prototype.hasOwnProperty.call(values, "farmTruthOpenPending")) { farmTruthOpenPending = values.farmTruthOpenPending; }
      if (Object.prototype.hasOwnProperty.call(values, "sampleMode")) { sampleMode = values.sampleMode; }
      if (Object.prototype.hasOwnProperty.call(values, "interfaceLocale")) { interfaceLocale = values.interfaceLocale; }
    },
    state: function () {
      return {
        selectedFarmTruthContextKey: selectedFarmTruthContextKey,
        farmTruthCases: farmTruthCases,
        currentFarmTruthCase: currentFarmTruthCase,
        farmTruthOpenPending: farmTruthOpenPending
      };
    },
    farmTruthContexts: farmTruthContexts,
    openFarmTruthReview: openFarmTruthReview,
    closeManagerSessionDialog: closeManagerSessionDialog,
    renderPortfolio: renderPortfolio,
    renderFarmTruthDetail: renderFarmTruthDetail,
    renderFarmTruthUnavailable: renderFarmTruthUnavailable,
    submitFarmTruthDecision: submitFarmTruthDecision,
    farmTruthDecisionResponse: farmTruthDecisionResponse,
    showFarmTruthDecisionSuccess: showFarmTruthDecisionSuccess,
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

async function main() {
  const incomplete = portfolio(
    [{ id: "unit-a", name: "Unit A", active_allocation_count: 1 }],
    [
      { id: "allocation-a", operating_unit_id: "unit-a", season_id: "season-a", crop_name: "Paddy", status: "active" },
      { id: "allocation-b", operating_unit_id: "unit-b", season_id: "season-b", crop_name: "Wheat", status: "active" }
    ]
  );
  api.setState({ currentPortfolio: incomplete, managerSessionAuthenticated: true, selectedFarmTruthContextKey: "" });
  assert.deepEqual(Array.from(api.farmTruthContexts()), [], "one unmappable allocation must invalidate every context");
  fetchCalls.length = 0;
  api.openFarmTruthReview();
  await Promise.resolve();
  assert.equal(api.state().selectedFarmTruthContextKey, "", "invalid scope must not select a context");
  assert.equal(fetchCalls.some((call) => call.options.method === "POST"), false, "invalid scope must not refresh");

  const oldCase = {
    id: "case-old", status: "open",
    place: { village: "Old village", block: "Old block", district: "Old district" },
    area: {}, registration: {}, crop_timing: {},
    people: { farmer_display_name: "Old farmer", field_worker_display_names: [] },
    evidence: { reason_chips: [], safe_task_labels: [] }
  };
  const newPortfolio = portfolio(
    [{ id: "unit-new", name: "New Unit", active_allocation_count: 1 }],
    [{ id: "allocation-new", operating_unit_id: "unit-new", season_id: "season-new", crop_name: "Paddy", status: "active" }]
  );
  getElement("farm-truth-dialog").open = true;
  getElement("farm-truth-decision-panel").hidden = false;
  getElement("farm-truth-list").innerHTML = "stale card";
  api.setState({
    currentPortfolio: portfolio(
      [{ id: "unit-old", name: "Old Unit", active_allocation_count: 1 }],
      [{ id: "allocation-old", operating_unit_id: "unit-old", season_id: "season-old", crop_name: "Wheat", status: "active" }]
    ),
    selectedFarmTruthContextKey: "unit-old\u001fseason-old",
    farmTruthCases: [oldCase],
    currentFarmTruthCase: oldCase
  });
  fetchCalls.length = 0;
  api.renderPortfolio(newPortfolio);
  await Promise.resolve();
  assert.equal(api.state().currentFarmTruthCase, null, "context replacement must clear current case");
  assert.deepEqual(Array.from(api.state().farmTruthCases), [], "context replacement must clear case list");
  assert.equal(getElement("farm-truth-decision-panel").hidden, true, "context replacement must hide decisions");
  assert.equal(getElement("farm-truth-list").innerHTML.includes("stale card"), false, "stale card must be removed");
  assert.equal(fetchCalls.some((call) => call.options.method === "POST"), false, "portfolio changes must never refresh");
  api.submitFarmTruthDecision({ preventDefault: () => {}, currentTarget: getElement("farm-truth-accept-form") }, "accept");
  assert.equal(fetchCalls.some((call) => call.options.method === "POST"), false, "cleared stale case must not submit");

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
  api.renderFarmTruthUnavailable(new Error("Network request failed"));
  assert.ok(getElement("farm-truth-detail").innerHTML.includes(api.translate("farmTruthUnavailable")));
  assert.equal(getElement("farm-truth-detail").innerHTML.includes("Network request failed"), false, "raw English error must not render");
  await assert.rejects(
    api.farmTruthDecisionResponse({ ok: false, json: () => Promise.resolve({ detail: "Server English" }) }),
    (error) => error.message === api.translate("reviewFailed") && !error.message.includes("Server English")
  );

  api.setState({ sampleMode: true, currentFortuneMap: { type: "FeatureCollection", features: [] } });
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
