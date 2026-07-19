# Extension Live/Local Server Toggle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an admin-only popup toggle that routes scraped-job submission to either the live app or a local dev server (`http://localhost:8080`), without changing identity/auth (always Live).

**Architecture:** A stored `serverMode` key (`"live"` | `"local"`, default `"live"`) drives where the service worker sends `stage-job` and the ATS-resolution `PATCH`. Identity (`SIGN_IN`, `/api/ext/me`) is always Live. In local mode the worker sends requests **without** an `Authorization` header (the local server resolves the active profile via its dev-stub path, since it does not gate `/api/*` unless `APP_ENV=production`). The popup shows the toggle only when `/api/ext/me` reports `is_admin`, and resets a stray `local` mode to `live` for non-admins.

**Tech Stack:** MV3 browser extension, vanilla JS (self-contained `service_worker.js` with an inline `_api`/`_p` shim; no `xb`/`browser_shim.js` in the worker). No backend changes.

## Global Constraints

- **No backend changes.** `/api/ext/me` already returns `is_admin` (`web/auth/routes.py:398`); rely on it.
- **Identity is always Live.** Only `stage-job` and `PATCH /api/scraper/jobs/{job_key}/ats-resolution` honor `serverMode`. `SIGN_IN` and `/api/ext/me` always use the live URL.
- **Local target is fixed:** `http://localhost:8080`. Live target: `https://autoapply.matthewbarlow.me`.
- **Fail-safe resolution:** any `serverMode` value other than exactly `"local"` resolves to Live.
- **Local mode omits the `Authorization` header** and must **not** short-circuit on a missing token; Live mode keeps the existing token requirement (`no_account` when absent) unchanged.
- **Admin-only toggle:** non-admins never see it; on a non-admin popup render, reset stored `serverMode` to `"live"`.
- **Dedup across modes** is handled by the existing "Clear scrape history" button — no new code.
- **Commit format:** `[type] Imperative subject` (`feat`/`fix`/`refactor`/`docs`/`test`/`chore`). No Claude attribution.
- **JS style:** match the surrounding file (2-space indent, double quotes, semicolons).

---

## File Structure

- **Modify** `browser-extension/background/service_worker.js` — add mode-aware server resolution; make `stage-job` and the ATS `PATCH` mode-aware (local = tokenless, no `no_account` block). Keep `SIGN_IN` on Live.
- **Modify** `browser-extension/popup/popup.html` — add the (hidden-by-default) toggle markup in the signed-in section.
- **Modify** `browser-extension/popup/popup.js` — read `is_admin` from `/api/ext/me`; show/hide + initialize the toggle; persist changes; reset `serverMode` to `"live"` for non-admins.
- **Modify** `browser-extension/CONTEXT.md` — document the toggle, `serverMode`, the identity-vs-routing split, and the local-mode tokenless behavior (final task step).

> **Testing note (spec deviation, intentional):** the spec lists a unit test for the mode→URL resolver. The extension has **no** JS test harness, and the worker is deliberately non-modular (it cannot be `import`ed cleanly in Node — see the file's top comment). Standing up a test runner for one 2-line fail-safe function is disproportionate (YAGNI). The resolver is kept inline and trivially correct, and verification is folded into the manual smoke test, consistent with the rest of the extension's testing posture.

---

## Task 1: Mode-aware server resolution in the service worker

**Files:**
- Modify: `browser-extension/background/service_worker.js`

**Interfaces:**
- Consumes: existing `storageGet`/`storageSet`, `TOKEN_KEY`, `postStageJob`, `handleScrape`, `enqueueResolution`, `_resolveOne`, `_patchResolution`.
- Produces: `resolveServerUrl(mode) -> string`; `getServer() -> Promise<{mode: "live"|"local", url: string}>`; `serverMode` storage key (`MODE_KEY`). `enqueueResolution(jobKey, applyUrl, baseUrl, mode)` and `_patchResolution(jobKey, finalUrl, baseUrl, mode)` gain `baseUrl`/`mode` params. `stage-job` and the ATS `PATCH` send no `Authorization` header in local mode.

> No automated tests (extension posture). Steps end in a manual smoke test, then a commit.

- [ ] **Step 1: Add mode constants + resolver** — in `service_worker.js`, replace the single `const SERVER = ...` line (line 34) with the live/local constants, a fail-safe resolver, and a mode reader. Keep a `LIVE_URL` alias so identity code stays on Live:

```javascript
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
```

(Delete the now-duplicated `const DEDUP_KEY`/`const TOKEN_KEY` lines that were at 35-36 — they are folded into the block above. Do not leave duplicate declarations.)

- [ ] **Step 2: Keep sign-in on Live** — in `handleSignIn` (line 71), change `${SERVER}` to `${LIVE_URL}`:

```javascript
  const url = `${LIVE_URL}/auth/ext/login/${provider}?redirect_uri=${encodeURIComponent(redirectUri)}`;
```

- [ ] **Step 3: Make `postStageJob` base-URL- and token-aware** — replace the function (lines 86-99) so it takes a base URL and a nullable token, adding the `Authorization` header only when a token is present:

```javascript
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
```

- [ ] **Step 4: Make `handleScrape` mode-aware** — in `handleScrape` (lines 101-134), resolve the server, only require a token in live mode, pass the base URL + (mode-appropriate) token into `postStageJob`, and forward the base URL + mode to resolution. Replace the token guard (lines 106-107), the `postStageJob` call (line 113), and the `enqueueResolution` call (line 130):

```javascript
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
```

- [ ] **Step 5: Thread base URL + mode through the resolution queue** — update `enqueueResolution` (line 147), `_resolveOne` (line 163), and `_patchResolution` (line 211) so the PATCH targets the same server and omits auth in local mode:

```javascript
function enqueueResolution(jobKey, applyUrl, baseUrl, mode) {
  _resQueue.push({ jobKey, applyUrl, baseUrl, mode });
  _pumpResolution();
}
```

```javascript
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
```

```javascript
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
```

- [ ] **Step 6: Syntax check**

Run: `node --check browser-extension/background/service_worker.js`
Expected: no output, exit 0.

Also confirm no stray `SERVER` references remain:
Run: `grep -n "\bSERVER\b" browser-extension/background/service_worker.js`
Expected: no matches (all replaced by `LIVE_URL` / resolved URLs).

- [ ] **Step 7: Commit**

```bash
git add browser-extension/background/service_worker.js
git commit -m "[feat] Route stage-job/ATS-resolution by serverMode (local = tokenless)"
```

---

## Task 2: Admin-only popup toggle

**Files:**
- Modify: `browser-extension/popup/popup.html`
- Modify: `browser-extension/popup/popup.js`

**Interfaces:**
- Consumes: `serverMode` / `MODE_KEY` semantics from Task 1 (stored value `"live"`/`"local"`); the `is_admin` field of `GET /api/ext/me`.
- Produces: a toggle in the signed-in UI, visible only to admins, that reads/writes `serverMode`; non-admin renders force `serverMode = "live"`.

> No automated tests (extension posture). Steps end in a manual smoke test, then a commit.

- [ ] **Step 1: Add the toggle markup** — in `popup/popup.html`, inside the `#signedIn` div, add a hidden toggle block after the greeting `<p id="greeting">` line and before the "Ready to look at jobs?" paragraph:

```html
    <div id="serverToggle" class="hidden" style="margin:6px 0; padding:6px 0; border-top:1px solid #eee;">
      <p style="margin:0 0 4px; font-size:12px; color:#555;">Send jobs to:</p>
      <label style="display:inline-flex; align-items:center; width:auto; margin-right:10px;">
        <input type="radio" name="serverMode" value="live" style="width:auto; margin:0 4px 0 0;" /> Live
      </label>
      <label style="display:inline-flex; align-items:center; width:auto;">
        <input type="radio" name="serverMode" value="local" style="width:auto; margin:0 4px 0 0;" /> Local (localhost:8080)
      </label>
    </div>
```

- [ ] **Step 2: Add a storage helper + mode constant** — in `popup/popup.js`, after the existing `TOKEN_KEY` constant (line 3), add:

```javascript
const MODE_KEY = "serverMode";

async function getServerMode() {
  const { [MODE_KEY]: mode } = await xb.storage.local.get(MODE_KEY);
  return mode === "local" ? "local" : "live";
}
```

- [ ] **Step 3: Render + wire the toggle by admin status** — in `popup.js`, update `render()` so the `/api/ext/me` response reads `is_admin` and drives the toggle. Replace the success block of `render()` (the part after `const { email } = await res.json();`, lines ~78-83) with:

```javascript
    const { email, is_admin: isAdmin } = await res.json();
    document.getElementById("greeting").textContent = `Hi ${displayName(email)}!`;
    document.getElementById("email").textContent = email;
    await renderServerToggle(!!isAdmin);
    inEl.classList.remove("hidden");
    outEl.classList.add("hidden");
```

Then add the helper function (near the other functions, e.g. after `render`):

```javascript
// Admin-only routing toggle. Non-admins never see it; any stray "local" mode
// left on a now-non-admin account is reset to "live".
async function renderServerToggle(isAdmin) {
  const wrap = document.getElementById("serverToggle");
  if (!isAdmin) {
    await xb.storage.local.set({ [MODE_KEY]: "live" });
    wrap.classList.add("hidden");
    return;
  }
  const mode = await getServerMode();
  for (const input of wrap.querySelectorAll('input[name="serverMode"]')) {
    input.checked = input.value === mode;
    input.onchange = async () => {
      if (input.checked) await xb.storage.local.set({ [MODE_KEY]: input.value });
    };
  }
  wrap.classList.remove("hidden");
}
```

- [ ] **Step 4: Hide the toggle when signed out** — in `render()`, in the no-token branch and the 401 branch (where `signedIn` is hidden and `signedOut` shown), also hide the toggle so it never lingers. In the `if (!token)` block (lines ~68-73) add before `return;`:

```javascript
    document.getElementById("serverToggle").classList.add("hidden");
```

And in the `res.status === 401` block (lines ~86-90) add the same line alongside hiding `signedIn`:

```javascript
        document.getElementById("serverToggle").classList.add("hidden");
```

- [ ] **Step 5: Syntax check**

Run: `node --check browser-extension/popup/popup.js`
Expected: no output, exit 0.

- [ ] **Step 6: Manual smoke test** (maintainer, in Chrome/Firefox — reload the extension first)

  1. **Non-admin account:** open popup → no toggle shown. Scrape a job → goes to Live (network panel shows the live host + `Authorization` header). Confirm `serverMode` in storage is `"live"`.
  2. **Admin account, Live (default):** toggle visible, "Live" selected. Scrape → live host, bearer header present. Unchanged from today.
  3. **Admin, switch to Local:** start the local server (`start.bat`). Flip to "Local". Scrape a job → service-worker network panel shows `POST http://localhost:8080/api/scraper/stage-job` with **no** `Authorization` header, HTTP 200, and the job appears in the **local** DB.
  4. **Admin, Local, external job:** confirm the ATS-resolution `PATCH` also hits `localhost:8080` with no auth header, and the card's chip flips from "Resolving…" to the ATS name.
  5. **Flip back to Live:** scrape → requests carry the bearer token and hit the live app again.
  6. **Mode-switch dedup:** re-scraping the same job across modes shows "✗ Already staged"; "Clear scrape history" resets it.

  Record results in `browser-extension/CONTEXT.md` (Step 7).

- [ ] **Step 7: Document + commit** — add a short section to `browser-extension/CONTEXT.md` covering: the `serverMode` storage key and admin-only toggle; the identity-always-Live vs. job-routing-toggleable split; local-mode tokenless behavior (relies on the local server not gating `/api/*` unless `APP_ENV=production`); and that cross-mode dedup is handled by "Clear scrape history". Then:

```bash
git add browser-extension/popup/popup.html browser-extension/popup/popup.js browser-extension/CONTEXT.md
git commit -m "[feat] Add admin-only Live/Local server toggle to extension popup"
```

---

## Final verification

- [ ] `node --check` passes for both `service_worker.js` and `popup.js`.
- [ ] `grep -n "\bSERVER\b" browser-extension/background/service_worker.js` returns nothing (no stale constant).
- [ ] Manual smoke test (Task 2 Step 6) completed and recorded in `browser-extension/CONTEXT.md`.
- [ ] Confirm no backend files were touched (`git diff --stat` shows only `browser-extension/**`).

---

## Self-Review Notes

- **Spec coverage:** stored `serverMode` + resolver (T1 S1); identity-always-Live (T1 S2, `LIVE_URL` for sign-in; popup `/me` on live `SERVER`); job routing toggleable (T1 S4/S5); local tokenless + no `no_account` block (T1 S3/S4, `_patchResolution` T1 S5); admin-only toggle (T2 S3); non-admin reset to Live (T2 S3 `renderServerToggle(false)`); fixed localhost:8080 (T1 S1); fail-safe unknown→Live (T1 S1 `resolveServerUrl`, `getServer`); dedup via existing button (no code); docs (T2 S7). All covered.
- **Deviation (documented above):** spec's "unit test for resolveServerUrl" is intentionally not automated — no extension JS test harness exists and the worker is non-modular; the function is trivially fail-safe and covered by the manual smoke test.
- **Type consistency:** `serverMode` values `"live"`/`"local"` and `MODE_KEY` identical across worker and popup; `getServer()`/`getServerMode()` both normalize unknown→`"live"`; `enqueueResolution`/`_resolveOne`/`_patchResolution` all carry `(baseUrl, mode)` consistently; `is_admin` (snake_case from the API) destructured as `isAdmin` in the popup.
```
