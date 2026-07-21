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
    const applyInfo = (typeof _viewSource.getApplyInfo === 'function')
      ? _viewSource.getApplyInfo()
      : { easy_apply: null, apply_url_raw: '' };
    const payload = {
      ...jobData,
      description,
      remote: /remote/i.test(jobData.location || ''),
      salary: '',
      posted_at: '',
      scraped_at: new Date().toISOString(),
      easy_apply: applyInfo.easy_apply,
      apply_url_raw: applyInfo.apply_url_raw,
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
    const applyInfo = (typeof _source.getApplyInfo === "function")
      ? _source.getApplyInfo()
      : { easy_apply: null, apply_url_raw: "" };
    const payload = {
      ...jobData,
      description,
      remote: /remote/i.test(jobData.location || ""),
      salary: "",
      posted_at: "",
      scraped_at: new Date().toISOString(),
      easy_apply: applyInfo.easy_apply,
      apply_url_raw: applyInfo.apply_url_raw,
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

// --- Application-plan enumeration (read-only, no form writing) -------------
// Runs on recognized ATS apply-page domains (see manifest.json content_scripts).
// Matches the current page against a staged job's apply URL (tracked in
// service_worker.js's stagedJobMeta), enumerates the visible form (via
// form_enumerate.js, loaded alongside this script), and POSTs the enumeration
// to the application-plan endpoint. Purely read-only — form-fill is a later
// sub-project. Never blocks page interaction; all failures are swallowed.
const _ATS_APPLY_HOSTS = /\.(greenhouse|lever|ashbyhq)\.(io|co|com)$/i;

// Prefix so users can filter the DevTools console for the whole enumeration
// story on an apply page. Every silent-exit path below logs one line, turning
// "nothing happened" into a diagnosable trace.
const _AP_LOG = "[job-scraper][application-plan]";

function _maybeEnumerateApplyForm() {
  if (!_ATS_APPLY_HOSTS.test(location.hostname)) return;
  if (typeof enumerateForm !== "function") {
    console.warn(`${_AP_LOG} form_enumerate.js not loaded — skipping`);
    return;
  }
  _runFormEnumeration().catch((err) => {
    console.warn(`${_AP_LOG} enumeration failed:`, err);
  });
}

async function _runFormEnumeration() {
  const found = await _msg({ type: "FIND_STAGED_JOB", url: location.href });
  const jobKey = found && found.job_key;
  if (!jobKey) {
    console.info(
      `${_AP_LOG} this page did not match any staged job (check stagedJobMeta / that the job was staged via the extension as an external posting) — nothing to do`
    );
    return;
  }
  console.info(`${_AP_LOG} matched staged job ${jobKey}; waiting for form to render`);

  const ready = await _waitForFormReady(8000);
  if (!ready) {
    console.warn(`${_AP_LOG} no form or input controls appeared within 8s — giving up`);
    return;
  }

  const enumerated_fields = enumerateForm();
  if (!enumerated_fields.length) {
    console.warn(`${_AP_LOG} form ready but zero enumerable fields found`);
    return;
  }

  const result = await _msg({ type: "ENUMERATE_FORM", job_key: jobKey, enumerated_fields });
  if (result && result.ok) {
    console.info(
      `${_AP_LOG} posted ${enumerated_fields.length} fields for ${jobKey} to ${result.server_url} — reopen the "Plan" modal to view`
    );
    if (result.application_answers_complete === false) {
      _showAnswersNudge(result.server_url);
    }
  } else {
    console.warn(
      `${_AP_LOG} server rejected the enumeration for ${jobKey}:`,
      (result && result.error) || "unknown error",
      "(if this is a 404, the extension's server mode likely points at a server that doesn't have this job)"
    );
  }
}

// "Ready" means either a real <form> OR (for form-less SPA ATSs like Ashby)
// the page has rendered actual input controls. enumerateForm() falls back to
// document.body when there's no <form>, so gating strictly on <form> would
// permanently block enumeration on Ashby — the exact ATS the fallback exists
// for. We prefer a <form> when present but accept controls-in-body otherwise.
function _waitForFormReady(timeoutMs) {
  const check = () =>
    !!document.querySelector("form") ||
    document.querySelectorAll("input, select, textarea").length > 0;
  return new Promise((resolve) => {
    if (check()) {
      resolve(true);
      return;
    }
    const obs = new MutationObserver(() => {
      if (check()) {
        obs.disconnect();
        clearTimeout(timer);
        resolve(true);
      }
    });
    obs.observe(document.body, { childList: true, subtree: true });
    const timer = setTimeout(() => {
      obs.disconnect();
      resolve(check());
    }, timeoutMs);
  });
}

// Non-blocking banner nudging the user to fill out application-answer
// profile fields (eligibility/EEO) so more of the form can be mapped. No
// alert()/confirm() — those break the extension. Dismissible, never re-shown
// once closed for this page load.
function _showAnswersNudge(serverUrl) {
  if (document.getElementById("autoapply-answers-nudge")) return;

  const bar = document.createElement("div");
  bar.id = "autoapply-answers-nudge";
  bar.style.cssText = [
    "position:fixed", "bottom:20px", "right:20px", "z-index:2147483647",
    "max-width:320px", "padding:10px 14px", "font-size:12px", "font-weight:500",
    "font-family:sans-serif", "background:#1a1a2e", "color:#fff", "border-radius:6px",
    "box-shadow:0 2px 10px rgba(0,0,0,0.4)", "line-height:1.4",
  ].join(";");

  const link = document.createElement("a");
  link.href = `${serverUrl || "https://autoapply.matthewbarlow.me"}/#/settings`;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.style.cssText = "color:#7dd3fc;text-decoration:underline;";
  link.textContent = "Complete your application answers to auto-fill more →";
  bar.appendChild(link);

  const close = document.createElement("span");
  close.textContent = " ✕";
  close.style.cssText = "margin-left:10px;cursor:pointer;opacity:0.7;";
  close.addEventListener("click", () => bar.remove());
  bar.appendChild(close);

  document.body.appendChild(bar);
}

_maybeEnumerateApplyForm();

