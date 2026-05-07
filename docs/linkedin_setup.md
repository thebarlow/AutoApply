# LinkedIn Extension Setup

The AutoApply browser extension adds a **Scrape** button to LinkedIn job pages so you can save jobs directly to AutoApply with one click.

## Prerequisites

Your AutoApply server must be running before the extension can save jobs. Start it first:

```bash
bin/start.sh
```

The server runs on `http://localhost:8080`.

---

## Install in Chrome

1. Open Chrome and go to `chrome://extensions/`
2. Toggle **Developer mode** on (top-right corner)
3. Click **Load unpacked**
4. Navigate to and select the folder:
   ```
   C:\Users\barlo\projects\AutoApply\browser-extension
   ```
5. The **Job Scraper** extension appears in your extensions list

The extension persists across browser restarts. When you update the extension code, click the refresh icon on its card in `chrome://extensions/`.

---

## Configure the Server URL

The extension needs to know where your server is running.

1. Click the **Job Scraper icon** in the Chrome toolbar (puzzle piece menu if not pinned)
2. The popup shows a URL field defaulting to `http://localhost:8000`
3. Change it to `http://localhost:8080`
4. Click **Save**

You only need to do this once — the setting persists.

---

## Install in Firefox

1. Go to `about:debugging` in the address bar
2. Click **This Firefox** on the left
3. Click **Load Temporary Add-on...**
4. Navigate to `AutoApply/browser-extension/` and select `manifest.json`

> Firefox loads extensions temporarily — they are removed when the browser closes and must be reloaded each session.

---

## Pages the Extension Works On

| Page | URL pattern | What you see |
|---|---|---|
| Job search results | `linkedin.com/jobs/search/*` | **Scrape** button on each job card in the left panel |
| Single job listing | `linkedin.com/jobs/view/*` | **Scrape** button fixed in the top-right of the page |

The extension does not run on any other LinkedIn pages.

---

## What You Should See

**On a search results page:**

Each job card in the left panel gets a small blue **Scrape** button in its top-right corner. Clicking it triggers the scrape — the button updates to show the result:

| Button text | Meaning |
|---|---|
| Scraping… | In progress |
| ✓ Scraped | Saved to AutoApply |
| ✓ Already staged | Already in the database (skipped) |
| ✗ Parse error | Could not extract title or URL from the card |
| ✗ Server error | Could not reach the AutoApply server |
| ✗ Timeout | Job description did not load within 10 seconds |

**On a single job page:**

A blue **Scrape** button appears fixed in the top-right corner of the browser window once the job description has loaded.

---

## Troubleshooting

**✗ Server error** — Check that:
- `bin/start.sh` is running
- The popup URL is set to `http://localhost:8080`

**No Scrape button appears** — LinkedIn changes its page structure periodically and the extension's CSS selectors may be stale. Right-click a job card, click Inspect, and check whether the card element still uses `scaffold-layout__list-item`. If not, the selectors in `browser-extension/content/linkedin.js` need updating.

**Extension disappeared** — In Firefox, this is expected after closing the browser. In Chrome, check `chrome://extensions/` and reload if disabled.
