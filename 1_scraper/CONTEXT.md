# Scraper Context

Collects job postings from Indeed (browser extension) and remote job board APIs (n8n), then stages them as JSON files in `../jobs/pending/`.

## Extension Architecture

```
indeed-jobs-extension/
├── manifest.json           # MV3 manifest — permissions, content script routes
├── background/
│   └── service_worker.js   # Orchestration: scrape list → open tabs → collect descriptions → POST webhook
├── content/
│   ├── saved_jobs.js       # Injected on myjobs.indeed.com — responds to GET_JOBS, returns job card data
│   └── job_detail.js       # Injected on /viewjob* — waits for #jobDescriptionText, reports back via runtime.sendMessage
├── popup/
│   ├── popup.html
│   └── popup.js            # Triggers START_SCRAPE, displays live status from service worker
└── options/
    ├── options.html
    └── options.js          # Lets user configure webhook URL (stored in chrome.storage.sync)
```

## Message Flow

1. User clicks "Scrape" in popup → popup sends `START_SCRAPE` to service worker
2. Service worker sends `GET_JOBS` to `saved_jobs.js` → gets job card list
3. For each new job, service worker opens a hidden `/viewjob` tab
4. `job_detail.js` extracts `#jobDescriptionText`, sends `JOB_DESCRIPTION` back to service worker
5. Service worker POSTs full job payload to n8n webhook; marks job key as sent in `chrome.storage.local`

**Deduplication:** Sent job keys persisted in `chrome.storage.local` under `sentJobKeys`. Already-sent jobs are skipped.

## Key Configuration

- Default webhook URL: `http://localhost:5678/webhook/indeed-jobs` (overridable via Options page, stored in `chrome.storage.sync`)
- Tab open delay: 600–1400ms random jitter between job tabs
- Description timeout: 10s in `job_detail.js`, 20s in service worker
- `config.json`: search keywords, location, remote filter, enabled job board sources

## Loading the Extension

- Chrome: `chrome://extensions` → Enable Developer Mode → Load Unpacked → select `indeed-jobs-extension/`
- Firefox: `about:debugging` → This Firefox → Load Temporary Add-on → select `indeed-jobs-extension/manifest.json`

No build step — plain ES2020+ JS, no transpilation.

## Output

Job JSON files written to `../jobs/pending/` with schema:
```json
{
  "job_key": "2069747",
  "source": "remotive",
  "title": "...",
  "company": "...",
  "location": "...",
  "remote": true,
  "description": "...",
  "url": "...",
  "posted_at": "...",
  "scraped_at": "..."
}
```
