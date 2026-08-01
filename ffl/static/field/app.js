const PENDING_KEY = "ffl.pendingExceptions";
const API_URL = "/api/v1/exceptions";

const form = document.querySelector("#exception-form");
const syncButton = document.querySelector("#sync-now");
const syncStatus = document.querySelector("#sync-status");
const formStatus = document.querySelector("#form-status");
const locationStatus = document.querySelector("#location-status");
let location = null;
let syncing = false;

function pendingSubmissions() {
  try {
    const saved = JSON.parse(localStorage.getItem(PENDING_KEY) || "[]");
    return Array.isArray(saved) ? saved : [];
  } catch (_) {
    return [];
  }
}

function savePending(pending) {
  localStorage.setItem(PENDING_KEY, JSON.stringify(pending));
  updateSyncStatus();
}

function queueSubmission(payload) {
  const pending = JSON.parse(localStorage.getItem(PENDING_KEY) || "[]");
  pending.push({
    idempotency_key: payload.idempotency_key,
    payload,
    queued_at: new Date().toISOString(),
  });
  localStorage.setItem(PENDING_KEY, JSON.stringify(pending));
}

function updateSyncStatus(message) {
  const count = pendingSubmissions().length;
  syncStatus.textContent = message || (count ? `${count} report${count === 1 ? "" : "s"} pending sync.` : "All reports are synced.");
  syncButton.disabled = syncing || count === 0;
}

function removeSubmission(idempotencyKey) {
  const pending = pendingSubmissions();
  const index = pending.findIndex((entry) => entry.idempotency_key === idempotencyKey);
  if (index >= 0) {
    pending.splice(index, 1);
    savePending(pending);
  }
}

async function sendSubmission(entry) {
  const response = await fetch(API_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": entry.idempotency_key,
    },
    body: JSON.stringify(entry.payload),
  });
  if (!response.ok) {
    throw new Error(`Request failed (${response.status})`);
  }
}

async function syncPending() {
  if (syncing) return;
  const queued = pendingSubmissions();
  if (!queued.length) return updateSyncStatus();

  syncing = true;
  updateSyncStatus("Syncing saved reports…");
  for (const entry of queued) {
    try {
      await sendSubmission(entry);
      removeSubmission(entry.idempotency_key);
    } catch (_) {
      // Keep this entry (and every unsent entry) for a later retry.
    }
  }
  syncing = false;
  const remaining = pendingSubmissions().length;
  updateSyncStatus(remaining ? "Pending sync — retry when connected." : "All reports are synced.");
}

async function photoData(file) {
  if (!file) return null;
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve({ name: file.name, type: file.type, data: reader.result });
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

document.querySelector("#get-location").addEventListener("click", () => {
  if (!navigator.geolocation) {
    locationStatus.textContent = "Location is unavailable on this device.";
    return;
  }
  locationStatus.textContent = "Finding location…";
  navigator.geolocation.getCurrentPosition(
    (position) => {
      location = { latitude: position.coords.latitude, longitude: position.coords.longitude, accuracy: position.coords.accuracy };
      locationStatus.textContent = "Location added.";
    },
    () => { locationStatus.textContent = "Location not added. You can still save the report."; },
    { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 },
  );
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const submit = form.querySelector("button[type=submit]");
  submit.disabled = true;
  try {
    const file = document.querySelector("#photo").files[0];
    const payload = {
      idempotency_key: crypto.randomUUID(),
      details: document.querySelector("#details").value.trim(),
      severity: document.querySelector("#severity").value,
      photo: await photoData(file),
      location,
    };
    queueSubmission(payload);
    updateSyncStatus("Pending sync — saving report…");
    form.reset();
    location = null;
    locationStatus.textContent = "Not added";
    await syncPending();
    formStatus.textContent = pendingSubmissions().length ? "Report saved. Pending sync." : "Report sent successfully.";
  } catch (_) {
    formStatus.textContent = "Could not save the photo. Please try again.";
  } finally {
    submit.disabled = false;
  }
});

syncButton.addEventListener("click", syncPending);
window.addEventListener("online", syncPending);

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/static/field/sw.js"));
}

updateSyncStatus();
