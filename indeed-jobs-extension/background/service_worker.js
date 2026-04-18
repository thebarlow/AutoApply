// Orchestrates scraping: gets job list, opens each viewjob tab, collects
// descriptions, POSTs to n8n webhook, and tracks sent job keys.

const DEFAULT_WEBHOOK_URL = "http://localhost:5678/webhook/indeed-jobs";
const DEDUP_KEY = "sentJobKeys";

// Pending resolvers waiting for JOB_DESCRIPTION messages, keyed by job_key.
const pendingJobs = new Map();

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type === "START_SCRAPE") {
    handleScrape(message.tabId).catch(console.error);
    sendResponse({ ok: true });
  }

  if (message.type === "JOB_DESCRIPTION" || message.type === "JOB_DESCRIPTION_ERROR") {
    const resolver = pendingJobs.get(message.job_key);
    if (resolver) {
      pendingJobs.delete(message.job_key);
      resolver(message);
    }
  }
});

async function handleScrape(savedJobsTabId) {
  notifyPopup({ status: "scraping_list" });

  // 1. Get job cards from the saved jobs page.
  let jobs;
  try {
    const response = await chrome.tabs.sendMessage(savedJobsTabId, { type: "GET_JOBS" });
    jobs = response.jobs;
  } catch (err) {
    notifyPopup({ status: "error", message: "Could not read saved jobs page. Make sure you are on myjobs.indeed.com." });
    return;
  }

  if (!jobs.length) {
    notifyPopup({ status: "done", sent: 0, total: 0 });
    return;
  }

  // 2. Filter out already-sent jobs.
  const { sentJobKeys = [] } = await chrome.storage.local.get(DEDUP_KEY);
  const sentSet = new Set(sentJobKeys);
  const newJobs = jobs.filter((j) => !sentSet.has(j.job_key));

  if (!newJobs.length) {
    notifyPopup({ status: "done", sent: 0, total: jobs.length, allDuplicates: true });
    return;
  }

  const { webhookUrl = DEFAULT_WEBHOOK_URL } = await chrome.storage.sync.get("webhookUrl");

  // 3. Process each new job sequentially.
  let sent = 0;
  for (let i = 0; i < newJobs.length; i++) {
    const job = newJobs[i];
    notifyPopup({ status: "processing", current: i + 1, total: newJobs.length, title: job.title });

    // Random delay between tab opens to avoid looking like a bot.
    if (i > 0) {
      await sleep(600 + Math.random() * 800);
    }

    let description = "";
    let tab;
    try {
      description = await scrapeJobDescription(job.url, savedJobsTabId);
    } catch (err) {
      console.warn(`Failed to scrape ${job.job_key}:`, err.message);
      description = "";
    } finally {
      // Tab is closed inside scrapeJobDescription; this is a no-op if already closed.
      if (tab) {
        chrome.tabs.remove(tab.id).catch(() => {});
      }
    }

    // POST to n8n even if description scraping failed — log what we have.
    const payload = {
      job_key: job.job_key,
      title: job.title,
      company: job.company,
      location: job.location,
      url: job.url,
      description,
      scraped_at: new Date().toISOString(),
    };

    try {
      const res = await fetch(webhookUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      // Mark as sent only after a successful POST.
      sentSet.add(job.job_key);
      await chrome.storage.local.set({ [DEDUP_KEY]: [...sentSet] });
      sent++;
    } catch (err) {
      console.error(`Webhook POST failed for ${job.job_key}:`, err.message);
      notifyPopup({ status: "error", message: `Webhook failed for "${job.title}": ${err.message}` });
      return;
    }
  }

  notifyPopup({ status: "done", sent, total: jobs.length });
}

// Opens a viewjob tab with openerTabId set (so the browser sends a Referer header),
// waits for job_detail.js to report back, then closes the tab.
function scrapeJobDescription(url, openerTabId) {
  return new Promise((resolve, reject) => {
    chrome.tabs.create({ url, openerTabId, active: false }, (tab) => {
      const tabId = tab.id;

      // Register resolver before the page has a chance to load.
      const jobKeyMatch = url.match(/[?&]jk=([a-f0-9]+)/i);
      const jobKey = jobKeyMatch ? jobKeyMatch[1] : null;

      if (!jobKey) {
        chrome.tabs.remove(tabId).catch(() => {});
        return reject(new Error("Could not parse job_key from URL"));
      }

      const timeout = setTimeout(() => {
        pendingJobs.delete(jobKey);
        chrome.tabs.remove(tabId).catch(() => {});
        reject(new Error(`Timed out waiting for description of ${jobKey}`));
      }, 20000);

      pendingJobs.set(jobKey, (message) => {
        clearTimeout(timeout);
        chrome.tabs.remove(tabId).catch(() => {});
        if (message.type === "JOB_DESCRIPTION_ERROR") {
          reject(new Error(message.error));
        } else {
          resolve(message.description);
        }
      });
    });
  });
}

function notifyPopup(data) {
  // Best-effort — popup may not be open.
  chrome.runtime.sendMessage({ type: "SCRAPE_STATUS", ...data }).catch(() => {});
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
