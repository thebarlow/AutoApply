# Browser Extension Installation

## Prerequisites

AutoApply's server must be running before using the extension. Start it first, then load the extension in your browser.

## Chrome (recommended)

1. Go to `chrome://extensions/` in the address bar
2. Toggle **Developer mode** on (top right)
3. Click **Load unpacked**
4. Navigate to `AutoApply/browser-extension/` and select the folder
5. Done — the extension persists across browser restarts

To pick up code changes: click the refresh icon on the extension card in `chrome://extensions/`.

## Firefox

1. Go to `about:debugging` in the address bar
2. Click **This Firefox** on the left
3. Click **Load Temporary Add-on...**
4. Navigate to `AutoApply/browser-extension/` and select `manifest.json`

Note: Firefox loads it as a temporary add-on — it is removed when the browser closes and must be reloaded each session.

## Configuration

Click the extension icon in the toolbar and confirm the base URL matches your running server — typically `http://localhost:8000` or `http://localhost:8080`.

## Usage on LinkedIn

**From search results** (`linkedin.com/jobs/search/`)
1. Run a job search on LinkedIn
2. A **Scrape** button appears on each job card in the left panel
3. Click it — the extension clicks through to load the job description, then saves the job to AutoApply with `state=scraped`
4. The button updates inline: **✓ Scraped**, **✓ Already staged**, or an error

**From a single job page** (`linkedin.com/jobs/view/123456/`)
1. Open any individual job listing
2. A blue **Scrape** button appears fixed in the top-right of the page once the description loads
3. Click it — the job is saved immediately, no navigation needed

In both cases, duplicates are detected automatically and reported as **✓ Already staged**.
