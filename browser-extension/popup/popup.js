// browser-extension/popup/popup.js
const SERVER = "https://autoapply.matthewbarlow.me";
const TOKEN_KEY = "extToken";

async function getToken() {
  const { [TOKEN_KEY]: t } = await xb.storage.local.get(TOKEN_KEY);
  return t || "";
}

async function signIn(provider) {
  const redirectUri = xb.identity.getRedirectURL();
  const url = `${SERVER}/auth/ext/login/${provider}?redirect_uri=${encodeURIComponent(redirectUri)}`;
  let resultUrl;
  try {
    resultUrl = await xb.identity.launchWebAuthFlow({ url, interactive: true });
  } catch (e) {
    return showError("Sign-in cancelled or failed.");
  }
  const frag = new URL(resultUrl).hash.slice(1);
  const params = new URLSearchParams(frag);
  if (params.get("error") === "no_account") {
    return showError("No AutoApply account. Sign up at autoapply.matthewbarlow.me first.");
  }
  const token = params.get("token");
  if (!token) return showError("Sign-in failed, try again.");
  await xb.storage.local.set({ [TOKEN_KEY]: token });
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
