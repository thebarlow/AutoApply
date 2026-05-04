const _IS_SEARCH = location.hostname === "www.indeed.com";
const _IS_SAVED = location.hostname === "myjobs.indeed.com";

if (_IS_SEARCH || _IS_SAVED) {
  registerSource({
    cardSelector: _IS_SEARCH
      ? ".job_seen_beacon"
      : "div.atw-AppCard[data-jobkey]",

    getJobData(card) {
      if (_IS_SEARCH) {
        const anchor = card.querySelector("h2.jobTitle a, .jobTitle a");
        const rawUrl = anchor ? new URL(anchor.href, window.location.href).href : "";
        const jkMatch = rawUrl.match(/[?&]jk=([a-f0-9]+)/i);
        const job_key = jkMatch ? `indeed_${jkMatch[1]}` : `indeed_${Date.now()}`;
        const title = anchor?.innerText?.trim() ?? "";
        const company = card.querySelector(
          ".companyName, [data-testid='company-name']"
        )?.innerText?.trim() ?? "";
        const jobLocation = card.querySelector(
          ".companyLocation, [data-testid='text-location']"
        )?.innerText?.trim() ?? "";
        return { source: "indeed", job_key, title, company, location: jobLocation, url: rawUrl };
      } else {
        // myjobs.indeed.com — same DOM as retired extension
        const jobKey = card.getAttribute("data-jobkey") ?? "";
        const anchor = card.querySelector("a.atw-JobInfo-jobTitle");
        const title = anchor?.innerText?.trim() ?? "";
        const url = anchor?.href ?? "";
        const spans = card.querySelectorAll(".atw-JobInfo-companyLocation span");
        const company = spans[0]?.innerText?.trim() ?? "";
        const jobLocation = spans[1]?.innerText?.trim() ?? "";
        return { source: "indeed", job_key: `indeed_${jobKey}`, title, company, location: jobLocation, url };
      }
    },

    getDescription() {
      return document.querySelector("#jobDescriptionText")?.innerText?.trim() ?? "";
    },

    clickCard(card) {
      if (_IS_SEARCH) {
        card.querySelector("h2.jobTitle a, .jobTitle a")?.click();
      } else {
        card.querySelector("a.atw-JobInfo-jobTitle")?.click();
      }
    },

    detailReadySelector: "#jobDescriptionText",

    bookmarkCard: _IS_SEARCH
      ? (card) => {
          const btn = card.querySelector(
            "button[aria-label*='save'], button[aria-label*='Save'], .jobsearch-SaveJobButton"
          );
          btn?.click();
        }
      : null,
  });
}
