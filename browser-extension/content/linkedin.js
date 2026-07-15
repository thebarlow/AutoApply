const _IS_VIEW   = /^\/jobs\/view\//.test(location.pathname);
const _IS_SEARCH = !_IS_VIEW && /^\/jobs\//.test(location.pathname);
const _IS_SAVED  = /^\/my-items\/saved-jobs/.test(location.pathname);

// LinkedIn fully hashes class names and IDs, so locate the description by the
// "About the job" header text and walk up to a container with enough body text.
const _ABOUT_RE = /^\s*about the job\s*$/i;

function _findAboutHeader() {
  const candidates = document.querySelectorAll('h1, h2, h3, h4, h5, h6, strong, span, div');
  for (const el of candidates) {
    if (_ABOUT_RE.test(el.innerText || '')) return el;
  }
  return null;
}

function _findDescriptionContainer() {
  const header = _findAboutHeader();
  if (!header) return null;
  // Walk up until the ancestor contains substantially more text than the header alone.
  let node = header;
  for (let i = 0; i < 8 && node; i++) {
    const len = (node.innerText || '').length;
    if (len > 400) return node;
    node = node.parentElement;
  }
  return node;
}

let _lastSeenContainer = null;

function _markStale() {
  _lastSeenContainer = _findDescriptionContainer();
}

function _isDetailReady() {
  const c = _findDescriptionContainer();
  if (!c) return false;
  if ((c.innerText || '').length <= 400) return false;
  // After clicking a different card we want the container element to differ
  // from the one that was on screen at click-time.
  if (_lastSeenContainer && c === _lastSeenContainer) return false;
  return true;
}

function _getDescriptionText() {
  return _findDescriptionContainer()?.innerText?.trim() ?? '';
}

if (_IS_VIEW) {
  registerViewSource({
    isDetailReady: _isDetailReady,

    getJobData() {
      const jobIdMatch = location.pathname.match(/\/view\/(\d+)/);
      const job_key = jobIdMatch ? `linkedin_${jobIdMatch[1]}` : `linkedin_${Date.now()}`;
      const url = location.href.split('?')[0];
      const title = document.querySelector('h1')?.innerText?.trim() ?? '';
      // Company/location have no stable selectors on the view page either;
      // best effort: dismiss button aria-labels often include them, otherwise blank.
      return { source: 'linkedin', job_key, title, company: '', location: '', url };
    },

    getDescription: _getDescriptionText,
  });
}

if (_IS_SEARCH || _IS_SAVED) {
  registerSource({
    // componentkey="job-card-component-ref-{jobId}" remains stable on search cards.
    cardSelector: _IS_SEARCH
      ? "[componentkey^='job-card-component-ref']"
      : ".entity-result",

    getJobData(card) {
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

      // Company/location: positional <p> order — paragraphs[1]=company, [2]=location.
      const paragraphs = [...card.querySelectorAll("p")]
        .map((p) => {
          const visual = p.querySelector("[aria-hidden='true']");
          return (visual ?? p).innerText?.trim() ?? "";
        })
        .filter((t) => t.length > 1 && !/^[\s·•]+$/.test(t));
      const company = paragraphs[1] ?? "";
      const jobLocation = paragraphs[2] ?? "";

      return { source: "linkedin", job_key, title, company, location: jobLocation, url };
    },

    getDescription: _getDescriptionText,

    clickCard(card) {
      // If this card is already the selected one, the pane won't re-render a
      // new container node — drop the identity check so readiness can pass.
      const jobId = (card.getAttribute("componentkey") ?? "")
        .match(/job-card-component-ref-(\d+)/)?.[1];
      const selected = new URLSearchParams(location.search).get("currentJobId");
      if (jobId && jobId === selected) _lastSeenContainer = null;
      card.click();
    },

    isDetailReady: _isDetailReady,
    markStale: _markStale,

    bookmarkCard: null,
  });
}
