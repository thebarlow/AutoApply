// browser-extension/popup/popup.js
const SERVER = "https://autoapply.matthewbarlow.me";
const TOKEN_KEY = "extToken";

async function getToken() {
  const { [TOKEN_KEY]: t } = await xb.storage.local.get(TOKEN_KEY);
  return t || "";
}

async function signIn(provider) {
  // Delegate to the service worker: opening the auth window closes this popup,
  // so any token-storing code awaited here would never run. The worker stores
  // the token; on success we re-render if the popup is still open, and if it
  // was closed the next open will already show the signed-in state.
  showError("Opening sign-in…");
  let res;
  try {
    res = await xb.runtime.sendMessage({ type: "SIGN_IN", provider });
  } catch (e) {
    return; // popup closed during the flow; worker finishes + stores the token
  }
  if (res && res.ok === false) {
    if (res.error === "no_account") {
      return showError("No AutoApply account. Sign up at autoapply.matthewbarlow.me first.");
    }
    return showError("Sign-in failed, try again.");
  }
  await render();
}

async function signOut() {
  const token = await getToken();
  if (token) {
    try {
      await fetch(`${SERVER}/auth/ext/revoke`, { method: "POST", headers: { Authorization: `Bearer ${token}` } });
    } catch (_) {}
  }
  await xb.storage.local.remove(TOKEN_KEY);
  await render();
}

function showError(msg) {
  document.getElementById("err").textContent = msg;
}

// Friendly first name derived from the email local part (no name field exists
// server-side); "matthew.barlow@x.com" -> "Matthew".
function displayName(email) {
  const local = (email || "").split("@")[0].split(/[._-]/)[0];
  return local ? local.charAt(0).toUpperCase() + local.slice(1) : "there";
}

async function render() {
  const token = await getToken();
  const inEl = document.getElementById("signedIn");
  const outEl = document.getElementById("signedOut");
  showError("");
  if (!token) {
    inEl.classList.add("hidden");
    outEl.classList.remove("hidden");
    return;
  }
  try {
    const res = await fetch(`${SERVER}/api/ext/me`, { headers: { Authorization: `Bearer ${token}` } });
    if (!res.ok) {
      if (res.status === 401) {
        await xb.storage.local.remove(TOKEN_KEY);
        inEl.classList.add("hidden");
        outEl.classList.remove("hidden");
      }
      return;
    }
    const { email } = await res.json();
    document.getElementById("greeting").textContent = `Hi ${displayName(email)}!`;
    document.getElementById("email").textContent = email;
    inEl.classList.remove("hidden");
    outEl.classList.add("hidden");
  } catch (_) {
    // Network error or other transient failure; keep token and stay signed in
  }
}

document.getElementById("loginGoogle").addEventListener("click", () => signIn("google"));
document.getElementById("loginGithub").addEventListener("click", () => signIn("github"));
document.getElementById("logout").addEventListener("click", signOut);
document.getElementById("clearDedup").addEventListener("click", async () => {
  await xb.storage.local.remove("stagedJobKeys");
  const msgEl = document.getElementById("msg");
  if (msgEl) {
    msgEl.textContent = "Scrape history cleared.";
  }
});
render();
