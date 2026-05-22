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

  if (message.type === "REGISTER_JOB_TAB") {
    const { jobTabs = {} } = await chrome.storage.session.get("jobTabs");
    jobTabs[sender.tab.id] = message.job_key;
    await chrome.storage.session.set({ jobTabs });
    sendResponse({ ok: true });
    return;
  }

  if (message.type === "GET_JOB_KEY") {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    const tabId = tabs[0]?.id;
    const { jobTabs = {} } = await chrome.storage.session.get("jobTabs");
    sendResponse({ job_key: jobTabs[tabId] ?? null });
    return;
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

chrome.webNavigation.onCreatedNavigationTarget.addListener(async ({ sourceTabId, tabId }) => {
  const { jobTabs = {} } = await chrome.storage.session.get("jobTabs");
  if (jobTabs[sourceTabId]) {
    jobTabs[tabId] = jobTabs[sourceTabId];
    await chrome.storage.session.set({ jobTabs });
  }
});

chrome.tabs.onRemoved.addListener(async (tabId) => {
  const { jobTabs = {} } = await chrome.storage.session.get("jobTabs");
  delete jobTabs[tabId];
  await chrome.storage.session.set({ jobTabs });
});
