# Scraper Context

Collects job postings from LinkedIn and Indeed via a browser extension, then stages them as DB records (`state=scraped`) via `POST /api/scraper/stage-job`. Also pulls from Remotive and RemoteOK via `POST /api/scraper/run`.

## Extension Architecture

```
job-scraper-extension/
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

Firefox: `about:debugging` → This Firefox → Load Temporary Add-on → select `job-scraper-extension/manifest.json`

## Known Issues (open)

- **LinkedIn bookmark not firing** — the `bookmarkCard` function targets `button[aria-label*='Save job']` within the card, but LinkedIn's save button does not appear in the card DOM. Needs re-investigation to find the correct element and trigger.
- **LinkedIn saved jobs page (`/my-items/saved-jobs/`) has no buttons** — the card selector `.entity-result` does not match the current saved jobs DOM. Needs live DOM inspection to find the correct selector.

## API Sources (automated)

`POST /api/scraper/run` — triggers Remotive + RemoteOK scrape in a background thread. Sources configured via `scraper_sources` config key.

## Output

All scraped jobs written to SQLite DB with `state=scraped`. Schema matches `ScrapedJob` dataclass in `scraper/base.py`.
