const webhookInput = document.getElementById("webhook-url");
const btnSave = document.getElementById("btn-save");
const btnClear = document.getElementById("btn-clear");
const msgEl = document.getElementById("msg");
const dedupCount = document.getElementById("dedup-count");

async function load() {
  const { webhookUrl = "" } = await chrome.storage.sync.get("webhookUrl");
  webhookInput.value = webhookUrl;
  await refreshDedupCount();
}

async function refreshDedupCount() {
  const { sentJobKeys = [] } = await chrome.storage.local.get("sentJobKeys");
  dedupCount.textContent = ` (${sentJobKeys.length} job${sentJobKeys.length !== 1 ? "s" : ""} on record)`;
}

btnSave.addEventListener("click", async () => {
  const url = webhookInput.value.trim();
  if (!url) {
    showMsg("Enter a webhook URL.", "error");
    return;
  }
  await chrome.storage.sync.set({ webhookUrl: url });
  showMsg("Saved.");
});

btnClear.addEventListener("click", async () => {
  await chrome.storage.local.set({ sentJobKeys: [] });
  await refreshDedupCount();
  showMsg("History cleared.");
});

function showMsg(text, cls = "") {
  msgEl.textContent = text;
  msgEl.className = cls;
  setTimeout(() => { msgEl.textContent = ""; }, 3000);
}

load();
