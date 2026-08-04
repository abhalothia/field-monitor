(function () {
  "use strict";

  var phoneForm = document.getElementById("phone-form");
  var codeForm = document.getElementById("code-form");
  var phoneInput = document.getElementById("phone");
  var codeInput = document.getElementById("code");
  var message = document.getElementById("portal-message");
  var detail = document.getElementById("portal-detail");
  var title = document.getElementById("portal-title");
  var kicker = document.getElementById("portal-kicker");
  var codeDetail = document.getElementById("code-detail");
  var requestButton = document.getElementById("request-code");
  var verifyButton = document.getElementById("verify-code");
  var signedInState = document.getElementById("signed-in-state");
  var signedInCopy = document.getElementById("signed-in-copy");
  var phone = "";
  var enabled = false;

  function showMessage(text, ok) {
    message.textContent = text || "";
    message.className = "portal-message" + (ok ? " ok" : "");
  }

  function normalisePhone(value) {
    return value.trim().replace(/[\s()-]/g, "");
  }

  function setBusy(button, busy, text) {
    button.disabled = busy;
    if (text) button.textContent = text;
  }

  async function api(path, options) {
    var response = await fetch(path, Object.assign({
      headers: { "Content-Type": "application/json" }, credentials: "same-origin"
    }, options || {}));
    var payload = null;
    try { payload = await response.json(); } catch (error) { payload = {}; }
    if (!response.ok) throw new Error(payload.detail || "Please try again.");
    return payload;
  }

  async function load() {
    try {
      var bootstrap = await api("/api/v1/portal/bootstrap");
      kicker.textContent = bootstrap.portal.name;
      document.title = "AGRO CEO — " + bootstrap.portal.name;
      enabled = Boolean(bootstrap.phone_sign_in.enabled);
      if (!enabled) {
        title.textContent = "Phone sign-in is being connected.";
        detail.textContent = "This portal will open as soon as its verified phone service is ready.";
        phoneForm.hidden = true;
        return;
      }
      detail.textContent = bootstrap.phone_sign_in.delivery_channel === "whatsapp"
        ? "Your one-time code will arrive on WhatsApp."
        : "Your one-time code will arrive by SMS.";
      codeDetail.textContent = detail.textContent;
      var session = await api("/api/v1/portal/session");
      if (session.next_path === "/manager") {
        window.location.assign(session.next_path);
      } else {
        showOwnPortal(session);
      }
    } catch (error) {
      if (error.message !== "phone sign-in is required") {
        showMessage(error.message);
      }
    }
  }

  function showOwnPortal(session) {
    phoneForm.hidden = true;
    codeForm.hidden = true;
    signedInState.hidden = false;
    title.textContent = "You are signed in.";
    if (session.portal_role === "farmer") {
      signedInCopy.textContent = "Your farm and crop history will appear here once Fortune has linked your reviewed record.";
    } else {
      signedInCopy.textContent = "Your field work and visit history will appear here once Fortune has linked your reviewed record.";
    }
    showMessage("", true);
  }

  phoneForm.addEventListener("submit", async function (event) {
    event.preventDefault();
    if (!enabled) return;
    phone = normalisePhone(phoneInput.value);
    if (!/^\+[1-9][0-9]{7,14}$/.test(phone)) {
      showMessage("Use country code, for example +91 98765 43210.");
      phoneInput.focus();
      return;
    }
    setBusy(requestButton, true, "Sending…");
    showMessage("");
    try {
      await api("/api/v1/portal/auth/request-code", { method: "POST", body: JSON.stringify({ phone: phone }) });
      phoneForm.hidden = true;
      codeForm.hidden = false;
      title.textContent = "Enter your code.";
      codeInput.focus();
    } catch (error) {
      showMessage(error.message);
    } finally {
      setBusy(requestButton, false, "Send code");
    }
  });

  codeForm.addEventListener("submit", async function (event) {
    event.preventDefault();
    var code = codeInput.value.trim();
    if (!/^[0-9]{4,12}$/.test(code)) {
      showMessage("Enter the code from your phone.");
      return;
    }
    setBusy(verifyButton, true, "Checking…");
    showMessage("");
    try {
      var result = await api("/api/v1/portal/auth/verify-code", {
        method: "POST", body: JSON.stringify({ phone: phone, code: code })
      });
      showMessage("Signed in.", true);
      if (result.next_path === "/manager") {
        window.location.assign(result.next_path);
      } else {
        showOwnPortal({ portal_role: result.portal_role });
      }
    } catch (error) {
      showMessage(error.message);
    } finally {
      setBusy(verifyButton, false, "Continue");
    }
  });

  document.getElementById("use-other-number").addEventListener("click", function () {
    codeForm.hidden = true;
    phoneForm.hidden = false;
    codeInput.value = "";
    title.textContent = "Sign in with your phone.";
    showMessage("");
    phoneInput.focus();
  });

  document.getElementById("sign-out").addEventListener("click", async function () {
    try { await api("/api/v1/portal/auth/logout", { method: "POST" }); } catch (error) { /* best effort */ }
    window.location.reload();
  });

  load();
}());
