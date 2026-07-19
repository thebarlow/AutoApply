// browser-extension/background/service_worker.js
// Self-contained: does NOT load the external browser_shim.js. Firefox MV3 and
// Chrome MV3 disagree on whether the background is a service worker (importScripts
// available) or an event page (it is not), and on whether the manifest `scripts`
// array is honored — relying on either to inject the shim proved unreliable. The
// few APIs the background needs are wrapped inline instead, so the worker has zero
// external-load dependency and registers its message listener no matter how the
// background context is created.
const _api = typeof browser !== "undefined" ? browser : chrome;
const _isFirefox = typeof browser !== "undefined";

// Promisify a callback-style chrome.* API; pass Firefox's native promise through.
function _p(fn, ctx) {
  return (...args) =>
    _isFirefox
      ? fn.apply(ctx, args)
      : new Promise((resolve, reject) =>
          fn.call(ctx, ...args, (res) =>
            chrome.runtime.lastError
              ? reject(new Error(chrome.runtime.lastError.message))
              : resolve(res)
          )
        );
}

const storageGet = _p(_api.storage.local.get, _api.storage.local);
const storageSet = _p(_api.storage.local.set, _api.storage.local);
const launchWebAuthFlow = _p(_api.identity.launchWebAuthFlow, _api.identity);
const getRedirectURL = (...a) => _api.identity.getRedirectURL(...a);
const tabsCreate = _p(_api.tabs.create, _api.tabs);
const tabsRemove = _p(_api.tabs.remove, _api.tabs);
const tabsGet = _p(_api.tabs.get, _api.tabs);

const LIVE_URL = "https://autoapply.matthewbarlow.me";
const LOCAL_URL = "http://localhost:8080";
const MODE_KEY = "serverMode";
const DEDUP_KEY = "stagedJobKeys";
const TOKEN_KEY = "extToken";

// Any value other than exactly "local" resolves to Live (fail-safe: never
// accidentally target localhost from an unexpected stored value).
function resolveServerUrl(mode) {
  return mode === "local" ? LOCAL_URL : LIVE_URL;
}

// Read the stored routing mode. Only stage-job / ATS-resolution honor this;
// identity (sign-in, /api/ext/me) is always Live.
async function getServer() {
  const { [MODE_KEY]: mode } = await storageGet(MODE_KEY);
  const m = mode === "local" ? "local" : "live";
  return { mode: m, url: resolveServerUrl(m) };
}

_api.runtime.onMessage.addListener((message, sender, sendResponse) => {
  handleMessage(message, sender, sendResponse);
  return true;
});

async function handleMessage(message, sender, sendResponse) {
  if (message.type === "CHECK_DEDUP") {
    const { [DEDUP_KEY]: keys = [] } = await storageGet(DEDUP_KEY);
    sendResponse({ isDuplicate: keys.includes(message.job_key) });
    return;
  }
  if (message.type === "SCRAPE_JOB") {
    try {
      sendResponse(await handleScrape(message.payload));
    } catch (err) {
      sendResponse({ ok: false, error: err.message });
    }
    return;
  }
  if (message.type === "SIGN_IN") {
    // Runs here, not in the popup: opening the auth window closes the popup and
    // would kill an in-flight await, so the token would never get stored.
    try {
      sendResponse(await handleSignIn(message.provider));
    } catch (err) {
      sendResponse({ ok: false, error: "auth" });
    }
    return;
  }
}

async function handleSignIn(provider) {
  const redirectUri = getRedirectURL();
  const url = `${LIVE_URL}/auth/ext/login/${provider}?redirect_uri=${encodeURIComponent(redirectUri)}`;
  const resultUrl = await launchWebAuthFlow({ url, interactive: true });
  const params = new URLSearchParams(new URL(resultUrl).hash.slice(1));
  if (params.get("error") === "no_account") return { ok: false, error: "no_account" };
  const token = params.get("token");
  if (!token) return { ok: false, error: "auth" };
  await storageSet({ [TOKEN_KEY]: token });
  return { ok: true };
}

const REQUEST_TIMEOUT_MS = 10000;
const MAX_ATTEMPTS = 2;

async function postStageJob(baseUrl, token, payload) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  const headers = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  try {
    return await fetch(`${baseUrl}/api/scraper/stage-job`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timer);
  }
}

async function handleScrape(payload) {
  const { [DEDUP_KEY]: keys = [] } = await storageGet(DEDUP_KEY);
  const keySet = new Set(keys);
  if (keySet.has(payload.job_key)) return { ok: true, status: "duplicate" };

  const { mode, url } = await getServer();
  const { [TOKEN_KEY]: token } = await storageGet(TOKEN_KEY);
  if (mode === "live" && !token) return { ok: false, error: "no_account" };

  let res;
  let lastErr;
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    try {
      res = await postStageJob(url, mode === "local" ? null : token, payload);
      break; // got an HTTP response (even an error status) — don't retry those
    } catch (err) {
      // Timeout (AbortError) or network failure — retry once, then give up.
      lastErr = err;
    }
  }
  if (!res) throw new Error(lastErr && lastErr.name === "AbortError" ? "timeout" : "network");

  if (res.status === 401) return { ok: false, error: "no_account" };
  if (!res.ok) throw new Error(`HTTP ${res.status}`);

  const data = await res.json();
  keySet.add(payload.job_key);
  await storageSet({ [DEDUP_KEY]: [...keySet] });

  if (data.status === "staged" && payload.easy_apply === false && payload.apply_url_raw) {
    enqueueResolution(data.job_key, payload.apply_url_raw, url, mode);
  }

  return { ok: true, status: data.status };
}

// --- ATS resolution queue -----------------------------------------------
// External (non easy-apply) jobs only give us the raw apply URL at scrape
// time; the real ATS often lives behind a redirect chain. Resolve it in a
// background tab (bounded concurrency, so a batch scrape doesn't spawn a
// pile of tabs) and PATCH the final URL back once navigation settles.
const _resQueue = [];
let _resActive = 0;
const RES_MAX_CONCURRENT = 2;
const RES_SETTLE_MS = 4000; // quiet period after last navigation
const RES_TIMEOUT_MS = 20000; // hard cap per resolution

function enqueueResolution(jobKey, applyUrl, baseUrl, mode) {
  _resQueue.push({ jobKey, applyUrl, baseUrl, mode });
  _pumpResolution();
}

function _pumpResolution() {
  while (_resActive < RES_MAX_CONCURRENT && _resQueue.length) {
    const task = _resQueue.shift();
    _resActive++;
    _resolveOne(task).finally(() => {
      _resActive--;
      _pumpResolution();
    });
  }
}

async function _resolveOne({ jobKey, applyUrl, baseUrl, mode }) {
  let tabId = null;
  try {
    const tab = await tabsCreate({ url: applyUrl, active: false });
    tabId = tab.id;
    const finalUrl = await _awaitSettled(tabId);
    await _patchResolution(jobKey, finalUrl, baseUrl, mode);
  } catch (e) {
    console.warn("[ats] resolution failed for", jobKey, e);
  } finally {
    if (tabId != null) {
      try {
        await tabsRemove(tabId);
      } catch (_) {}
    }
  }
}

// Resolve to the tab's URL once navigation has been quiet for RES_SETTLE_MS,
// or when RES_TIMEOUT_MS elapses — whichever comes first.
function _awaitSettled(tabId) {
  return new Promise((resolve) => {
    let lastUrl = "";
    let settleTimer = null;
    const hardTimer = setTimeout(finish, RES_TIMEOUT_MS);

    function onUpdated(id, info, tab) {
      if (id !== tabId) return;
      if (tab && tab.url) lastUrl = tab.url;
      if (settleTimer) clearTimeout(settleTimer);
      settleTimer = setTimeout(finish, RES_SETTLE_MS);
    }
    async function finish() {
      _api.tabs.onUpdated.removeListener(onUpdated);
      clearTimeout(hardTimer);
      if (settleTimer) clearTimeout(settleTimer);
      if (!lastUrl) {
        try {
          const t = await tabsGet(tabId);
          lastUrl = t.url || "";
        } catch (_) {}
      }
      resolve(lastUrl);
    }
    _api.tabs.onUpdated.addListener(onUpdated);
  });
}

async function _patchResolution(jobKey, finalUrl, baseUrl, mode) {
  const headers = { "Content-Type": "application/json" };
  if (mode === "live") {
    const { [TOKEN_KEY]: token } = await storageGet(TOKEN_KEY);
    if (!token) return;
    headers.Authorization = `Bearer ${token}`;
  }
  await fetch(`${baseUrl}/api/scraper/jobs/${encodeURIComponent(jobKey)}/ats-resolution`, {
    method: "PATCH",
    headers,
    body: JSON.stringify({ apply_url_resolved: finalUrl }),
  });
}
