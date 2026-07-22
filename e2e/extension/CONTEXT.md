# e2e/extension — Extension Autofill Harness

Playwright harness that drives the real unpacked browser extension against
captured static ATS fixtures to prove the field-mapping engine + `form_fill.js`
writer round-trip end to end: enumerate → `/application-plan` → fill. Separate
from `e2e/` (dashboard smoke) — different Playwright project, no Vite, talks to
the backend directly.

## What it does

`tests/autofill.spec.ts` is parametrized over three ATS cases (greenhouse,
lever, ashby). For each case it:

1. Dev-logs in (`POST /api/dev/login`) and PUTs a minimal profile
   (`first_name`/`last_name`/`email`) onto that account so the plan resolver
   has source data to fill with.
2. Seeds a staged job via `POST /api/dev/seed-ats-job` (`job_key`,
   `apply_url`, `ats_type`).
3. Writes `serverMode: 'local'` and `stagedJobMeta` directly into
   `chrome.storage.local` via the service worker, so the SW targets
   `localhost:8080` and can match the fixture's URL back to the seeded job.
   These are the real storage keys `background/service_worker.js` reads.
4. Routes the real ATS host (`context.route('https://<host>/**', ...)`) to
   the corresponding static fixture in `fixtures/*.html` instead of hitting
   the live site.
5. Navigates a new page to the (routed) apply URL, screenshots "before",
   waits for the email field to become non-empty (proof the injector →
   enumerate → plan → fill pipeline ran), screenshots "after", and asserts
   the email value is non-empty.

## Loading the extension

`fixtures.ts` launches a **persistent context** (`chromium.launchPersistentContext`)
in **headed** mode with `--load-extension`/`--disable-extensions-except`
pointed at `browser-extension/` — MV3 extensions require a real (non-headless)
persistent context; there is no headless equivalent. The service-worker
fixture waits for `context.serviceWorkers()` (or the `serviceworker` event) to
get a handle for `evaluate()`-ing storage writes directly into the SW's
context.

## Storage-key seeding

The spec pokes `chrome.storage.local` directly rather than going through the
extension's own UI flow, because there's no popup/staging UI to drive in this
harness:

- `serverMode: 'local'` — tells the SW to call `localhost:8080` instead of the
  hosted origin.
- `stagedJobMeta: { [jobKey]: { apply_url_raw, apply_url_resolved } }` — lets
  the SW resolve an incoming page URL back to a `job_key` it can ask the
  backend for a plan for.

If these key names drift in `background/service_worker.js`, the spec's
`serviceWorker.evaluate()` call must be updated to match — the fixture reads
the literal strings, not a shared constant.

## Canonical-fields-only fixtures ⇒ no LLM

Each `fixtures/*.html` intentionally includes **only** the ATS's canonical
static-schema fields (name/email/phone/location/links) and omits any
free-text essay/custom questions. That keeps `needs_essay_pass()` false for
every fixture, so `map_fields` is never metered and no LLM call happens during
these runs — the harness proves the deterministic mapping + write path only.
See `core/application_mapper.py::needs_essay_pass` and
`core/CONTEXT.md` → "Field-mapping engine" for the metering rule.

## Adding a new ATS fixture

1. Capture a real apply-page's HTML (scripts/styles stripped, structural
   markup kept) into `fixtures/<ats>.html`; add a header comment noting the
   source, capture date, and any field-naming quirks (id vs name, controlled
   inputs, etc.) — see the existing three fixtures for the pattern.
2. Add a `SchemaField` entry set to `core/ats_schemas.py::STATIC_SCHEMAS` if
   the ATS is new — **the schema's `field_id` values must equal the live
   DOM's `name`/`id` attributes**, not a generic placeholder. `form_fill.js`
   looks fields up by `[name="<field_id>"]` / `getElementById(field_id)`, so a
   mismatch here silently leaves the field unfilled (see the Ashby gap fixed
   in this task — the static schema originally used `"email"` when the live
   DOM field is `name="_systemfield_email"`).
3. Add a `content_scripts` match + `host_permissions` entry in
   `browser-extension/manifest.json` for the ATS's domain if not already
   present.
4. Add a case object to the `CASES` array in `tests/autofill.spec.ts` (own
   `ats`, `host`, `applyUrl`, `jobKey`, `fixture`, `emailSelector`) — the loop
   handles seeding/routing/asserting/screenshotting generically.

## Known limitations

- **Single-page forms only.** No multi-step/wizard ATS flows are exercised;
  the harness assumes the whole canonical form is present on first load.
- Only the email field is asserted per ATS (the one canonical field every
  static schema guarantees). Fields the dynamic classifier can't map by exact
  `field_id` (e.g. an enumerated field whose live `name` doesn't match a
  `CANONICAL_FIELDS` key) are a classifier gap, not a harness bug — see
  `browser-extension/CONTEXT.md` for currently-known per-ATS field gaps.
- Screenshots (`screenshots/*.png`) are gitignored — regenerate by running the
  suite; they are not committed artifacts.
- No submit is ever attempted; no essay/LLM path is exercised (by design, see
  above).

## Running

Needs headed Chromium + the backend reachable at `localhost:8080`.
`playwright.config.ts` auto-boots (`webServer`) the backend from the repo
root's `.venv` if nothing is already listening on `/health`, and reuses an
already-running instance otherwise.

```bash
cd e2e/extension
npm install            # once
npx playwright install chromium   # once
npm test
```
