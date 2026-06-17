// Source modules call registerSource() on load. injector.js runs first (manifest order).
let _source = null;
let _viewSource = null;

function registerSource(config) {
  _source = config;
  _init();
}

function registerViewSource(config) {
  _viewSource = config;
  _initView();
}

async function _initView() {
  const ready = await _waitForReady(_viewSource, 10000);
  if (!ready) return;
  _injectViewButton();
}

function _injectViewButton() {
  if (document.getElementById('autoapply-view-btn')) return;

  const btn = document.createElement('button');
  btn.id = 'autoapply-view-btn';
  btn.textContent = 'Scrape';
  btn.style.cssText = [
    'position:fixed', 'top:80px', 'right:20px', 'z-index:9999',
    'padding:6px 14px', 'font-size:13px', 'font-weight:600',
    'cursor:pointer', 'background:#0a66c2', 'color:#fff',
    'border:none', 'border-radius:4px', 'line-height:1.4',
    'box-shadow:0 2px 6px rgba(0,0,0,0.3)',
  ].join(';');
  document.body.appendChild(btn);

  btn.addEventListener('click', async (e) => {
    e.preventDefault();
    e.stopPropagation();
    await _handleViewScrape(btn);
  });
}

async function _handleViewScrape(btn) {
  btn.disabled = true;
  btn.textContent = 'Scraping…';

  try {
    const jobData = _viewSource.getJobData();
    if (!jobData.title || !jobData.url) {
      btn.textContent = '✗ Parse error';
      return;
    }

    const { isDuplicate } = await _msg({ type: 'CHECK_DEDUP', job_key: jobData.job_key });
    if (isDuplicate) {
      btn.textContent = '✓ Already staged';
      return;
    }

    const description = _viewSource.getDescription();
    const payload = {
      ...jobData,
      description,
      remote: /remote/i.test(jobData.location || ''),
      salary: '',
      posted_at: '',
      scraped_at: new Date().toISOString(),
    };

    const result = await _msg({ type: 'SCRAPE_JOB', payload });

    if (!result.ok && result.error === "no_account") {
      btn.textContent = "✗ Sign in required";
      btn.title = "Open the Job Scraper extension and sign in to AutoApply.";
      return;
    }
    if (!result.ok) {
      btn.textContent = '✗ Server error';
      return;
    }

    btn.textContent = result.status === 'duplicate' ? '✓ Already staged' : '✓ Scraped';
  } catch (err) {
    console.error('[job-scraper] view scrape failed:', err);
    btn.textContent = '✗ Server error';
  }
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

    // Mark current detail pane stale so we wait for the NEW one to load
    // after clicking the card.
    if (typeof _source.markStale === "function") _source.markStale();

    _source.clickCard(card);

    const ready = await _waitForReady(_source, 10000);
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

    if (!result.ok && result.error === "no_account") {
      btn.textContent = "✗ Sign in required";
      btn.title = "Open the Job Scraper extension and sign in to AutoApply.";
      return;
    }
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

function _waitForReady(source, timeoutMs) {
  const check = () => {
    if (typeof source.isDetailReady === 'function') return source.isDetailReady();
    return source.detailReadySelector
      ? !!document.querySelector(source.detailReadySelector)
      : false;
  };
  return new Promise((resolve) => {
    if (check()) { resolve(true); return; }
    const obs = new MutationObserver(() => {
      if (check()) {
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

