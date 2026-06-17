// browser-extension/background/service_worker.js
importScripts("../lib/browser_shim.js");

const SERVER = "https://autoapply.matthewbarlow.me";
const DEDUP_KEY = "stagedJobKeys";
const TOKEN_KEY = "extToken";

xb.runtime.onMessage.addListener((message, sender, sendResponse) => {
  handleMessage(message, sender, sendResponse);
  return true;
});

async function handleMessage(message, sender, sendResponse) {
  if (message.type === "CHECK_DEDUP") {
    const { [DEDUP_KEY]: keys = [] } = await xb.storage.local.get(DEDUP_KEY);
    sendResponse({ isDuplicate: keys.includes(message.job_key) });
    return;
  }
  if (message.type === "SCRAPE_JOB") {
    try {
      sendResponse(await handleScrape(message.payload));
    } catch (err) {
      sendResponse({ ok: false, error: err.message });
    }
  }
}

async function handleScrape(payload) {
  const { [DEDUP_KEY]: keys = [] } = await xb.storage.local.get(DEDUP_KEY);
  const keySet = new Set(keys);
  if (keySet.has(payload.job_key)) return { ok: true, status: "duplicate" };

  const { [TOKEN_KEY]: token } = await xb.storage.local.get(TOKEN_KEY);
  if (!token) return { ok: false, error: "no_account" };

  const res = await fetch(`${SERVER}/api/scraper/stage-job`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(payload),
  });

  if (res.status === 401) return { ok: false, error: "no_account" };
  if (!res.ok) throw new Error(`HTTP ${res.status}`);

  const data = await res.json();
  keySet.add(payload.job_key);
  await xb.storage.local.set({ [DEDUP_KEY]: [...keySet] });
  return { ok: true, status: data.status };
}
