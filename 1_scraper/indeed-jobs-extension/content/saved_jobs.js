// Runs on myjobs.indeed.com — scrapes the Saved Jobs tab.
// Responds to GET_JOBS messages from the service worker.

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type !== "GET_JOBS") return;

  const cards = document.querySelectorAll("div.atw-AppCard[data-jobkey]");
  const jobs = [];

  for (const card of cards) {
    const jobKey = card.getAttribute("data-jobkey");

    const titleAnchor = card.querySelector("a.atw-JobInfo-jobTitle");
    // Strip the hidden accessibility span from the title text
    const hiddenSpan = titleAnchor?.querySelector("span");
    if (hiddenSpan) hiddenSpan.remove();
    const title = titleAnchor?.textContent?.trim() ?? "";

    const locationSpans = card.querySelectorAll(
      ".atw-JobInfo-companyLocation span"
    );
    const company = locationSpans[0]?.textContent?.trim() ?? "";
    const location = locationSpans[1]?.textContent?.trim() ?? "";

    const url = titleAnchor?.href ?? "";

    if (jobKey && title) {
      jobs.push({ job_key: jobKey, title, company, location, url });
    }
  }

  sendResponse({ jobs });
});
