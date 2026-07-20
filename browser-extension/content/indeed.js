const _IS_SEARCH = location.hostname === "www.indeed.com";
const _IS_SAVED = location.hostname === "myjobs.indeed.com";

// Description container selectors, most-current first. Indeed rotates its
// detail-pane DOM; `.simple-job-description-html` is the react-native layout,
// `#jobDescriptionText` is the legacy container kept as a fallback.
const _DESCRIPTION_SELECTORS = [
  ".simple-job-description-html",
  "#jobDescriptionText",
];

// First matching description container, most-current layout first.
function _findDescriptionEl() {
  for (const sel of _DESCRIPTION_SELECTORS) {
    const el = document.querySelector(sel);
    if (el) return el;
  }
  return null;
}

// Extract clean description text from a container. Indeed embeds `<style>`
// blocks (`@layer htmlContent {…}`) INSIDE the description container. When the
// element is fully laid out those `<style>` nodes are `display:none`, so
// `innerText` excludes them — but if we read before the pane is painted,
// `innerText` falls back to `textContent` and splices the raw CSS into the
// description. Strip `style`/`script` from a clone so the result is clean
// regardless of render timing.
function _extractDescription(el) {
  if (!el) return "";
  const clone = el.cloneNode(true);
  clone.querySelectorAll("style, script").forEach((n) => n.remove());
  return (clone.textContent || "").trim();
}

// Indeed's search page opens a detail pane that persists across card clicks and
// is REPLACED (new node) when a different job loads. Without this guard,
// `_waitForReady` sees the previous job's pane still present and resolves
// immediately, so a repeat scrape reads the PRIOR job's description. Mirror the
// LinkedIn approach: remember the container at click-time and only report ready
// once a different, populated container has mounted.
let _lastSeenContainer = null;

function _markStale() {
  _lastSeenContainer = _findDescriptionEl();
}

function _isDetailReady() {
  const el = _findDescriptionEl();
  if (!el) return false;
  // Measure the CSS-stripped description so a container holding only Indeed's
  // injected `<style>` blocks (transient, pre-render) isn't mistaken for ready.
  if (_extractDescription(el).length <= 100) return false;
  if (_lastSeenContainer && el === _lastSeenContainer) return false;
  return true;
}

function getApplyInfo() {
  const buttons = Array.from(document.querySelectorAll('button, a'));
  const companySite = buttons.find(b => /apply on company site/i.test(b.textContent || ''));
  if (companySite) {
    const href = companySite.tagName === 'A' ? companySite.href : '';
    return { easy_apply: false, apply_url_raw: href || '' };
  }
  const applyNow = buttons.find(b => /apply now|apply\b/i.test(b.textContent || ''));
  return { easy_apply: applyNow ? true : null, apply_url_raw: '' };
}

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
      return _extractDescription(_findDescriptionEl());
    },
    getApplyInfo,

    clickCard(card) {
      if (_IS_SEARCH) {
        card.querySelector("h2.jobTitle a, .jobTitle a")?.click();
      } else {
        card.querySelector("a.atw-JobInfo-jobTitle")?.click();
      }
    },

    isDetailReady: _isDetailReady,
    markStale: _markStale,
    detailReadySelector: _DESCRIPTION_SELECTORS.join(", "),

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
