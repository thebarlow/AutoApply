# Browser Extension Context

Collects job postings from LinkedIn and Indeed via a browser extension, then stages them as DB records (`state=scraped`) via `POST /api/scraper/stage-job`. API scrapers (Remotive, RemoteOK) are handled separately in `scraper/`.

## Architecture

```
browser-extension/
├── manifest.json               # MV3 (Firefox-compatible: background.scripts)
├── background/
│   └── service_worker.js       # Dedup (chrome.storage.local) + POST to FastAPI
├── content/
│   ├── injector.js             # MutationObserver, button injection, orchestration
│   ├── linkedin.js             # LinkedIn search + saved jobs selectors
│   └── indeed.js               # Indeed search + saved jobs selectors
└── popup/
    ├── popup.html
    └── popup.js                # FastAPI base URL config + clear dedup history
```

## How It Works

1. Extension injects a "Scrape" button on each job card (LinkedIn search, Indeed search, Indeed saved jobs)
2. On click: programmatically clicks the card to load the detail pane, waits for description to appear, extracts job data
3. POSTs to `POST /api/scraper/stage-job` → `save_jobs()` → SQLite DB (`state=scraped`)
4. Dedup: `chrome.storage.local` (extension-side by job_key) + `save_jobs()` (server-side by URL)
5. Button updates inline: "✓ Scraped", "✓ Already staged", "✗ Timeout", "✗ Server error", "✗ Parse error"

## Loading the Extension

Firefox: `about:debugging` → This Firefox → Load Temporary Add-on → select `browser-extension/manifest.json`

## Future Work

- **Auto-mark as applied on submission** — when the user clicks an Apply or Easy Apply button on LinkedIn/Indeed and the application is successfully submitted, the extension should detect the submission event and call `PATCH /api/jobs/{job_key}/state` with `state=applied`. This requires identifying the post-submission confirmation signal for each site (e.g., a DOM change, redirect, or confirmation modal). Tracked as a future goal in the dashboard design spec.

## Known Issues (open)

- **LinkedIn DOM is fully hashed** — LinkedIn replaced all CSS class names with hashed tokens (e.g. `d5efdad9`) that change on deploys. The search card selector now uses `[componentkey^="job-card-component-ref"]`, which is stable, but company/location extraction relies on positional `<p>` order and may drift. If company or location fields are wrong after a LinkedIn update, inspect the card DOM and recount `<p>` element order in `getJobData()`.
- **LinkedIn detail pane has no stable selectors** — all class names and IDs are hashed and rotate on deploys. Detection is text-based: `_findAboutHeader()` locates the "About the job" header and walks up to a container with >400 chars of text. If LinkedIn changes that header copy, update `_ABOUT_RE` in `linkedin.js`.
- **LinkedIn bookmark disabled** — `bookmarkCard` set to `null` after LinkedIn removed the save button from the card DOM. Needs live DOM inspection to find the new trigger.
- **LinkedIn saved jobs page (`/my-items/saved-jobs/`) has no buttons** — the card selector `.entity-result` does not match the current saved jobs DOM. Needs live DOM inspection to find the correct selector.
- **`employment_type` not collected** — neither Indeed nor LinkedIn scrapers extract employment type (Full-time, Contract, etc.). Add to `getJobData()` in both scrapers, add `employment_type` column to `Job` model, and include in the review queue card.
