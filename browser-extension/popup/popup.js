const urlInput = document.getElementById("fastapi-url");
const btnSave = document.getElementById("btn-save");
const btnClear = document.getElementById("btn-clear");
const countEl = document.getElementById("count");
const msgEl = document.getElementById("msg");
const applyJobLabel = document.getElementById("apply-job-label");
const applyStatus = document.getElementById("apply-status");
const btnResume = document.getElementById("btn-resume");
const btnCover = document.getElementById("btn-cover");

async function load() {
  const { fastapiUrl = "http://localhost:8080" } = await chrome.storage.sync.get("fastapiUrl");
  urlInput.value = fastapiUrl;
  const { stagedJobKeys = [] } = await chrome.storage.local.get("stagedJobKeys");
  countEl.textContent = stagedJobKeys.length;
  await loadApplySection(fastapiUrl);
}

async function loadApplySection(fastapiUrl) {
  let job_key = null;
  try {
    const resp = await chrome.runtime.sendMessage({ type: "GET_JOB_KEY" });
    job_key = resp?.job_key ?? null;
  } catch (_) {}

  if (!job_key) {
    applyStatus.textContent = "No job associated with this tab. Open a job posting from the dashboard.";
    return;
  }

  let job = null;
  try {
    const res = await fetch(`${fastapiUrl}/api/jobs/${encodeURIComponent(job_key)}`);
    if (!res.ok) throw new Error("not found");
    job = await res.json();
  } catch (_) {
    applyStatus.textContent = "Could not reach local server.";
    return;
  }

  applyJobLabel.textContent = `Apply — ${job.title} @ ${job.company}`;
  applyStatus.textContent = "";

  if (job.resume_path) {
    btnResume.disabled = false;
    btnResume.addEventListener("click", () => triggerUpload(job_key, "resume", fastapiUrl));
  } else {
    btnResume.title = "Generate resume first";
  }

  if (job.cover_path) {
    btnCover.disabled = false;
    btnCover.addEventListener("click", () => triggerUpload(job_key, "cover", fastapiUrl));
  } else {
    btnCover.title = "Generate cover letter first";
  }
}

async function triggerUpload(job_key, file_type, fastapiUrl) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const isFirefox = typeof browser !== "undefined";

  if (isFirefox) {
    // Firefox: inject into all frames, clicks input to open OS dialog, then native host fills it
    await (browser.scripting || chrome.scripting).executeScript({
      target: { tabId: tab.id, allFrames: true },
      func: clickFileInput,
      args: [file_type],
    });
    const result = await chrome.runtime.sendMessage({ type: "NATIVE_UPLOAD", job_key, file_type });
    if (!result?.ok) {
      const messages = {
        file_not_found: "PDF not found. Regenerate from the dashboard.",
        dialog_timeout: "File dialog did not open in time. Try again.",
        native_host_disconnected: "Native host not installed. Run native-host/setup.bat to enable Firefox uploads.",
      };
      showMsg(messages[result?.error] || "Upload failed.", "red");
    }
  } else {
    // Chrome: inject into all frames, DataTransfer sets file directly
    await chrome.scripting.executeScript({
      target: { tabId: tab.id, allFrames: true },
      func: injectFileChrome,
      args: [{ job_key, file_type, fastapiUrl }],
    });
  }
}

// Injected into page on Firefox — clicks the file input to open OS dialog
function clickFileInput(file_type) {
  const keyword = file_type === "resume" ? "resume" : "cover";

  function findInput() {
    const inputs = [...document.querySelectorAll('input[type="file"]')];
    return inputs.find(el => {
      const label =
        el.closest("label")?.textContent ||
        document.querySelector(`label[for="${el.id}"]`)?.textContent ||
        el.getAttribute("aria-label") || "";
      return label.toLowerCase().includes(keyword);
    }) || inputs.find(el => /pdf|doc/i.test(el.accept || "")) || (inputs.length === 1 ? inputs[0] : null);
  }

  const inputs = [...document.querySelectorAll('input[type="file"]')];
  if (inputs.length === 0) return;
  const input = inputs.find(el => {
    const label =
      el.closest("label")?.textContent ||
      document.querySelector(`label[for="${el.id}"]`)?.textContent ||
      el.getAttribute("aria-label") || "";
    return label.toLowerCase().includes(keyword);
  }) || inputs.find(el => /pdf|doc/i.test(el.accept || "")) || (inputs.length === 1 ? inputs[0] : null);
  if (!input) {
    const banner = document.createElement("div");
    banner.style.cssText = "position:fixed;top:0;left:0;right:0;background:#e53935;color:#fff;padding:10px;font-size:14px;z-index:99999;text-align:center;";
    banner.textContent = "No upload field found — scroll to the upload section and try again.";
    document.body.prepend(banner);
    setTimeout(() => banner.remove(), 5000);
    return;
  }
  input.click();
}

// Injected into page on Chrome — uses DataTransfer to set file directly
async function injectFileChrome({ job_key, file_type, fastapiUrl }) {
  const keyword = file_type === "resume" ? "resume" : "cover";

  const inputs = [...document.querySelectorAll('input[type="file"]')];
  if (inputs.length === 0) return;
  const input = inputs.find(el => {
    const label =
      el.closest("label")?.textContent ||
      document.querySelector(`label[for="${el.id}"]`)?.textContent ||
      el.getAttribute("aria-label") || "";
    return label.toLowerCase().includes(keyword);
  }) || inputs.find(el => /pdf|doc/i.test(el.accept || "")) || (inputs.length === 1 ? inputs[0] : null);
  if (!input) {
    const banner = document.createElement("div");
    banner.style.cssText = "position:fixed;top:0;left:0;right:0;background:#e53935;color:#fff;padding:10px;font-size:14px;z-index:99999;text-align:center;";
    banner.textContent = "No upload field found — scroll to the upload section and try again.";
    document.body.prepend(banner);
    setTimeout(() => banner.remove(), 5000);
    return;
  }

  const endpoint = file_type === "resume"
    ? `${fastapiUrl}/api/jobs/${job_key}/resume`
    : `${fastapiUrl}/api/jobs/${job_key}/cover`;

  const blob = await fetch(endpoint).then(r => r.blob());
  const file = new File([blob], `${file_type}.pdf`, { type: "application/pdf" });
  const dt = new DataTransfer();
  dt.items.add(file);
  input.files = dt.files;
  input.dispatchEvent(new Event("change", { bubbles: true }));
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
