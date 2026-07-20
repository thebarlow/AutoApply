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
// Maps job_key -> {apply_url_raw, apply_url_resolved} for external (non easy-apply)
// staged jobs, so a content script landing on an ATS apply page can find which
// staged job it corresponds to (Task 11 form enumeration).
const STAGED_META_KEY = "stagedJobMeta";

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
  if (message.type === "FIND_STAGED_JOB") {
    try {
      sendResponse(await handleFindStagedJob(message.url));
    } catch (err) {
      sendResponse({ job_key: null });
    }
    return;
  }
  if (message.type === "ENUMERATE_FORM") {
    try {
      sendResponse(await handleEnumerateForm(message.job_key, message.enumerated_fields));
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
    // Track the raw apply URL so a later ATS-page content script can match this
    // job (see handleFindStagedJob). Resolved URL is filled in on PATCH settle.
    const { [STAGED_META_KEY]: meta = {} } = await storageGet(STAGED_META_KEY);
    meta[data.job_key] = { apply_url_raw: payload.apply_url_raw, apply_url_resolved: "" };
    await storageSet({ [STAGED_META_KEY]: meta });
  }

  return { ok: true, status: data.status };
}

// --- Application-plan enumeration (Task 11) -----------------------------
// Read-only: matches an ATS apply page to a staged job, then relays the
// content script's field enumeration to the server. No form writing here.

// Greenhouse and Lever are multi-tenant: many companies' postings share one
// hostname (e.g. job-boards.greenhouse.io/<company>/..., jobs.lever.co/<company>/...),
// so hostname alone can bind an enumerated form to the wrong staged job. We
// therefore match hostname first, then disambiguate on the first path segment
// (the company slug for these ATSs). ATS flows rewrite deeper path segments and
// query params after landing, so we intentionally compare only the leading
// segment, and refuse to guess when the result is ambiguous.
function _hostMatches(currentUrl, storedUrl) {
  if (!storedUrl) return false;
  try {
    return new URL(currentUrl).hostname === new URL(storedUrl).hostname;
  } catch (_) {
    return false;
  }
}

function _firstSegment(u) {
  try {
    return new URL(u).pathname.split("/").filter(Boolean)[0] || "";
  } catch (_) {
    return "";
  }
}

function _segMatches(currentUrl, storedUrl) {
  if (!_hostMatches(currentUrl, storedUrl)) return false;
  const cur = _firstSegment(currentUrl);
  const stored = _firstSegment(storedUrl);
  return !!cur && cur === stored;
}

async function handleFindStagedJob(url) {
  const { [STAGED_META_KEY]: meta = {} } = await storageGet(STAGED_META_KEY);
  const entries = Object.entries(meta);
  const _matches = (info, pred) =>
    pred(url, info.apply_url_resolved) || pred(url, info.apply_url_raw);

  // Prefer a unique company-slug (first path segment) match — the reliable
  // signal on shared ATS hostnames.
  const segHits = entries.filter(([, info]) => _matches(info, _segMatches));
  if (segHits.length === 1) return { job_key: segHits[0][0] };

  // Fall back to hostname match only when it is unambiguous (a single staged
  // job on this ATS vendor). More than one hostname match without a unique
  // slug match is ambiguous — refuse to guess rather than POST the wrong job.
  if (segHits.length === 0) {
    const hostHits = entries.filter(([, info]) => _matches(info, _hostMatches));
    if (hostHits.length === 1) return { job_key: hostHits[0][0] };
  }
  return { job_key: null };
}

async function handleEnumerateForm(jobKey, enumeratedFields) {
  const { mode, url } = await getServer();
  const { [TOKEN_KEY]: token } = await storageGet(TOKEN_KEY);
  if (mode === "live" && !token) return { ok: false, error: "no_account" };

  const headers = { "Content-Type": "application/json" };
  if (mode !== "local") headers.Authorization = `Bearer ${token}`;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  let res;
  try {
    res = await fetch(`${url}/api/scraper/jobs/${encodeURIComponent(jobKey)}/application-plan`, {
      method: "POST",
      headers,
      body: JSON.stringify({ enumerated_fields: enumeratedFields }),
      signal: controller.signal,
    });
  } catch (err) {
    return { ok: false, error: err.name === "AbortError" ? "timeout" : "network" };
  } finally {
    clearTimeout(timer);
  }

  if (res.status === 401) return { ok: false, error: "no_account" };
  if (!res.ok) return { ok: false, error: `HTTP ${res.status}` };

  // The POST response is the plan itself and doesn't carry completeness;
  // fetch it via GET for the soft-nudge decision. Best-effort — the nudge is
  // non-critical, so a failure here degrades to "no nudge" rather than an error.
  let applicationAnswersComplete = null;
  try {
    const getHeaders = {};
    if (mode !== "local") getHeaders.Authorization = `Bearer ${token}`;
    const completeRes = await fetch(
      `${url}/api/scraper/jobs/${encodeURIComponent(jobKey)}/application-plan`,
      { headers: getHeaders }
    );
    if (completeRes.ok) {
      const data = await completeRes.json();
      applicationAnswersComplete = data.application_answers_complete;
    }
  } catch (_) {
    // Swallow — soft nudge only.
  }

  return { ok: true, application_answers_complete: applicationAnswersComplete, server_url: url };
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

  const { [STAGED_META_KEY]: meta = {} } = await storageGet(STAGED_META_KEY);
  if (meta[jobKey]) {
    meta[jobKey].apply_url_resolved = finalUrl;
    await storageSet({ [STAGED_META_KEY]: meta });
  }
}
