# Browser Extension Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a MV3 browser extension that injects a Scrape button on LinkedIn and Indeed job cards, extracts full job data including the detail-pane description, and stages jobs to the local FastAPI server via `POST /api/scraper/stage-job`.

**Architecture:** `injector.js` owns all orchestration (MutationObserver, button injection, click handling, detail-pane waiting). `linkedin.js` and `indeed.js` register source configs (selectors + callbacks) with `injector.js` via `registerSource()`. The background service worker owns deduplication and the FastAPI POST. The FastAPI endpoint constructs a `ScrapedJob` and calls the existing `save_jobs()`.

**Tech Stack:** Browser extension MV3 (plain ES2020+, no build step), FastAPI/SQLAlchemy (existing stack), pytest + TestClient for server-side tests.

> **Selector warning:** LinkedIn and Indeed change their DOM frequently. The selectors in Tasks 4 and 5 are correct as of the spec date but must be verified by inspecting the live pages before committing. Treat them as starting points.

---

## File Map

| File | Action |
|---|---|
| `1_scraper/job-scraper-extension/manifest.json` | Create |
| `1_scraper/job-scraper-extension/background/service_worker.js` | Create |
| `1_scraper/job-scraper-extension/content/injector.js` | Create |
| `1_scraper/job-scraper-extension/content/linkedin.js` | Create |
| `1_scraper/job-scraper-extension/content/indeed.js` | Create |
| `1_scraper/job-scraper-extension/popup/popup.html` | Create |
| `1_scraper/job-scraper-extension/popup/popup.js` | Create |
| `web/routers/scraper.py` | Modify — add `POST /api/scraper/stage-job` |
| `tests/scraper/test_stage_job.py` | Create |

---

## Task 1: Extension skeleton + manifest

**Files:**
- Create: `1_scraper/job-scraper-extension/manifest.json`
- Create: `1_scraper/job-scraper-extension/background/.gitkeep`
- Create: `1_scraper/job-scraper-extension/content/.gitkeep`
- Create: `1_scraper/job-scraper-extension/popup/.gitkeep`

- [ ] **Step 1: Create the directory structure**

```bash
mkdir -p 1_scraper/job-scraper-extension/background
mkdir -p 1_scraper/job-scraper-extension/content
mkdir -p 1_scraper/job-scraper-extension/popup
```

- [ ] **Step 2: Create `manifest.json`**

```json
{
  "manifest_version": 3,
  "name": "Job Scraper",
  "version": "1.0.0",
  "description": "Scrapes job listings from LinkedIn and Indeed.",
  "permissions": ["storage", "tabs"],
  "host_permissions": [
    "https://*.linkedin.com/*",
    "https://*.indeed.com/*",
    "http://localhost/*"
  ],
  "background": {
    "service_worker": "background/service_worker.js"
  },
  "content_scripts": [
    {
      "matches": [
        "https://www.linkedin.com/jobs/*",
        "https://www.linkedin.com/my-items/*"
      ],
      "js": ["content/injector.js", "content/linkedin.js"]
    },
    {
      "matches": [
        "https://www.indeed.com/jobs*",
        "https://myjobs.indeed.com/*"
      ],
      "js": ["content/injector.js", "content/indeed.js"]
    }
  ],
  "action": {
    "default_popup": "popup/popup.html",
    "default_title": "Job Scraper"
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add 1_scraper/job-scraper-extension/
git commit -m "[feat] Add browser extension manifest and directory skeleton"
```

---

## Task 2: Background service worker

**Files:**
- Create: `1_scraper/job-scraper-extension/background/service_worker.js`

- [ ] **Step 1: Create `service_worker.js`**

```js
const DEDUP_KEY = "stagedJobKeys";

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type === "CHECK_DEDUP") {
    chrome.storage.local.get(DEDUP_KEY).then(({ [DEDUP_KEY]: keys = [] }) => {
      sendResponse({ isDuplicate: keys.includes(message.job_key) });
    });
    return true;
  }

  if (message.type === "SCRAPE_JOB") {
    handleScrape(message.payload)
      .then(sendResponse)
      .catch((err) => sendResponse({ ok: false, error: err.message }));
    return true;
  }
});

async function handleScrape(payload) {
  const { [DEDUP_KEY]: keys = [] } = await chrome.storage.local.get(DEDUP_KEY);
  const keySet = new Set(keys);

  if (keySet.has(payload.job_key)) {
    return { ok: true, status: "duplicate" };
  }

  const { fastapiUrl = "http://localhost:8000" } = await chrome.storage.sync.get("fastapiUrl");

  const res = await fetch(`${fastapiUrl}/api/scraper/stage-job`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }

  const data = await res.json();
  keySet.add(payload.job_key);
  await chrome.storage.local.set({ [DEDUP_KEY]: [...keySet] });
  return { ok: true, status: data.status };
}
```

- [ ] **Step 2: Commit**

```bash
git add 1_scraper/job-scraper-extension/background/service_worker.js
git commit -m "[feat] Add extension service worker with dedup and FastAPI POST"
```

---

## Task 3: Shared injector

**Files:**
- Create: `1_scraper/job-scraper-extension/content/injector.js`

- [ ] **Step 1: Create `injector.js`**

```js
// Source modules call registerSource() on load. injector.js runs first (manifest order).
let _source = null;

function registerSource(config) {
  _source = config;
  _init();
}

function _init() {
  _injectButtons(document.querySelectorAll(_source.cardSelector));
  new MutationObserver(() => {
    _injectButtons(document.querySelectorAll(_source.cardSelector));
  }).observe(document.body, { childList: true, subtree: true });
}

function _injectButtons(cards) {
  for (const card of cards) {
    if (card.dataset.scraperInjected) continue;
    card.dataset.scraperInjected = "1";

    const btn = document.createElement("button");
    btn.textContent = "Scrape";
    btn.style.cssText = [
      "position:absolute", "top:8px", "right:8px", "z-index:9999",
      "padding:4px 10px", "font-size:11px", "font-weight:600",
      "cursor:pointer", "background:#0a66c2", "color:#fff",
      "border:none", "border-radius:4px", "line-height:1.4",
    ].join(";");
    card.style.position = "relative";
    card.appendChild(btn);

    btn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      _handleScrape(card, btn);
    });
  }
}

async function _handleScrape(card, btn) {
  btn.disabled = true;
  btn.textContent = "Scraping…";

  try {
    const jobData = _source.getJobData(card);
    if (!jobData.title || !jobData.url) {
      btn.textContent = "✗ Parse error";
      return;
    }

    const { isDuplicate } = await _msg({ type: "CHECK_DEDUP", job_key: jobData.job_key });
    if (isDuplicate) {
      btn.textContent = "✓ Already staged";
      return;
    }

    _source.clickCard(card);

    const ready = await _waitForSelector(_source.detailReadySelector, 10000);
    if (!ready) {
      btn.textContent = "✗ Timeout";
      return;
    }

    const description = _source.getDescription();
    const payload = {
      ...jobData,
      description,
      remote: /remote/i.test(jobData.location || ""),
      salary: "",
      posted_at: "",
      scraped_at: new Date().toISOString(),
    };

    const result = await _msg({ type: "SCRAPE_JOB", payload });

    if (!result.ok) {
      btn.textContent = "✗ Server error";
      return;
    }

    btn.textContent = result.status === "duplicate" ? "✓ Already staged" : "✓ Scraped";

    if (result.status !== "duplicate" && _source.bookmarkCard) {
      try {
        _source.bookmarkCard(card);
      } catch (err) {
        console.warn("[job-scraper] bookmark failed:", err);
      }
    }
  } catch (err) {
    console.error("[job-scraper] scrape failed:", err);
    btn.textContent = "✗ Server error";
  }
}

function _waitForSelector(selector, timeoutMs) {
  return new Promise((resolve) => {
    if (document.querySelector(selector)) { resolve(true); return; }
    const obs = new MutationObserver(() => {
      if (document.querySelector(selector)) {
        obs.disconnect();
        clearTimeout(timer);
        resolve(true);
      }
    });
    obs.observe(document.body, { childList: true, subtree: true });
    const timer = setTimeout(() => { obs.disconnect(); resolve(false); }, timeoutMs);
  });
}

function _msg(message) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage(message, (response) => {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message));
      } else {
        resolve(response);
      }
    });
  });
}
```

- [ ] **Step 2: Commit**

```bash
git add 1_scraper/job-scraper-extension/content/injector.js
git commit -m "[feat] Add extension injector with MutationObserver and scrape orchestration"
```

---

## Task 4: LinkedIn source module

**Files:**
- Create: `1_scraper/job-scraper-extension/content/linkedin.js`

> **Before coding:** Open LinkedIn job search in Chrome DevTools and confirm the selectors below. Right-click a job card → Inspect, then verify each selector. Common LinkedIn class names to look for: `jobs-search-results__list-item`, `job-card-list__title`, `job-card-container__company-name`, `jobs-description__content`, `jobs-save-button`.

- [ ] **Step 1: Inspect live LinkedIn DOM and note correct selectors**

Open `https://www.linkedin.com/jobs/search/?keywords=software+engineer` in Chrome. Open DevTools (F12). Run in the console:

```js
// Verify card selector
document.querySelectorAll('.jobs-search-results__list-item').length
// Should return the number of visible job cards (> 0)

// Verify title selector within a card
document.querySelector('.jobs-search-results__list-item a.job-card-list__title--link')?.textContent?.trim()
// Should return the first job title

// Verify detail pane selector (click a card first)
document.querySelector('.jobs-description__content')?.innerText?.slice(0, 80)
// Should return the beginning of the job description
```

If any return `undefined` or `null`, find the correct selector in DevTools and update accordingly.

- [ ] **Step 2: Create `linkedin.js`**

Replace selectors below if Step 1 found corrections:

```js
const _IS_SEARCH = /^\/jobs\//.test(location.pathname);
const _IS_SAVED = /^\/my-items\/saved-jobs/.test(location.pathname);

if (_IS_SEARCH || _IS_SAVED) {
  registerSource({
    cardSelector: _IS_SEARCH
      ? ".jobs-search-results__list-item"
      : ".entity-result",

    getJobData(card) {
      const anchor = card.querySelector(
        "a.job-card-list__title--link, a.job-card-container__link, .entity-result__title-text a"
      );
      const rawUrl = anchor?.href ?? "";
      const url = rawUrl.split("?")[0];
      const jobIdMatch = url.match(/\/view\/(\d+)/);
      const job_key = jobIdMatch
        ? `linkedin_${jobIdMatch[1]}`
        : `linkedin_${Date.now()}`;
      const title = anchor?.innerText?.trim() ?? "";
      const company = card.querySelector(
        ".job-card-container__primary-description, .artdeco-entity-lockup__subtitle, .entity-result__primary-subtitle"
      )?.innerText?.trim() ?? "";
      const location = card.querySelector(
        ".job-card-container__metadata-item, .job-card-list__footer-item, .entity-result__secondary-subtitle"
      )?.innerText?.trim() ?? "";
      return { source: "linkedin", job_key, title, company, location, url };
    },

    getDescription() {
      return document.querySelector(
        ".jobs-description__content .jobs-box__html-content, #job-details, .jobs-description-content__text"
      )?.innerText?.trim() ?? "";
    },

    clickCard(card) {
      const anchor = card.querySelector(
        "a.job-card-list__title--link, a.job-card-container__link, .entity-result__title-text a"
      );
      anchor?.click();
    },

    detailReadySelector: ".jobs-description__content, #job-details, .jobs-description-content__text",

    bookmarkCard: _IS_SEARCH
      ? (card) => {
          const btn = card.querySelector(
            "button.jobs-save-button, button[aria-label*='Save job'], button[aria-label*='save job']"
          );
          btn?.click();
        }
      : null,
  });
}
```

- [ ] **Step 3: Load unpacked and verify LinkedIn search**

1. Go to `chrome://extensions` → Enable Developer Mode → Load Unpacked → select `1_scraper/job-scraper-extension/`
2. Navigate to `https://www.linkedin.com/jobs/search/?keywords=software+engineer`
3. Confirm: a blue "Scrape" button appears in the top-right corner of each job card
4. Click a Scrape button — confirm button changes to "Scraping…" then "✓ Scraped"
5. Click the same button again — confirm "✓ Already staged" appears immediately

- [ ] **Step 4: Verify LinkedIn saved jobs**

1. Navigate to `https://www.linkedin.com/my-items/saved-jobs/`
2. Confirm Scrape buttons appear on saved job cards
3. Click one — confirm "✓ Scraped" (no bookmark toggled)

- [ ] **Step 5: Commit**

```bash
git add 1_scraper/job-scraper-extension/content/linkedin.js
git commit -m "[feat] Add LinkedIn source module for job card scraping"
```

---

## Task 5: Indeed source module

**Files:**
- Create: `1_scraper/job-scraper-extension/content/indeed.js`

> **Before coding:** Open Indeed job search in Chrome DevTools and confirm selectors. Common Indeed class names: `job_seen_beacon`, `jobTitle`, `companyName`, `companyLocation`, `jobDescriptionText`.

- [ ] **Step 1: Inspect live Indeed DOM and note correct selectors**

Open `https://www.indeed.com/jobs?q=software+engineer` in Chrome. Run in the console:

```js
// Verify card selector
document.querySelectorAll('.job_seen_beacon').length
// Should return number of visible job cards

// Verify title link within a card
document.querySelector('.job_seen_beacon h2.jobTitle a')?.innerText?.trim()
// Should return first job title

// Verify description (click a card first)
document.querySelector('#jobDescriptionText')?.innerText?.slice(0, 80)
// Should return start of description
```

- [ ] **Step 2: Create `indeed.js`**

```js
const _IS_SEARCH = location.hostname === "www.indeed.com";
const _IS_SAVED = location.hostname === "myjobs.indeed.com";

if (_IS_SEARCH || _IS_SAVED) {
  registerSource({
    cardSelector: _IS_SEARCH
      ? ".job_seen_beacon"
      : "div.atw-AppCard[data-jobkey]",

    getJobData(card) {
      if (_IS_SEARCH) {
        const anchor = card.querySelector("h2.jobTitle a, .jobTitle a");
        const rawUrl = anchor ? new URL(anchor.href, location.href).href : "";
        const jkMatch = rawUrl.match(/[?&]jk=([a-f0-9]+)/i);
        const job_key = jkMatch ? `indeed_${jkMatch[1]}` : `indeed_${Date.now()}`;
        const title = anchor?.innerText?.trim() ?? "";
        const company = card.querySelector(
          ".companyName, [data-testid='company-name']"
        )?.innerText?.trim() ?? "";
        const location = card.querySelector(
          ".companyLocation, [data-testid='text-location']"
        )?.innerText?.trim() ?? "";
        return { source: "indeed", job_key, title, company, location, url: rawUrl };
      } else {
        // myjobs.indeed.com — same DOM as retired extension
        const jobKey = card.getAttribute("data-jobkey") ?? "";
        const anchor = card.querySelector("a.atw-JobInfo-jobTitle");
        const title = anchor?.innerText?.trim() ?? "";
        const url = anchor?.href ?? "";
        const spans = card.querySelectorAll(".atw-JobInfo-companyLocation span");
        const company = spans[0]?.innerText?.trim() ?? "";
        const location = spans[1]?.innerText?.trim() ?? "";
        return { source: "indeed", job_key: `indeed_${jobKey}`, title, company, location, url };
      }
    },

    getDescription() {
      return document.querySelector("#jobDescriptionText")?.innerText?.trim() ?? "";
    },

    clickCard(card) {
      if (_IS_SEARCH) {
        card.querySelector("h2.jobTitle a, .jobTitle a")?.click();
      } else {
        card.querySelector("a.atw-JobInfo-jobTitle")?.click();
      }
    },

    detailReadySelector: "#jobDescriptionText",

    bookmarkCard: _IS_SEARCH
      ? (card) => {
          const btn = card.querySelector(
            "button[aria-label*='save'], button[aria-label*='Save'], .jobsearch-SaveJobButton"
          );
          btn?.click();
        }
      : null,
  });
}
```

- [ ] **Step 3: Reload extension and verify Indeed search**

1. Go to `chrome://extensions` → click the refresh icon on Job Scraper
2. Navigate to `https://www.indeed.com/jobs?q=software+engineer`
3. Confirm Scrape buttons appear on job cards
4. Click one — confirm "✓ Scraped"

- [ ] **Step 4: Verify Indeed saved jobs**

1. Navigate to `https://myjobs.indeed.com/`
2. Confirm Scrape buttons appear, no bookmark action fires

- [ ] **Step 5: Commit**

```bash
git add 1_scraper/job-scraper-extension/content/indeed.js
git commit -m "[feat] Add Indeed source module for job card scraping"
```

---

## Task 6: Popup

**Files:**
- Create: `1_scraper/job-scraper-extension/popup/popup.html`
- Create: `1_scraper/job-scraper-extension/popup/popup.js`

- [ ] **Step 1: Create `popup.html`**

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body { font-family: sans-serif; padding: 12px; min-width: 280px; font-size: 13px; }
    h3 { margin: 0 0 12px; font-size: 14px; }
    label { display: block; margin-bottom: 4px; font-size: 11px; color: #555; }
    input { width: 100%; box-sizing: border-box; padding: 5px; margin-bottom: 10px; border: 1px solid #ccc; border-radius: 3px; }
    button { width: 100%; padding: 6px; cursor: pointer; border: 1px solid #ccc; border-radius: 3px; margin-bottom: 6px; background: #f5f5f5; }
    button#btn-save { background: #0a66c2; color: #fff; border-color: #0a66c2; }
    #msg { font-size: 11px; min-height: 14px; }
  </style>
</head>
<body>
  <h3>Job Scraper</h3>
  <label>FastAPI Base URL</label>
  <input id="fastapi-url" type="text" placeholder="http://localhost:8000">
  <button id="btn-save">Save</button>
  <button id="btn-clear">Clear history (<span id="count">0</span> jobs staged)</button>
  <div id="msg"></div>
  <script src="popup.js"></script>
</body>
</html>
```

- [ ] **Step 2: Create `popup.js`**

```js
const urlInput = document.getElementById("fastapi-url");
const btnSave = document.getElementById("btn-save");
const btnClear = document.getElementById("btn-clear");
const countEl = document.getElementById("count");
const msgEl = document.getElementById("msg");

async function load() {
  const { fastapiUrl = "http://localhost:8000" } = await chrome.storage.sync.get("fastapiUrl");
  urlInput.value = fastapiUrl;
  const { stagedJobKeys = [] } = await chrome.storage.local.get("stagedJobKeys");
  countEl.textContent = stagedJobKeys.length;
}

btnSave.addEventListener("click", async () => {
  const url = urlInput.value.trim();
  if (!url) { showMsg("Enter a URL.", "red"); return; }
  await chrome.storage.sync.set({ fastapiUrl: url });
  showMsg("Saved.");
});

btnClear.addEventListener("click", async () => {
  await chrome.storage.local.set({ stagedJobKeys: [] });
  countEl.textContent = "0";
  showMsg("History cleared.");
});

function showMsg(text, color = "green") {
  msgEl.style.color = color;
  msgEl.textContent = text;
  setTimeout(() => { msgEl.textContent = ""; }, 3000);
}

load();
```

- [ ] **Step 3: Commit**

```bash
git add 1_scraper/job-scraper-extension/popup/
git commit -m "[feat] Add extension popup with FastAPI URL config and history clear"
```

---

## Task 7: FastAPI `POST /api/scraper/stage-job` endpoint

**Files:**
- Modify: `web/routers/scraper.py`
- Create: `tests/scraper/test_stage_job.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/scraper/test_stage_job.py`:

```python
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import get_db
from db.models import Base, Job
from web.main import app

@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


_VALID = {
    "source": "linkedin",
    "job_key": "linkedin_123",
    "title": "Software Engineer",
    "company": "Acme Corp",
    "url": "https://www.linkedin.com/jobs/view/123",
    "description": "Build cool stuff.",
    "location": "Remote (US)",
    "remote": True,
    "salary": "",
    "posted_at": "",
    "scraped_at": "2026-04-28T12:00:00Z",
}


def test_stage_job_returns_staged_and_creates_db_record(client, db_session):
    response = client.post("/api/scraper/stage-job", json=_VALID)
    assert response.status_code == 200
    assert response.json() == {"status": "staged", "job_key": "linkedin_123"}
    assert db_session.query(Job).filter_by(job_key="linkedin_123").count() == 1


def test_stage_job_returns_duplicate_for_same_url(client, db_session):
    client.post("/api/scraper/stage-job", json=_VALID)
    payload2 = {**_VALID, "job_key": "linkedin_999"}
    response = client.post("/api/scraper/stage-job", json=payload2)
    assert response.status_code == 200
    assert response.json() == {"status": "duplicate", "job_key": "linkedin_999"}
    assert db_session.query(Job).count() == 1  # still only one record


def test_stage_job_returns_422_for_missing_title(client):
    payload = {k: v for k, v in _VALID.items() if k != "title"}
    response = client.post("/api/scraper/stage-job", json=payload)
    assert response.status_code == 422


def test_stage_job_returns_422_for_missing_url(client):
    payload = {k: v for k, v in _VALID.items() if k != "url"}
    response = client.post("/api/scraper/stage-job", json=payload)
    assert response.status_code == 422
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/scraper/test_stage_job.py -v
```

Expected: all 4 tests fail with 404 (endpoint doesn't exist yet).

- [ ] **Step 3: Add the endpoint to `web/routers/scraper.py`**

Add after the existing imports and before `router = APIRouter(...)`:

```python
from pydantic import BaseModel
from scraper.runner import save_jobs
from scraper.base import ScrapedJob
```

Add the request model and endpoint after the existing `trigger_scrape` function:

```python
class StageJobRequest(BaseModel):
    source: str
    job_key: str
    title: str
    company: str
    url: str
    description: str
    location: str = ""
    salary: str = ""
    remote: bool = False
    posted_at: str = ""
    scraped_at: str = ""


@router.post("/stage-job")
def stage_job(body: StageJobRequest, db: Session = Depends(get_db)) -> dict[str, str]:
    job = ScrapedJob(
        source=body.source,
        job_key=body.job_key,
        title=body.title,
        company=body.company,
        url=body.url,
        description=body.description,
        location=body.location,
        salary=body.salary,
        remote=body.remote,
        posted_at=body.posted_at,
    )
    inserted = save_jobs(db, [job])
    status = "staged" if inserted > 0 else "duplicate"
    return {"status": status, "job_key": body.job_key}
```

The full updated file should look like:

```python
from __future__ import annotations

import threading
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import SessionLocal, get_db
from db.models import Config
from scraper.base import JobSource, ScrapedJob
from scraper.remotive import RemotiveSource
from scraper.remoteok import RemoteOKSource
from scraper.runner import run_scraper, save_jobs

router = APIRouter(prefix="/api/scraper")

_SOURCES = {
    "remotive": RemotiveSource,
    "remoteok": RemoteOKSource,
}


def _get_enabled_source_ids(db: Session) -> list[str]:
    row = db.query(Config).filter_by(key="scraper_sources").first()
    if not row or not row.value.strip():
        return []
    return [s.strip() for s in row.value.split(",") if s.strip() in _SOURCES]


def _run_in_background(source_ids: list[str]) -> None:
    db = SessionLocal()
    try:
        sources = [_SOURCES[sid]() for sid in source_ids]
        run_scraper(db, sources)
    finally:
        db.close()


@router.post("/run")
def trigger_scrape(db: Session = Depends(get_db)) -> dict[str, Any]:
    source_ids = _get_enabled_source_ids(db)

    if not source_ids:
        raise HTTPException(
            status_code=400,
            detail="No enabled sources configured. Set 'scraper_sources' in the config table.",
        )

    t = threading.Thread(target=_run_in_background, args=(source_ids,), daemon=True)
    t.start()
    return {"status": "started", "sources": source_ids}


class StageJobRequest(BaseModel):
    source: str
    job_key: str
    title: str
    company: str
    url: str
    description: str
    location: str = ""
    salary: str = ""
    remote: bool = False
    posted_at: str = ""
    scraped_at: str = ""


@router.post("/stage-job")
def stage_job(body: StageJobRequest, db: Session = Depends(get_db)) -> dict[str, str]:
    job = ScrapedJob(
        source=body.source,
        job_key=body.job_key,
        title=body.title,
        company=body.company,
        url=body.url,
        description=body.description,
        location=body.location,
        salary=body.salary,
        remote=body.remote,
        posted_at=body.posted_at,
    )
    inserted = save_jobs(db, [job])
    status = "staged" if inserted > 0 else "duplicate"
    return {"status": status, "job_key": body.job_key}
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/scraper/test_stage_job.py -v
```

Expected output:
```
tests/scraper/test_stage_job.py::test_stage_job_returns_staged_and_creates_db_record PASSED
tests/scraper/test_stage_job.py::test_stage_job_returns_duplicate_for_same_url PASSED
tests/scraper/test_stage_job.py::test_stage_job_returns_422_for_missing_title PASSED
tests/scraper/test_stage_job.py::test_stage_job_returns_422_for_missing_url PASSED
```

- [ ] **Step 5: Run full test suite to check for regressions**

```bash
pytest --tb=short -q
```

Expected: all previously passing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add web/routers/scraper.py tests/scraper/test_stage_job.py
git commit -m "[feat] Add POST /api/scraper/stage-job endpoint"
```

---

## Task 8: End-to-end verification

No automated tests for the extension. Run through this checklist manually with the FastAPI server running (`uvicorn web.main:app --reload`).

- [ ] **Step 1: Verify LinkedIn search scrape creates a DB record**

1. Reload the extension at `chrome://extensions`
2. Navigate to `https://www.linkedin.com/jobs/search/?keywords=software+engineer`
3. Click Scrape on any card — button should show "✓ Scraped"
4. In a terminal: `sqlite3 auto_apply.db "SELECT job_key, title, source, state FROM jobs ORDER BY id DESC LIMIT 1;"`
5. Confirm the record exists with `state=scraped` and `source=linkedin`

- [ ] **Step 2: Verify dedup prevents double-insert**

1. Click the same Scrape button again — should show "✓ Already staged" instantly
2. Re-run the sqlite3 query — row count should be unchanged

- [ ] **Step 3: Verify LinkedIn saved jobs**

1. Navigate to `https://www.linkedin.com/my-items/saved-jobs/`
2. Click Scrape on a card — confirm "✓ Scraped", no bookmark toggle
3. Confirm DB record created

- [ ] **Step 4: Verify Indeed search**

1. Navigate to `https://www.indeed.com/jobs?q=software+engineer`
2. Click Scrape on a card — confirm "✓ Scraped"
3. Confirm DB record with `source=indeed`

- [ ] **Step 5: Verify Indeed saved jobs**

1. Navigate to `https://myjobs.indeed.com/`
2. Click Scrape — confirm "✓ Scraped", no bookmark toggle

- [ ] **Step 6: Retire old extension**

Once all above steps pass, delete the old extension directory:

```bash
git rm -r 1_scraper/indeed-jobs-extension/
git commit -m "[chore] Retire old Indeed-only extension, replaced by job-scraper-extension"
```

- [ ] **Step 7: Update `1_scraper/CONTEXT.md`**

Replace the existing content to reflect the new extension architecture. Commit:

```bash
git add 1_scraper/CONTEXT.md
git commit -m "[docs] Update scraper CONTEXT.md for new job-scraper-extension"
```
