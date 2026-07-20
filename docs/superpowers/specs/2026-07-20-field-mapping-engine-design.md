# Field-Mapping Engine — Design

**Date:** 2026-07-20
**Status:** Approved (brainstorming complete)
**Sub-project:** 2 of 5 in "Full automation of document submission" (see `.claude/TODO.md`).

## Context

"Full automation of document submission" is decomposed into five sequenced sub-projects:

1. **ATS detection & apply-URL resolution** — DONE & shipped 2026-07-19 (see
   `docs/superpowers/specs/2026-07-19-ats-detection-design.md`). Gives each job an `ats_type`
   and resolved apply URL.
2. **Field-mapping engine** — *this spec*.
3. Form-fill + submit automation.
4. Credential vault (client-side, encrypted, extension-only).
5. Submission confirmation (auto-mark applied).

Sub-project 1 tells us, per job, whether it is easy-apply or external and — for external jobs —
which ATS hosts the form. This sub-project turns that into an **ApplicationPlan**: the resolved
`{form field → value}` mapping that sub-project 3 will use to actually fill and submit the form.
This sub-project performs **no form writing** — read-only form enumeration, server-side value
resolution, and a read-only preview.

**In scope:** LinkedIn/Indeed jobs already carrying an `ats_type` of `greenhouse`, `lever`, or
`ashby` (static-schema ATSs), plus dynamic enumeration for any recognized ATS form present on the
page. **Out of scope:** the API scrapers (Remotive/RemoteOK), login-gated ATSs
(Workday/iCIMS/Taleo — deferred to sub-project 4), and all form writing/submission.

## Goals

- Define a **canonical field taxonomy** and per-ATS **static schemas** (greenhouse, lever, ashby).
- Given a job, the user's profile, and the generated résumé/cover documents, compute an
  `ApplicationPlan` mapping each form field to a resolved value with a status.
- Let the extension enumerate a live form's fields (read-only) and merge them into the plan so
  job-specific custom questions are covered.
- Answer **objective/eligibility** questions and **EEO self-ID** questions deterministically from
  stored user profile answers; draft **free-text essay** questions with the LLM; never let the LLM
  touch demographic fields.
- Collect the eligibility + EEO answers in a new dashboard settings section, and nudge (softly, not
  block) when they are incomplete.
- Surface the computed plan in a read-only preview modal for eyeballing correctness now.

## Non-goals

- No form writing, submission, credential storage, or confirmation detection (sub-projects 3–5).
- No plan editing/approval UI (deferred to sub-project 3, which owns the fill flow).
- No hard gate on auto-fill — the readiness signal drives a soft nudge only.
- No ATS coverage beyond greenhouse/lever/ashby for static schemas (others rely on dynamic
  enumeration only).
- No filtering/sorting of jobs by plan readiness.

## Architecture overview

```
Extension (on apply page, read-only)          Server (core/ + web/)
─────────────────────────────────────         ─────────────────────────────────────
enumerate <input>/<select>/<textarea>  ──POST──▶  /api/jobs/{job_key}/application-plan
  → EnumeratedField[]                              │
                                                   ▼
                                          application_mapper.build_plan(
                                            job, user, documents, enumerated_fields)
                                                   │
                          ┌────────────────────────┼───────────────────────────┐
                          ▼                         ▼                           ▼
                 static ATS schema        canonical taxonomy            LLM essay pass
                 (greenhouse/lever/         + resolvers                  (one metered call,
                  ashby)                    (profile/doc/eligibility/     EEO-guarded)
                                            EEO answers)
                                                   │
                                                   ▼
                                          ApplicationPlan  ── persist (jobs.application_plan JSON)
                                                   │              + SSE broadcast
                                                   ▼
                                          read-only plan modal (dashboard)
```

The engine runs **server-side** (profile data, platform LLM key, tenant scoping, and testability all
live there). The extension only does DOM I/O.

## Canonical field taxonomy — `core/application_fields.py`

A registry of canonical field keys. Each entry declares a `kind` and a `resolver` (a pure function
of `(user, documents, job, answers)` returning a value or `None`):

| kind | examples | resolved from |
|---|---|---|
| `deterministic` | `first_name`, `last_name`, `full_name`, `email`, `phone`, `linkedin_url`, `github_url`, `resume_file`, `cover_letter_text` | `User` fields + generated documents |
| `profile_sourced` (eligibility) | `work_authorized`, `requires_sponsorship`, `willing_to_relocate`, `location`, `start_date`, `years_experience` | stored **eligibility** answers |
| `profile_sourced` (EEO) | `eeo_gender`, `eeo_race`, `eeo_veteran`, `eeo_disability` | stored **EEO self-ID** answers |
| `essay` | free-text ("Why this company?", "Tell us about a project…") | LLM draft, grounded in profile+job |
| `unknown` | enumerated custom field that matches no canonical key and is not classified essay | left blank |

`resume_file` and `cover_letter_text` resolve to **pointers** to the generated document artifacts
(rendered PDF path / cover text), not uploaded bytes — the actual upload is sub-project 3.

EEO fields are `profile_sourced`, **never** `essay`: they resolve from stored answers when present
and are blank otherwise. They are never LLM-inferred (see EEO guard below).

## Application-answers profile section (server-side)

A new structured section of the user profile, edited in the dashboard, holding two groups:

- **Eligibility (objective):** `work_authorized` (yes/no), `requires_sponsorship` (yes/no),
  `willing_to_relocate` (yes/no), `location` (free text), `start_date` (free text / date),
  `years_experience` (overall; per-skill deferred).
- **EEO self-ID:** `gender`, `race_ethnicity`, `veteran_status`, `disability_status` — each a
  single-select whose options include an explicit **"Decline to self-identify"** value.

Storage: persisted per-profile alongside the rest of the profile (tenant-scoped). This puts
sensitive demographic PII on the server for the first time; accepted as a **tier-gated
(Friends+Family) tradeoff** and recorded under Accepted limitations. All fields are optional.

A server-computed readiness flag, `application_answers_complete`, is derived from these values
(eligibility group filled; EEO group either filled or explicitly declined). It drives the soft
nudge only — it never blocks plan computation or (later) auto-fill.

## Static per-ATS schemas — `core/ats_schemas/`

Hand-authored standard-application field maps for **greenhouse, lever, ashby** only. Each maps the
ATS's native field identifiers (field `name`, `autocomplete`, and/or label text) → canonical keys,
for the standard fields those forms present (name, email, phone, résumé, cover letter, LinkedIn,
etc.). This table is the single source of truth for "what a standard form looks like" per supported
ATS. Any other `ats_type` has no static schema and relies entirely on dynamic enumeration.

## The engine — `core/application_mapper.py`

`build_plan(job, user, documents, enumerated_fields=None, answers=None) -> ApplicationPlan`

1. **Seed** expected fields from the static schema for `job.ats_type` (if any).
2. **Merge** dynamically-enumerated fields (if provided): normalize each to a canonical key using
   label/name/autocomplete heuristics; unmatched fields become candidate custom questions.
3. **Classify + resolve** each field, in this order:
   1. **EEO guard (first, deterministic):** a regex over the field label/name matching demographic
      terms (race, ethnicity, gender, sex, veteran, disability, …). A match forces the field to the
      EEO `profile_sourced` path — resolved from stored EEO answers or left blank — and **removes it
      from any LLM consideration**. This guard runs before classification so a misclassification can
      never route a demographic field to the essay pass.
   2. **deterministic** canonical → value from `User`/documents.
   3. **profile_sourced eligibility** → value from stored eligibility answers.
   4. **objective custom** (label matches a known eligibility question by keyword) → mapped to the
      corresponding eligibility answer.
   5. Remaining **free-text custom** → collected for the essay pass.
4. **Essay pass (one LLM call, EEO-free by construction):** draft answers for the collected
   free-text questions, grounded in profile + job context and the existing generation honesty rules.
   Marked `status=drafted` (needs review).
5. **Emit** `ApplicationPlan`.

### Field statuses

`filled` (deterministic/profile value present), `drafted` (LLM essay, needs review),
`blank` (profile_sourced with no stored answer, incl. declined EEO), `unknown` (custom field the
engine could not resolve or classify).

## Data model & schemas

Pydantic models in `core/schemas.py`:

- `EnumeratedField` — `{ field_id, label, input_type, options?, required }` (from the extension).
- `PlannedField` — `{ field_id, label, canonical_key?, value?, status, source }`.
- `ApplicationPlan` — `{ job_key, ats_type, fields: PlannedField[], generated_at }`.

Persistence: a new nullable `application_plan` JSON column on the `jobs` table (idempotent
`init_db.py` migration for SQLite + an Alembic migration for hosted Postgres — same pattern as the
ATS-detection columns). Stores the latest computed plan; recomputable at any time. Added to
`Job.serialize()`.

The application-answers profile section is stored via the existing profile persistence path (no new
table); a small set of typed fields on the profile.

## Server endpoints

In the jobs router, tenant-scoped `(profile_id, job_key)` (never `job_key` alone):

- `POST /api/jobs/{job_key}/application-plan` — body: `{ enumerated_fields?: EnumeratedField[] }`.
  Computes the plan via `build_plan`, persists it, SSE-broadcasts the updated job, returns the plan.
  404 if the `(profile_id, job_key)` row is absent.
- `GET /api/jobs/{job_key}/application-plan` — returns the last stored plan (drives the modal).

**Metering.** A new fixed-unit price-card action `map_fields` (`core/pricing.py`), charged with the
atomic upfront `debit_fixed` + refund-on-failure pattern **only when the LLM essay pass runs**. A
deterministic-only plan (no essay fields, hence no LLM call) is **not metered**. Consistent with the
existing prepaid model and its worst-case-cost-below-unit-price invariant.

The application-answers editing endpoints reuse the existing profile-update surface (tenant-scoped,
free — no LLM).

## Extension — read-only form enumeration

- On a recognized apply page, a new content routine walks the form's `<input>/<select>/<textarea>`
  elements, capturing per field: a stable id/name, label text, input type, options (for selects),
  and the required flag → `EnumeratedField[]`. **Read-only**; writing is sub-project 3.
- POSTs the enumerated fields to `POST /api/jobs/{job_key}/application-plan` with the stored bearer
  token (respecting the admin Live/Local toggle).
- **Soft nudge:** if the readiness flag `application_answers_complete` is false, the extension shows
  a non-blocking prompt ("Complete your application answers to auto-fill more") linking to the
  dashboard settings section. No hard gate.
- Selector-fragile like the rest of the extension; documented in `browser-extension/CONTEXT.md`.
  Form semantics (labels/autocomplete/`name`) are generally more stable than the hashed card DOM.

## UI

- **Application-answers settings section** (dashboard) — a new section editing the eligibility +
  EEO self-ID answers, reusing the profile-tree field-widget patterns
  (`react-dashboard/src/components/widgets/profile-tree/`). EEO selects include "Decline to
  self-identify". Tier-gated to Friends+Family.
- **Read-only plan modal** — a button on the job card (near `AtsChip`) opens a modal rendering the
  stored `ApplicationPlan` as a read-only table (field · value · status). No editing/approval —
  deferred to sub-project 3. If no plan exists yet, the modal explains the plan is computed when the
  extension visits the apply page.

## Testing

- **`core/application_fields.py`** — resolver unit tests: profile/documents/answers → canonical
  value, including missing-data → `None`.
- **Static schemas** — per-ATS table tests: native field identifier → expected canonical key.
- **Custom-question classification** — the **EEO regex guard** is the highest-value test: a table of
  demographic labels must all route to the EEO path and never to essay; objective-question keyword
  matching; essay routing for the remainder.
- **Engine** — end-to-end with a fixture job + profile + `enumerated_fields`, LLM mocked, asserting
  the resulting `ApplicationPlan` fields/statuses. Include an EEO-answered vs EEO-blank case.
- **Endpoints** — `POST` computes/persists/tenant-scopes (a cross-tenant POST cannot touch another
  tenant's row); metering debit on the essay path and refund on LLM failure; 404 on missing job;
  `GET` returns the stored plan.
- **Migration** — idempotency of the `application_plan` column add (running `init_db.py` twice is a
  no-op; nullable so existing rows are unaffected).
- **Extension DOM enumeration** — manual smoke test, consistent with the existing extension testing
  posture (selectors are not unit-tested).

## Open risks / accepted limitations

- **Demographic PII server-side.** Storing EEO self-ID answers on the server is a new,
  higher-sensitivity PII class than the app holds today. Accepted as a tier-gated (Friends+Family)
  tradeoff; all fields optional with an explicit "Decline to self-identify"; tenant-scoped like all
  profile data. Revisit if the app broadens beyond the trusted tier.
- **Selector fragility.** Read-only enumeration adds DOM reads that can break on an ATS redesign.
  Fails gracefully (no plan enrichment; static-schema plan still computed). Mitigated long-term by
  the "Browser-extension DOM recalibration tool" backlog item.
- **Essay honesty.** LLM-drafted answers reuse the existing generation honesty rules and are always
  marked `drafted` (needs review) — never submitted unreviewed (submission is sub-project 3, which
  will surface them for approval).
- **Classification imperfection.** A custom question may be mis-bucketed (objective vs essay vs
  unknown). The EEO guard is the only classification whose failure is unacceptable and is therefore
  deterministic and tested exhaustively; other misclassifications degrade to `unknown`/`drafted`
  (safe, user-reviewable) rather than wrong-and-silent.
- **No hard unlock gate.** Per the design decision, incomplete answers only trigger a soft nudge;
  auto-fill (sub-project 3) will proceed with whatever answers exist.
