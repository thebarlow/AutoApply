const DEDUP_KEY = "stagedJobKeys";
const jobTabs = {};

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
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

  if (message.type === "REGISTER_JOB_TAB") {
    jobTabs[sender.tab.id] = message.job_key;
    sendResponse({ ok: true });
    return true;
  }

  if (message.type === "GET_JOB_KEY") {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      const tabId = tabs[0]?.id;
      sendResponse({ job_key: jobTabs[tabId] ?? null });
    });
    return true;
  }

  if (message.type === "NATIVE_UPLOAD") {
    const port = chrome.runtime.connectNative("com.auto_apply.host");
    port.onMessage.addListener((response) => {
      sendResponse(response);
      port.disconnect();
    });
    port.onDisconnect.addListener(() => {
      sendResponse({ ok: false, error: "native_host_disconnected" });
    });
    port.postMessage({ job_key: message.job_key, file_type: message.file_type });
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

chrome.webNavigation.onCreatedNavigationTarget.addListener(({ sourceTabId, tabId }) => {
  if (jobTabs[sourceTabId]) {
    jobTabs[tabId] = jobTabs[sourceTabId];
  }
});

chrome.tabs.onRemoved.addListener((tabId) => {
  delete jobTabs[tabId];
});
