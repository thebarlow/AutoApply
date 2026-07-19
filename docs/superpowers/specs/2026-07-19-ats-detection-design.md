# ATS Detection & Apply-URL Resolution — Design

**Date:** 2026-07-19
**Status:** Approved (brainstorming complete)
**Sub-project:** 1 of 5 in "Full automation of document submission" (see `.claude/TODO.md`).

## Context

"Full automation of document submission" is decomposed into five sequenced sub-projects:

1. **ATS detection & apply-URL resolution** — *this spec*.
2. Field-mapping engine.
3. Form-fill + submit automation.
4. Credential vault (client-side, encrypted, extension-only).
5. Submission confirmation (auto-mark applied).

This sub-project is the foundation: nothing downstream can fill or submit an application until we
know, per job, whether it is an in-platform ("easy") apply or an external application, and — for
external ones — which ATS (Greenhouse, Lever, Workday, …) hosts the real form. It is also
independently useful now as a per-job label.

**In scope:** LinkedIn and Indeed jobs scraped via the browser extension.
**Out of scope:** the API scrapers (Remotive, RemoteOK) — they are not part of the automation path.

## Goals

- At scrape time, flag each job as `easy_apply` (in-platform) or external.
- For external jobs, resolve the final apply-destination URL (following redirects) and classify the
  hosting ATS by domain, server-side.
- Persist the result on the job and surface a minimal ATS chip in the review queue.
- Do all of this without blocking or slowing the core scrape action.

## Non-goals

- No form filling, submission, credential storage, or confirmation detection (later sub-projects).
- No ATS filtering/sorting in the dashboard yet (only a display chip).
- No new column for the job board — the existing `jobs.source` column already records
  `linkedin`/`indeed`.

## Data flow

1. **Scrape (synchronous).** On Scrape, the source module (`linkedin.js` / `indeed.js`) additionally
   reads the DOM via a new `getApplyInfo()` returning `{ easy_apply, apply_url_raw }`. This is
   included in the existing `POST /api/scraper/stage-job` payload. The job is persisted immediately,
   now carrying `easy_apply` (and `apply_url_raw` if an external link was visible). `ats_type`
   remains null (= unresolved) at this point for external jobs; for easy-apply jobs the server sets
   `ats_type = "easy_apply"`.
2. **Enqueue resolution (only on scrape success).** `stage-job` returns `{ status, job_key }`. Only
   if it succeeds **and** the job is external does `injector.js` enqueue a resolution task keyed to
   that `job_key`. If the scrape POST fails, nothing is enqueued and no apply tab is opened — so a
   resolution PATCH can never target a non-existent job (orphan-PATCH concern resolved by ordering,
   not by merging endpoints).
3. **Resolve (asynchronous, background).** `service_worker.js` runs a small resolution queue
   (concurrency ≤ 2): open the apply destination in a **background tab**, watch `tabs.onUpdated`
   until the redirect chain settles (URL stops changing / load completes, with a timeout), read the
   final URL, close the tab (`tabs.remove`), then `PATCH /api/jobs/{job_key}/ats-resolution` with
   `{ apply_url_resolved }`.
4. **Classify (server).** The PATCH endpoint runs the resolved URL through `core/ats.py`
   `classify_ats(url)`, persists `apply_url_resolved`, `ats_type`, `ats_domain`, and SSE-broadcasts
   the updated job.
5. **Surface (UI).** A small `AtsChip` on the review-queue card reflects `ats_type`.

## Data model

New nullable columns on the `jobs` table (idempotent migration in `init_db.py`, plus an Alembic
migration for hosted Postgres, matching the existing project pattern):

| Column | Type | Meaning |
|---|---|---|
| `easy_apply` | Boolean, nullable | `true` = in-platform apply, `false` = external, `null` = unknown/unscraped |
| `apply_url_raw` | String, nullable | apply link seen in the card DOM before any redirect |
| `apply_url_resolved` | String, nullable | final settled URL after following redirects |
| `ats_type` | String, nullable | classifier output (see below); `null` = external-but-not-yet-resolved |
| `ats_domain` | String, nullable | resolved hostname, retained especially for `other` so it can be eyeballed |

`ats_type` values: `greenhouse`, `lever`, `ashby`, `workday`, `icims`, `taleo`, `smartrecruiters`,
`jobvite`, `bamboohr`, `other`, `easy_apply`. `null` distinctly means "external, resolution pending
or failed."

These fields are added to `Job.serialize()` so the dashboard/SSE payload carries them.

## Classifier — `core/ats.py`

A new module with a pure function:

```python
def classify_ats(url: str) -> tuple[str, str]:
    """Return (ats_type, hostname) for a resolved apply URL."""
```

- No LLM, no network — a domain-signature table matched against the URL's hostname
  (suffix/substring rules, e.g. `boards.greenhouse.io` and `*.greenhouse.io` → `greenhouse`,
  `jobs.lever.co` → `lever`, `*.myworkdayjobs.com` / `*.workday.com` → `workday`,
  `*.icims.com` → `icims`, `*.taleo.net` → `taleo`, `jobs.ashbyhq.com` → `ashby`,
  `*.smartrecruiters.com` → `smartrecruiters`, `*.jobvite.com` → `jobvite`,
  `*.bamboohr.com` → `bamboohr`).
- Unrecognized host → `("other", hostname)`.
- Malformed/empty URL → `("other", "")` (never raises).
- This table is the single source of truth for the recognized-ATS set and the only place to update
  when adding an ATS.

Unit tests over a table of representative real ATS URLs are the highest-value tests in this
sub-project.

## Server endpoint

`PATCH /api/jobs/{job_key}/ats-resolution` in the jobs router.

- Auth: bearer-or-session, tenant-scoped. Resolves `(profile_id, job_key)` — never `job_key` alone,
  since two tenants may have scraped the same posting.
- Body: `{ apply_url_resolved: str }`.
- Behavior: classify via `core/ats.py`, persist `apply_url_resolved` + `ats_type` + `ats_domain`,
  SSE-broadcast the updated job, return the updated fields.
- Kept separate from the existing state PATCH so the concerns stay clean; the orphan risk is handled
  by enqueue ordering (see Data flow #2), not by merging.
- 404 if the `(profile_id, job_key)` row does not exist.

`stage-job` is extended to accept and persist `easy_apply` and `apply_url_raw`, and to set
`ats_type = "easy_apply"` when `easy_apply` is true. The `StageJobRequest` schema and `ScrapedJob`
dataclass gain the two optional fields.

## Extension changes

- `manifest.json`: add the `"tabs"` permission.
- `linkedin.js` / `indeed.js`: add `getApplyInfo()` → `{ easy_apply, apply_url_raw }`. DOM-based and
  selector-fragile like the rest of the extension; documented as such in
  `browser-extension/CONTEXT.md`. (LinkedIn: native "Easy Apply" button vs. external "Apply";
  Indeed: "Apply now" (Indeed-hosted) vs. "Apply on company site".)
- `injector.js`: include the apply info in the scrape payload; on a successful `stage-job` response
  for an external job, enqueue a resolution task with the returned `job_key`.
- `service_worker.js`: a resolution queue that opens a background tab, waits for the redirect chain
  to settle (with a timeout and a stale-guard), reads the final URL, closes the tab, and PATCHes the
  result with the stored bearer token. Concurrency ≤ 2 so rapid scraping does not spawn a swarm of
  tabs.

Selector fragility here is the motivation for the separately-tracked "Browser-extension DOM
recalibration tool" backlog item.

## UI

A single `AtsChip` component on the review-queue job card, driven by `ats_type`:

- `easy_apply` → grey "Easy Apply".
- a recognized ATS → coloured chip with the ATS name.
- `other` → neutral chip labeled with the domain (or just "External").
- `null` on an external job → "Resolving…" placeholder.

No filtering or sorting in this sub-project.

## Testing

- **`core/ats.py`** — unit tests: table of real ATS URLs → expected `(ats_type, hostname)`;
  malformed URLs; `other` fallback. Highest-value tests.
- **Server** — `PATCH /ats-resolution` persists + classifies + tenant-scopes (cross-tenant PATCH
  cannot touch another tenant's row); 404 on missing job; `stage-job` persists `easy_apply` /
  `apply_url_raw` and sets `easy_apply` → `ats_type`.
- **Migration** — idempotency (running `init_db.py` twice is a no-op; columns nullable so existing
  rows are unaffected).
- **Extension DOM parsing** — manual smoke test, consistent with the existing extension testing
  posture (selectors are not unit-tested).

## Open risks / accepted limitations

- **Selector fragility** — `getApplyInfo()` adds one more DOM read that can break on a
  LinkedIn/Indeed redesign. Fails gracefully (job still scrapes; `easy_apply` = null). Mitigated
  long-term by the recalibration-tool backlog item.
- **Resolution failure** — a redirect that never settles, requires login, or times out leaves
  `ats_type = null` on an external job. Acceptable: the job is still usable; resolution can be
  retried in a later pass. (A manual "re-resolve" affordance is out of scope here.)
- **Background-tab UX** — opening/closing tabs is mostly invisible but not entirely; the ≤ 2
  concurrency guard bounds the disruption.
