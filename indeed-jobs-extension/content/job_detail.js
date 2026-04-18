// Runs on indeed.com/viewjob* — scrapes the job description.
// Waits for the description element to appear, then messages the service worker.

const JOB_KEY_RE = /[?&]jk=([a-f0-9]+)/i;

function getJobKey() {
  const match = window.location.search.match(JOB_KEY_RE);
  return match ? match[1] : null;
}

function tryExtract() {
  const el = document.querySelector("#jobDescriptionText");
  if (!el) return null;
  return el.innerText.trim();
}

function waitForDescription(maxWaitMs = 10000) {
  return new Promise((resolve, reject) => {
    const description = tryExtract();
    if (description) {
      resolve(description);
      return;
    }

    const observer = new MutationObserver(() => {
      const text = tryExtract();
      if (text) {
        observer.disconnect();
        clearTimeout(timeout);
        resolve(text);
      }
    });

    observer.observe(document.body, { childList: true, subtree: true });

    const timeout = setTimeout(() => {
      observer.disconnect();
      reject(new Error("Timed out waiting for #jobDescriptionText"));
    }, maxWaitMs);
  });
}

(async () => {
  const jobKey = getJobKey();
  if (!jobKey) return;

  try {
    const description = await waitForDescription();
    chrome.runtime.sendMessage({
      type: "JOB_DESCRIPTION",
      job_key: jobKey,
      description,
    });
  } catch (err) {
    chrome.runtime.sendMessage({
      type: "JOB_DESCRIPTION_ERROR",
      job_key: jobKey,
      error: err.message,
    });
  }
})();
