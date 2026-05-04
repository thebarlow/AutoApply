const _IS_SEARCH = /^\/jobs\//.test(location.pathname);
const _IS_SAVED = /^\/my-items\/saved-jobs/.test(location.pathname);

if (_IS_SEARCH || _IS_SAVED) {
  registerSource({
    cardSelector: _IS_SEARCH
      ? ".scaffold-layout__list-item"
      : ".entity-result",

    getJobData(card) {
      const anchor = card.querySelector(
        "a.job-card-list__title--link, a.job-card-container__link, .entity-result__title-text a"
      );
      const rawUrl = anchor?.href ?? "";
      const url = rawUrl.split("?")[0];
      const jobIdMatch = url.match(/\/view\/(\d+)/);
      const job_key = jobIdMatch
        ? `linkedin_${jobIdMatch[1]}`
        : `linkedin_${Date.now()}`;
      const title = anchor?.innerText?.trim() ?? "";
      const company = card.querySelector(
        ".job-card-container__primary-description, .artdeco-entity-lockup__subtitle, .entity-result__primary-subtitle"
      )?.innerText?.trim() ?? "";
      const jobLocation = card.querySelector(
        ".artdeco-entity-lockup__caption li, .entity-result__secondary-subtitle"
      )?.innerText?.trim() ?? "";
      return { source: "linkedin", job_key, title, company, location: jobLocation, url };
    },

    getDescription() {
      return document.querySelector(
        ".jobs-description__content .jobs-box__html-content, #job-details, .jobs-description-content__text"
      )?.innerText?.trim() ?? "";
    },

    clickCard(card) {
      const anchor = card.querySelector(
        "a.job-card-list__title--link, a.job-card-container__link, .entity-result__title-text a"
      );
      anchor?.click();
    },

    detailReadySelector: ".jobs-description__content, #job-details, .jobs-description-content__text",

    bookmarkCard: _IS_SEARCH
      ? (card) => {
          const btn = card.querySelector(
            "button.jobs-save-button, button[aria-label*='Save job'], button[aria-label*='save job']"
          );
          btn?.click();
        }
      : null,
  });
}
