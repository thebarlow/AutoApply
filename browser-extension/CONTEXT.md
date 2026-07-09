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
6. On open, the popup calls `GET /api/ext/me` with the stored bearer token to verify session validity and display the signed-in email. A 401 response auto-clears the stored token.

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

## Known Issues (open)

### Live smoke test — PENDING maintainer execution
The full OAuth + scrape flow (sign-in on both Chrome and Firefox, LinkedIn and Indeed field verification, selector validity) **has not yet been verified by a human**. The items below reflect the pre-OAuth state of the selectors and are marked accordingly. Do not treat any selector as verified-working post-OAuth until the smoke test has been run and logged here.

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
