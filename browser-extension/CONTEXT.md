# Browser Extension Context

Collects job postings from LinkedIn and Indeed via a browser extension, then stages them as DB records (`state=scraped`) via `POST /api/scraper/stage-job`. API scrapers (Remotive, RemoteOK) are handled separately in `scraper/`.

## Architecture

```
browser-extension/
├── manifest.json               # MV3 (Firefox-compatible: background.scripts)
├── icons/                      # Extension icons (16, 32, 48, 128 px PNG)
├── background/
│   └── service_worker.js       # Dedup (chrome.storage.local) + POST to FastAPI
├── content/
│   ├── injector.js             # MutationObserver, button injection, orchestration; also handles /jobs/view/ single-job page
│   ├── linkedin.js             # LinkedIn search, saved jobs, and direct view-page selectors
│   └── indeed.js               # Indeed search (www.indeed.com) + saved jobs (myjobs.indeed.com) selectors
└── popup/
    ├── popup.html
    └── popup.js                # FastAPI base URL config + clear dedup history
```

## How It Works

### Cross-browser shim (`lib/browser_shim.js`)
Exposes a unified promise-based `xb` API over `chrome.*` (Chrome) or `browser.*` (Firefox). All extension code uses `xb.*` instead of `chrome.*` directly. Covers `xb.storage.local`, `xb.identity` (OAuth), and `xb.runtime.sendMessage`.

### Authentication — OAuth + bearer token
1. User opens the extension popup and clicks "Sign in with Google" or "Sign in with GitHub".
2. `popup.js` calls `xb.identity.launchWebAuthFlow()` pointing to `https://autoapply.matthewbarlow.me/auth/ext/login/{provider}?redirect_uri=<xb.identity.getRedirectURL()>`.
3. On success the server redirects back with `#token=<jwt>` in the fragment. The popup parses this and stores it under the `extToken` key in `xb.storage.local`.
4. If the OAuth account has no AutoApply record, the server returns `#error=no_account`; the popup shows "No AutoApply account. Sign up at autoapply.matthewbarlow.me first."
5. The popup also provides a "Sign out" button that POSTs to `/auth/ext/revoke` (bearer auth) then removes `extToken` from storage.
6. On open, the popup calls `GET /api/ext/me` with the stored bearer token to verify session validity, display the signed-in email, and check admin status (`is_admin`) to conditionally show the Live/Local server toggle. A 401 response auto-clears the stored token.

### Scrape flow
1. `injector.js` injects a "Scrape" button on each job card via `MutationObserver` (card-list pages) or a fixed-position button (LinkedIn `/jobs/view/` single-job pages).
2. On click: programmatically clicks the card, waits for the description pane to load (`detailReadySelector` / `isDetailReady()`), then calls the source module's `getJobData()` and `getDescription()`.
3. `injector.js` sends a `SCRAPE_JOB` message to `background/service_worker.js`.
4. The service worker reads `extToken` from `xb.storage.local`. If absent it returns `{ ok: false, error: "no_account" }` without hitting the network.
5. The service worker POSTs the payload to `https://autoapply.matthewbarlow.me/api/scraper/stage-job` with `Authorization: Bearer <extToken>`.
6. Button state after the round-trip: `✓ Scraped`, `✓ Already staged`, `✗ Sign in required`, `✗ Timeout`, `✗ Server error`, `✗ Parse error`.
   - **"✗ Sign in required"** is shown (with a tooltip) when the service worker has no token or the server returns 401. This applies to both the card-list scrape handler (`_handleScrape`) and the single-view scrape handler (`_handleViewScrape`).

### Dedup
Extension-side: `stagedJobKeys` array in `xb.storage.local` (checked via `CHECK_DEDUP` message before the network call). Server-side: `save_jobs()` deduplicates by URL. The popup "Clear scrape history" button removes `stagedJobKeys`.

### ATS detection (easy-apply flag + external URL resolution)
- **`getApplyInfo()`** (`linkedin.js`/`indeed.js`) inspects the job card/detail pane for
  an Easy Apply (LinkedIn) / Indeed Apply signal vs. an external "Apply on company site"
  link, returning `{easy_apply, apply_url_raw}`. `getJobData()` includes this in the
  scrape payload; `stage-job` persists it and the server sets `ats_type="easy_apply"`
  server-side for in-platform jobs (see `web/CONTEXT.md`).
- **`"tabs"` permission** was added to `manifest.json` so the background script can open
  a non-focused background tab to follow an external apply link's redirect chain.
- **Background ATS-resolution queue** (`service_worker.js`) — jobs staged with an
  `apply_url_raw` but no `ats_type` are enqueued for resolution. For each job the worker
  opens a background tab at `apply_url_raw`, watches `webNavigation`/tab-URL updates, and
  settles on the final URL after a **4s quiet period** (no further navigation) or a **20s
  hard cap**, whichever comes first; the tab is then closed. Concurrency is capped at
  **≤2** in-flight resolutions. On settle, the worker PATCHes
  `/api/scraper/jobs/{job_key}/ats-resolution` with the resolved URL so the server can
  classify it via `core/ats.py`. Jobs are enqueued only after a successful stage (never on
  a duplicate/failed stage).

**Known limitations:**
1. **No `href` → never enqueued.** If an external "Apply" control renders as a `<button>`
   with no underlying `href` (JS-driven navigation), `getApplyInfo()` can't produce an
   `apply_url_raw`, so that job is never queued for resolution and its chip stays
   "Resolving…" indefinitely. No current workaround; would need per-site click-simulation.
2. **MV3 service-worker idle termination can orphan a resolution.** Chrome may kill an
   idle/backgrounded MV3 service worker at any point, including mid-resolution (within the
   ≤20s window). If that happens the background tab is left open (never closed) and the
   PATCH is never sent — there is no retry/resume on worker restart. Same class of
   fragility as the selector breakage below; the "Browser-extension DOM recalibration
   tool" TODO item (`.claude/TODO.md`) is the tracked mitigation direction for this and
   the selector issues generally (a maintainer-run tool to re-derive selectors/behavior
   after a site DOM change, rather than hand-patching each break).

## Loading the Extension

### Chrome
1. Go to `chrome://extensions` → enable "Developer mode".
2. Click "Load unpacked" → select the `browser-extension/` directory.
3. Note the extension's redirect URL: open the background service worker console and run `chrome.identity.getRedirectURL()`. Add this URL (comma-separated with the Firefox value) to `EXTENSION_REDIRECT_URLS` in your local `.env` and in the Railway environment variables.

### Firefox
1. Go to `about:debugging` → "This Firefox" → "Load Temporary Add-on" → select `browser-extension/manifest.json`.
2. Note the extension's redirect URL: in the extension's background console run `browser.identity.getRedirectURL()`. Add this URL (comma-separated with the Chrome value) to `EXTENSION_REDIRECT_URLS`.

`EXTENSION_REDIRECT_URLS` is a comma-separated list of allowed redirect URLs that the server validates after OAuth. Both browser-specific values must be present or sign-in will fail with a redirect-mismatch error.

## Future Work

- **Auto-mark as applied on submission** — when the user clicks an Apply or Easy Apply button on LinkedIn/Indeed and the application is successfully submitted, the extension should detect the submission event and call `PATCH /api/jobs/{job_key}/state` with `state=applied`. This requires identifying the post-submission confirmation signal for each site (e.g., a DOM change, redirect, or confirmation modal). Tracked as a future goal in the dashboard design spec.
- **Store packaging (sub-project B, deferred)** — publishing to Chrome Web Store / Firefox Add-on store requires a stable pinned extension ID (assigned by the store). That ID determines the permanent `xb.identity.getRedirectURL()` value, which in turn must be added to `EXTENSION_REDIRECT_URLS` on the server. Do not package for stores until the redirect URL is captured from the pinned ID and allowlisted.
- **Pin a Chrome `key` in `manifest.json` to stabilize the redirect URL.** Chrome has no `key`, so load-unpacked derives the extension ID (and thus `chrome.identity.getRedirectURL()` → `https://<id>.chromiumapp.org/`) from the install path. Reinstalling or loading from a different folder/machine changes the ID, so its redirect URL silently drops off the `EXTENSION_REDIRECT_URLS` allowlist and `/auth/ext/login/{provider}` starts 400-ing ("redirect_uri not allowed" → "Sign-in failed" with no Google page). Add a fixed `"key"` (the base64 public key) to `manifest.json` so the dev ID — and its redirect URL — stays constant. Firefox is already stable via `browser_specific_settings.gecko.id`.

## Admin-only Live/Local Server Toggle

The popup now includes an optional toggle (admin users only) that routes job submissions to either the live server (`https://autoapply.matthewbarlow.me`) or a local development instance (`http://localhost:8080`). Toggling does not affect OAuth sign-in (identity is always verified against the live server).

**Storage key:** `serverMode` with values `"live"` (default) or `"local"`.

**Implementation:**
- **Popup:** `renderServerToggle()` reads the stored mode and wires the radio buttons. Non-admins never see the toggle; if a non-admin account has a stray `"local"` mode in storage, it is reset to `"live"` on render.
- **Service worker:** `getServer()` (Task 1) resolves the base URL from `serverMode` and uses it for `POST /api/scraper/stage-job` and `PATCH /api/scraper/jobs/{job_key}/ats-resolution`.
- **Local mode behavior:** When `serverMode="local"`, the service worker submits to `http://localhost:8080` without an `Authorization` header. This works because the local server (when run via `start.bat` without `APP_ENV=production`) does not gate `/api/*` endpoints on authentication.
- **Cross-mode dedup:** Switching between modes does not clear the dedup history. The "Clear scrape history" button in the popup (existing UX) resets `stagedJobKeys` in storage; re-scraping the same job across modes will show "✗ Already staged" unless this button is clicked.

## Known Issues (open)

### Live smoke test — PENDING maintainer execution (Task 2)
The full OAuth + scrape flow (sign-in on both Chrome and Firefox, LinkedIn and Indeed field verification, selector validity) **has not yet been verified by a human**. The items below reflect the pre-OAuth state of the selectors and are marked accordingly. Do not treat any selector as verified-working post-OAuth until the smoke test has been run and logged here.

**Also PENDING:** the ATS-detection flow added in this feature (`getApplyInfo()` easy-apply/apply-URL extraction and the background ATS-resolution queue described above) has only been exercised via unit tests — it has **not** been smoke-tested live in Chrome/Firefox. Verify during the next smoke-test pass: easy-apply detection on a real LinkedIn Easy Apply card, external-apply URL capture on both sites, the background tab opening/closing correctly, and the PATCH landing with the right `ats_type`.

**PENDING (Task 2 Step 6):** The admin-only Live/Local server toggle (popup radio buttons, serverMode storage, routing in the service worker) has not been smoke-tested. Verify:
  1. **Non-admin account:** open popup → no toggle shown; scrape a job → goes to Live (network panel shows live host + `Authorization` header); `serverMode` in storage is `"live"`.
  2. **Admin account, Live (default):** toggle visible, "Live" selected; scrape → live host with bearer header; unchanged from today.
  3. **Admin, switch to Local:** start local server (`start.bat`); flip to "Local"; scrape a job → service-worker network panel shows `POST http://localhost:8080/api/scraper/stage-job` with **no** `Authorization` header (HTTP 200); job appears in **local** DB.
  4. **Admin, Local, external job:** confirm the ATS-resolution `PATCH` also hits `localhost:8080` with no auth header; card's chip flips from "Resolving…" to the ATS name.
  5. **Flip back to Live:** scrape → requests carry bearer token and hit live app again.
  6. **Mode-switch dedup:** re-scraping the same job across modes shows "✗ Already staged"; "Clear scrape history" resets it.

Selectors to check during the smoke test:
- `indeed.js` — `getJobData()` field extraction, `getDescription()`, and `detailReadySelector` (Indeed changes its DOM regularly).
- `linkedin.js` — card selector (`[componentkey^="job-card-component-ref"]`), positional `<p>` extraction for company/location in `getJobData()`, `_findAboutHeader()` / `_ABOUT_RE` for description, and the saved-jobs card selector.

### Resolved
- **Chrome extension sign-in failed with no Google redirect (2026-07-09)** — `/auth/ext/login/google`
  returned `400 redirect_uri not allowed` because the server's `EXTENSION_REDIRECT_URLS` only held the
  Firefox redirect; this Chrome install's `https://bblnkpilhkoaaadanhdmnamiolegodjl.chromiumapp.org/`
  was never allowlisted. Fixed by adding it (comma-separated, alongside Firefox) to the Railway env var
  and redeploying; verified both browsers' redirect URIs now `307 → accounts.google.com`. The allowlist
  is multi-value by design — no need to choose one browser. Root fragility (unstable Chrome ID) tracked
  under Future Work → pin a Chrome `key`.
- **Indeed description was empty / stale on the current layout (2026-07-09)** — two root causes,
  both fixed in `indeed.js` and verified live via Claude-in-Chrome:
  1. **Wrong selector.** Indeed migrated the detail pane to a react-native container
     (`div.react-native-html-content.simple-job-description-html`) and dropped the legacy
     `#jobDescriptionText` id, so `getDescription()` returned `""` and readiness never fired.
     Now uses `_DESCRIPTION_SELECTORS` (`.simple-job-description-html` → legacy `#jobDescriptionText`).
  2. **Stale-pane race.** The detail pane persists across card clicks and is REPLACED (new node)
     when a different job loads, so the shared `_waitForReady` resolved immediately on the PRIOR
     job's pane and read the wrong/old description on any repeat scrape. Added `_markStale` /
     `_isDetailReady` (mirroring `linkedin.js`): ready only once a *different*, populated
     (`innerText > 100`) container has mounted. Confirmed Indeed replaces the node on switch, so
     node-identity works.
  3. **CSS leaking into the description.** Indeed embeds `<style>@layer htmlContent{…}</style>`
     blocks INSIDE the description container. When fully laid out they're `display:none` so
     `innerText` excludes them, but if read before the pane paints, `innerText` falls back to
     `textContent` and splices the raw CSS into the scraped description. `getDescription` now goes
     through `_extractDescription`: clone the container, remove `style`/`script`, return
     `textContent` — clean regardless of render timing. `_isDetailReady` also measures the stripped
     length so a transient CSS-only container isn't treated as ready. reloading the *extension* does not re-inject content scripts into
  already-open tabs — you must reload the Indeed **page** (or open a new one) to pick up new code.

### Open selector issues (pre-smoke-test state)
- **LinkedIn DOM is fully hashed** — LinkedIn replaced all CSS class names with hashed tokens (e.g. `d5efdad9`) that change on deploys. The search card selector now uses `[componentkey^="job-card-component-ref"]`, which is stable, but company/location extraction relies on positional `<p>` order and may drift. If company or location fields are wrong after a LinkedIn update, inspect the card DOM and recount `<p>` element order in `getJobData()`.
- **LinkedIn detail pane has no stable selectors** — all class names and IDs are hashed and rotate on deploys. Detection is text-based: `_findAboutHeader()` locates the "About the job" header and walks up to a container with >400 chars of text. If LinkedIn changes that header copy, update `_ABOUT_RE` in `linkedin.js`.
- **LinkedIn bookmark disabled** — `bookmarkCard` set to `null` after LinkedIn removed the save button from the card DOM. Needs live DOM inspection to find the new trigger.
- **LinkedIn saved jobs page (`/my-items/saved-jobs/`) has no buttons** — the card selector `.entity-result` does not match the current saved jobs DOM. Needs live DOM inspection to find the correct selector.
- **`employment_type` not collected** — neither Indeed nor LinkedIn scrapers extract employment type (Full-time, Contract, etc.). Add to `getJobData()` in both scrapers, add `employment_type` column to `Job` model, and include in the review queue card.
