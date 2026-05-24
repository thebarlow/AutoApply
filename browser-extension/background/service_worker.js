const DEDUP_KEY = "stagedJobKeys";

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  handleMessage(message, sender, sendResponse);
  return true;
});

async function handleMessage(message, sender, sendResponse) {
  if (message.type === "CHECK_DEDUP") {
    const { [DEDUP_KEY]: keys = [] } = await chrome.storage.local.get(DEDUP_KEY);
    sendResponse({ isDuplicate: keys.includes(message.job_key) });
    return;
  }

  if (message.type === "SCRAPE_JOB") {
    try {
      const result = await handleScrape(message.payload);
      sendResponse(result);
    } catch (err) {
      sendResponse({ ok: false, error: err.message });
    }
    return;
  }
}

async function handleScrape(payload) {
  const { [DEDUP_KEY]: keys = [] } = await chrome.storage.local.get(DEDUP_KEY);
  const keySet = new Set(keys);

  if (keySet.has(payload.job_key)) {
    return { ok: true, status: "duplicate" };
  }

  const { fastapiUrl = "http://localhost:8080" } = await chrome.storage.sync.get("fastapiUrl");

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
