const btn = document.getElementById("btn-download");
const statusEl = document.getElementById("status");
const optionsLink = document.getElementById("link-options");

optionsLink.addEventListener("click", () => {
  chrome.runtime.openOptionsPage();
});

btn.addEventListener("click", async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

  if (!tab?.url?.includes("myjobs.indeed.com")) {
    setStatus("Navigate to myjobs.indeed.com first.", "error");
    return;
  }

  btn.disabled = true;
  setStatus("Starting…");

  chrome.runtime.sendMessage({ type: "START_SCRAPE", tabId: tab.id });
});

chrome.runtime.onMessage.addListener((message) => {
  if (message.type !== "SCRAPE_STATUS") return;

  switch (message.status) {
    case "scraping_list":
      setStatus("Reading saved jobs…");
      break;

    case "processing":
      setStatus(`Processing ${message.current} of ${message.total}: ${message.title}`);
      break;

    case "done":
      if (message.allDuplicates) {
        setStatus(`All ${message.total} jobs already sent. Clear history in Settings to re-send.`, "done");
      } else {
        setStatus(`Done — ${message.sent} job${message.sent !== 1 ? "s" : ""} sent.`, "done");
      }
      btn.disabled = false;
      break;

    case "error":
      setStatus(message.message, "error");
      btn.disabled = false;
      break;
  }
});

function setStatus(text, cls = "") {
  statusEl.textContent = text;
  statusEl.className = cls;
}
