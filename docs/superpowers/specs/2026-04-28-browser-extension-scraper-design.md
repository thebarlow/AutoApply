# Browser Extension Scraper Design Spec

**Sub-project 3 of 3 in the scraper module.** A browser extension that injects a Scrape button onto job cards on LinkedIn and Indeed, extracts full job data, and stages it to the SQLite DB via the FastAPI server. Replaces the existing `indeed-jobs-extension`.

---

## Goal

Allow the user to scrape individual job listings from LinkedIn and Indeed by clicking an injected button on each job card. Scraped jobs are POSTed to `POST /api/scraper/stage-job`, deduplicated by URL, and written to the DB in `scraped` state — consistent with API-sourced jobs from sub-project 1.

---

## Architecture

```
1_scraper/job-scraper-extension/
├── manifest.json               # MV3 — LinkedIn + Indeed host permissions
├── background/
│   └── service_worker.js       # Dedup (chrome.storage.local) + POST to FastAPI
├── content/
│   ├── injector.js             # Shared: MutationObserver, button injection, orchestration
│   ├── linkedin.js             # LinkedIn card selectors, getJobData, getDescription, bookmark
│   └── indeed.js               # Indeed card selectors, getJobData, getDescription, bookmark
└── popup/
    ├── popup.html
    └── popup.js                # FastAPI base URL config + clear dedup history
```

The old `indeed-jobs-extension/` directory is retired once this extension is verified working.

---

## Source Interface

Each source module calls `registerSource(config)` on load. `injector.js` consumes the config:

```js
registerSource({
  cardSelector,          // CSS selector matching job card elements
  getJobData(card),      // returns { job_key, title, company, location, url } from card DOM
  getDescription(),      // reads description text from the detail pane (already loaded)
  clickCard(card),       // programmatically clicks the card to load the detail pane
  bookmarkCard(card),    // clicks the platform bookmark button; null on saved-jobs pages
  detailReadySelector,   // CSS selector that signals the detail pane has populated
})
```

Each source module (`linkedin.js`, `indeed.js`) branches on `window.location` to select the correct selectors and set `bookmarkCard` to `null` on saved-jobs pages.

---

## Injector Orchestration (injector.js)

1. `MutationObserver` watches `document.body` for new cards matching `cardSelector`
2. For each new card: inject a "Scrape" button if one isn't already present
3. On button click:
   - Set button to "Scraping…" (disabled)
   - Check dedup via message to service worker — if already sent, set "✓ Already staged", stop
   - Call `clickCard(card)` to load the detail pane
   - Poll for `detailReadySelector` with 10s timeout
   - Call `getJobData(card)` + `getDescription()`
   - Send `SCRAPE_JOB` message to service worker with full payload
   - On success: call `bookmarkCard(card)` if not null; set button to "✓ Scraped"
   - On failure: set button to the appropriate error state (see Error Handling)

---

## Data Flow

```
User clicks Scrape button
  → injector.js: clickCard() → wait for detail pane → getJobData() + getDescription()
  → service_worker.js: dedup check → POST /api/scraper/stage-job
  → FastAPI: construct ScrapedJob → save_jobs() → SQLite DB (state=scraped)
  → service_worker.js: mark job_key as sent in chrome.storage.local
  → injector.js: bookmarkCard() → update button
```

---

## Job Payload

POSTed to `POST /api/scraper/stage-job`:

```json
{
  "source": "linkedin",
  "job_key": "linkedin_<platform_id>",
  "title": "...",
  "company": "...",
  "location": "...",
  "url": "...",
  "description": "...",
  "remote": true,
  "posted_at": "",
  "salary": "",
  "scraped_at": "<ISO timestamp>"
}
```

`remote` is derived client-side: `true` if location contains "remote" (case-insensitive), otherwise `false`. This matches the `ScrapedJob` dataclass from sub-project 1 exactly.

---

## FastAPI Endpoint

```
POST /api/scraper/stage-job
```

Registered in `web/routers/scraper.py` alongside the existing `/api/scraper/run` route.

Accepts the job payload, constructs a `ScrapedJob`, calls `save_jobs(db, [job])`. Returns:

```json
{ "status": "staged", "job_key": "linkedin_<id>" }
```

If the job already exists by URL, `save_jobs()` skips the insert and returns:

```json
{ "status": "duplicate", "job_key": "linkedin_<id>" }
```

Returns `400` if required fields (`title`, `url`, `source`) are missing.

---

## Deduplication

Two-layer dedup:

1. **Extension layer:** `chrome.storage.local` stores sent `job_key` values. Checked before any network call — gives instant "✓ Already staged" feedback without hitting the server.
2. **Server layer:** `save_jobs()` deduplicates by URL against the DB. Catches jobs the extension hasn't seen (e.g., scraped via API sources) and handles storage-cleared edge cases.

---

## Manifest

```json
{
  "manifest_version": 3,
  "permissions": ["storage", "tabs"],
  "host_permissions": [
    "https://*.linkedin.com/*",
    "https://*.indeed.com/*",
    "http://localhost/*"
  ],
  "background": { "service_worker": "background/service_worker.js" },
  "content_scripts": [
    {
      "matches": ["https://www.linkedin.com/jobs/*", "https://www.linkedin.com/my-items/*"],
      "js": ["content/injector.js", "content/linkedin.js"]
    },
    {
      "matches": ["https://www.indeed.com/jobs*", "https://myjobs.indeed.com/*"],
      "js": ["content/injector.js", "content/indeed.js"]
    }
  ],
  "action": { "default_popup": "popup/popup.html" }
}
```

---

## Popup

Config only — no live status display (feedback is inline on each button):

- **FastAPI base URL** input (default: `http://localhost:8000`) — stored in `chrome.storage.sync`
- **Clear history** button — wipes `chrome.storage.local` sent keys, with a count display

---

## Error Handling

| Scenario | Button state | POST made? |
|---|---|---|
| Detail pane doesn't load within 10s | "✗ Timeout" | No |
| FastAPI not running / POST fails | "✗ Server error" | Attempted, failed |
| Already staged (dedup hit in extension) | "✓ Already staged" | No |
| `getJobData` returns missing title or URL | "✗ Parse error" | No |
| Bookmark action fails | Log warning; button shows "✓ Scraped" | Yes |
| Server returns duplicate | Button shows "✓ Already staged" | Yes, server skipped insert |

---

## Testing

No automated tests — browser extension DOM scraping requires a full browser harness. Verification is manual:

1. Load unpacked extension from `1_scraper/job-scraper-extension/`
2. Navigate to LinkedIn job search — confirm Scrape button appears on cards
3. Click Scrape — confirm detail pane loads, button updates, DB record created
4. Click Scrape again on same job — confirm "✓ Already staged" without a second DB insert
5. Navigate to LinkedIn saved jobs — confirm Scrape button appears, bookmark not toggled
6. Repeat steps 2–5 for Indeed

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `1_scraper/job-scraper-extension/manifest.json` | Create | MV3 manifest |
| `1_scraper/job-scraper-extension/background/service_worker.js` | Create | Dedup + POST to FastAPI |
| `1_scraper/job-scraper-extension/content/injector.js` | Create | MutationObserver, button injection, orchestration |
| `1_scraper/job-scraper-extension/content/linkedin.js` | Create | LinkedIn selectors + bookmark logic |
| `1_scraper/job-scraper-extension/content/indeed.js` | Create | Indeed selectors + bookmark logic |
| `1_scraper/job-scraper-extension/popup/popup.html` | Create | Popup markup |
| `1_scraper/job-scraper-extension/popup/popup.js` | Create | Config UI |
| `web/routers/scraper.py` | Modify | Add `POST /api/scraper/stage-job` route |
| `1_scraper/indeed-jobs-extension/` | Retire | Delete after new extension verified |
