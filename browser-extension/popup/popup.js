const urlInput = document.getElementById("fastapi-url");
const btnSave = document.getElementById("btn-save");
const btnClear = document.getElementById("btn-clear");
const countEl = document.getElementById("count");
const msgEl = document.getElementById("msg");

async function load() {
  const { fastapiUrl = "http://localhost:8000" } = await chrome.storage.sync.get("fastapiUrl");
  urlInput.value = fastapiUrl;
  const { stagedJobKeys = [] } = await chrome.storage.local.get("stagedJobKeys");
  countEl.textContent = stagedJobKeys.length;
}

btnSave.addEventListener("click", async () => {
  const url = urlInput.value.trim();
  if (!url) { showMsg("Enter a URL.", "red"); return; }
  await chrome.storage.sync.set({ fastapiUrl: url });
  showMsg("Saved.");
});

btnClear.addEventListener("click", async () => {
  await chrome.storage.local.set({ stagedJobKeys: [] });
  countEl.textContent = "0";
  showMsg("History cleared.");
});

function showMsg(text, color = "green") {
  msgEl.style.color = color;
  msgEl.textContent = text;
  setTimeout(() => { msgEl.textContent = ""; }, 3000);
}

load();
