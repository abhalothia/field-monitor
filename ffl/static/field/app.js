const CONTEXT_URL = "/api/v1/field-capture/context";
const SUBMISSION_URL = "/api/v1/field-capture/submissions";

const state = document.querySelector("#field-state");
const assignmentSheet = document.querySelector("#assignment-sheet");
const captureSheet = document.querySelector("#capture-sheet");
const fieldContainer = document.querySelector("#template-fields");
const evidenceField = document.querySelector("#evidence-field");
const form = document.querySelector("#capture-form");
const formStatus = document.querySelector("#form-status");
let accessToken = null;
let assignment = null;

function tokenFromFragment() {
  const parameters = new URLSearchParams(window.location.hash.slice(1));
  const token = parameters.get("capture");
  // A fragment never reaches the server. Remove it after reading so it is not
  // accidentally copied into browser history or a screen recording later.
  if (token) window.history.replaceState({}, document.title, window.location.pathname);
  return token;
}

function authorization() {
  return { "Authorization": `Bearer ${accessToken}` };
}

function setState(hindi, english) {
  state.innerHTML = "";
  state.append(document.createTextNode(hindi));
  const translation = document.createElement("span");
  translation.textContent = english;
  state.append(translation);
}

function labelFor(field) {
  const label = document.createElement("label");
  label.htmlFor = `value-${field.key}`;
  label.textContent = field.label_hi || field.key;
  const small = document.createElement("small");
  small.textContent = field.label_en || field.key;
  label.append(small);
  return label;
}

function renderField(field) {
  const wrapper = document.createElement("div");
  wrapper.className = "template-field";
  wrapper.append(labelFor(field));
  let input;
  if (field.type === "choice") {
    input = document.createElement("select");
    (field.options || []).forEach((option) => {
      const element = document.createElement("option");
      element.value = option;
      element.textContent = option;
      input.append(element);
    });
  } else {
    input = document.createElement(field.type === "text" ? "textarea" : "input");
    if (input.tagName === "TEXTAREA") input.rows = 3;
    input.placeholder = field.hint || "";
  }
  input.id = `value-${field.key}`;
  input.dataset.key = field.key;
  input.required = Boolean(field.required);
  wrapper.append(input);
  fieldContainer.append(wrapper);
}

function renderAssignment(context) {
  assignment = context.assignment;
  const allocation = assignment.allocation;
  document.querySelector("#assignment-title").textContent = allocation.block_name;
  document.querySelector("#assignment-crop").textContent = [allocation.crop_name, allocation.cultivar].filter(Boolean).join(" · ");
  document.querySelector("#assignment-copy-hi").textContent = assignment.request.copy_hi;
  document.querySelector("#assignment-copy-en").textContent = assignment.request.copy_en;
  document.querySelector("#assignment-due").textContent = `Due / समय: ${new Date(assignment.request.due_at).toLocaleString()}`;
  fieldContainer.replaceChildren();
  assignment.template.fields.forEach(renderField);
  evidenceField.hidden = !assignment.request.evidence_required;
  const photo = document.querySelector("#photo");
  photo.required = assignment.request.evidence_required;
  assignmentSheet.hidden = false;
  captureSheet.hidden = false;
  setState("असाइनमेंट तैयार है।", "Your assigned field note is ready.");
}

async function readContext() {
  const response = await fetch(CONTEXT_URL, { headers: authorization(), cache: "no-store" });
  if (!response.ok) throw new Error("field link is not available");
  return response.json();
}

function fileAsEvidence(file) {
  if (!file) return Promise.resolve(null);
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = String(reader.result || "");
      const separator = dataUrl.indexOf(",");
      if (separator < 0) return reject(new Error("photo could not be read"));
      resolve({ content_base64: dataUrl.slice(separator + 1), media_type: file.type, filename: file.name });
    };
    reader.onerror = () => reject(new Error("photo could not be read"));
    reader.readAsDataURL(file);
  });
}

function valuesFromForm() {
  const values = {};
  fieldContainer.querySelectorAll("[data-key]").forEach((input) => { values[input.dataset.key] = input.value.trim(); });
  return values;
}

function observedAt() {
  const value = document.querySelector("#observed-at").value;
  if (!value) return null;
  return new Date(value).toISOString();
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!form.reportValidity() || !accessToken) return;
  const submit = form.querySelector("button[type=submit]");
  submit.disabled = true;
  formStatus.textContent = "Sending for review…";
  try {
    const payload = {
      idempotency_key: crypto.randomUUID(),
      observed_at: observedAt(),
      values: valuesFromForm(),
      evidence: await fileAsEvidence(document.querySelector("#photo").files[0]),
    };
    const response = await fetch(SUBMISSION_URL, {
      method: "POST",
      headers: { ...authorization(), "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error("submission unavailable");
    form.reset();
    formStatus.textContent = "समीक्षा के लिए भेज दिया गया। / Sent for review.";
  } catch (_) {
    formStatus.textContent = "अभी भेजा नहीं जा सका। सुरक्षित फील्ड लिंक दोबारा खोलें। / Could not send. Reopen the secure field link.";
  } finally {
    submit.disabled = false;
  }
});

accessToken = tokenFromFragment();
if (!accessToken) {
  setState("सुरक्षित फील्ड लिंक चाहिए।", "A manager must share a secure field link before you can submit a note.");
} else {
  setState("असाइनमेंट खोल रहे हैं…", "Opening your assignment…");
  readContext().then(renderAssignment).catch(() => {
    setState("यह फील्ड लिंक उपलब्ध नहीं है।", "This field link is unavailable. Ask your manager for a new one.");
  });
}

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/field-service-worker.js"));
}
