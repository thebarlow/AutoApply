const _IS_VIEW   = /^\/jobs\/view\//.test(location.pathname);
const _IS_SEARCH = !_IS_VIEW && /^\/jobs\//.test(location.pathname);
const _IS_SAVED  = /^\/my-items\/saved-jobs/.test(location.pathname);

if (_IS_VIEW) {
  registerViewSource({
    detailReadySelector: '.jobs-description__content, #job-details, .jobs-description-content__text',

    getJobData() {
      const jobIdMatch = location.pathname.match(/\/view\/(\d+)/);
      const job_key = jobIdMatch ? `linkedin_${jobIdMatch[1]}` : `linkedin_${Date.now()}`;
      const url = location.href.split('?')[0];
      const title = document.querySelector(
        'h1.job-details-jobs-unified-top-card__job-title, h1.jobs-unified-top-card__title, h1'
      )?.innerText?.trim() ?? '';
      const company = document.querySelector(
        '.job-details-jobs-unified-top-card__company-name a, .jobs-unified-top-card__company-name a, .jobs-unified-top-card__subtitle-link'
      )?.innerText?.trim() ?? '';
      const jobLocation = document.querySelector(
        '.job-details-jobs-unified-top-card__bullet, .jobs-unified-top-card__bullet'
      )?.innerText?.trim() ?? '';
      return { source: 'linkedin', job_key, title, company, location: jobLocation, url };
    },

    getDescription() {
      return document.querySelector(
        '.jobs-description__content .jobs-box__html-content, #job-details, .jobs-description-content__text'
      )?.innerText?.trim() ?? '';
    },
  });
}

if (_IS_SEARCH || _IS_SAVED) {
  registerSource({
    // LinkedIn replaced stable class names with hashed tokens.
    // componentkey="job-card-component-ref-{jobId}" is the only stable hook on search cards.
    cardSelector: _IS_SEARCH
      ? "[componentkey^='job-card-component-ref']"
      : ".entity-result",

    getJobData(card) {
      // Job ID lives in the componentkey attribute; URL is constructable from it.
      const componentKey = card.getAttribute("componentkey") ?? "";
      const jobIdMatch = componentKey.match(/job-card-component-ref-(\d+)/);
      const jobId = jobIdMatch?.[1] ?? null;
      const job_key = jobId ? `linkedin_${jobId}` : `linkedin_${Date.now()}`;
      const url = jobId ? `https://www.linkedin.com/jobs/view/${jobId}/` : "";

      // Title: dismiss button carries a stable aria-label "Dismiss {title} job".
      const dismissBtn = card.querySelector('button[aria-label^="Dismiss"]');
      const title = (dismissBtn?.getAttribute("aria-label") ?? "")
        .replace(/^Dismiss\s+/i, "")
        .replace(/\s+job$/i, "")
        .trim();

      // Company/location: no stable selectors; grab visible <p> text in order.
      // Paragraphs[0] = title text (skip), [1] = company, [2] = location.
      const paragraphs = [...card.querySelectorAll("p")]
        .map((p) => {
          // Prefer aria-hidden span (visual text) over screen-reader span to avoid duplication.
          const visual = p.querySelector("[aria-hidden='true']");
          return (visual ?? p).innerText?.trim() ?? "";
        })
        .filter((t) => t.length > 1 && !/^[\s·•]+$/.test(t));
      const company = paragraphs[1] ?? "";
      const jobLocation = paragraphs[2] ?? "";

      return { source: "linkedin", job_key, title, company, location: jobLocation, url };
    },

    getDescription() {
      return document.querySelector(
        ".jobs-description__content .jobs-box__html-content, #job-details, .jobs-description-content__text"
      )?.innerText?.trim() ?? "";
    },

    clickCard(card) {
      card.click();
    },

    detailReadySelector: ".jobs-description__content, #job-details, .jobs-description-content__text",

    bookmarkCard: null,
  });
}
