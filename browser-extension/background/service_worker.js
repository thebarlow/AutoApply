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
