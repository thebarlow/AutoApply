# core/ Context

Shared business logic. No framework dependencies — used by `web/`, `scraper/`, and tests.

## Files

```
core/
├── job.py               # Job entity + all LLM-driven methods (score, generate, extract, eval, refine, ATS check)
├── user.py              # User entity; profile load/save, prompt resolution, degree/skills helpers
├── profile_tree.py      # Recursive typed profile/résumé tree (closed node vocab) + validate_tree + tree_to_legacy adapter + legacy_to_tree migration
├── section_presets.py   # Preset section subtrees mirroring the legacy master profile (header/summary/experience/education/projects/skills)
├── llm.py               # LLM client construction and model resolution
├── logging_config.py    # setup_logging(): root logger → stdout + size-rotating file (5MB×5) + thread/sys excepthook; env-configurable (LOG_LEVEL/LOG_DIR/LOG_FILE); idempotent, never crashes startup
├── utils.py             # Misc helpers (sanitization, path utilities, PDF rendering)
├── session_cost.py      # Thread-safe accumulator for per-session LLM spend (from usage.cost)
├── skill_analytics.py   # Skill token normalization + frequency aggregation across jobs (no LLM)
├── demo_data.py         # seed_demo_job: inserts one pre-scored demo job at profile creation (onboarding tour content; no LLM)
├── schemas.py           # Pydantic models for structured résumé/cover generation (ResumeDocument, CoverDocument, ResumeGeneration, sub-models)
├── document_builder.py  # Snapshots profile data at generation time and joins LLM prose to structured profile data
├── document_assembler.py # PURE module — renders a structured document to canonical-ordered Markdown (no DB, no LLM)
├── document_parser.py    # Inverse of document_assembler — reconstructs a structured document from rendered Markdown (canonical AND legacy LLM formats)
├── application_fields.py # Canonical application-form field taxonomy with deterministic/eligibility/EEO value resolvers (pure, no LLM, no network)
├── application_classify.py # Label heuristics: is_eeo_label (demographic guard, runs first), match_eligibility, classify_custom (pure strings)
├── ats_schemas.py       # Hand-authored STATIC_SCHEMAS (greenhouse/lever/ashby only) mapping native form field ids → canonical keys; schema_for()
├── application_mapper.py # build_plan()/needs_essay_pass(): orchestrates taxonomy+classifier+schemas into an ApplicationPlan (pure; essay drafting injected)
├── ats_gate.py          # Two-layer ATS parseability gate over the rendered résumé PDF (mechanical + semantic)
├── pricing.py           # Fixed-unit price card: price_for()/unit_usd()/resolve_generate_action()
├── credits.py           # Credit ledger: prepaid fixed debit, refund, grant/reconcile, tiered signup grants
├── metering.py          # meter_action context manager: prepaid per-action debit + refund-on-failure around LLM calls
├── payments.py          # Tier-aware pricing calculator: compute_credits()/packs_for_tier()/resolve_price_id() (no Stripe SDK calls)
└── stripe_client.py     # Thin wrapper over the stripe SDK: create_customer, create_checkout_session, construct_event
```

## Field-mapping engine (sub-project 2 of document-submission automation)

Maps a profile + generated documents onto an ATS application form, producing a
read-only `ApplicationPlan` (no form writing — that is a later sub-project).
Pipeline: `application_fields.py` (canonical taxonomy + resolvers, `FieldKind` ∈
deterministic/eligibility/eeo/essay/unknown) + `application_classify.py`
(routing) + `ats_schemas.py` (static greenhouse/lever/ashby schemas) feed
`application_mapper.build_plan()`. Objective/EEO answers resolve deterministically
from `User.application_answers` (`{eligibility, eeo}`); free-text questions get one
injected LLM draft via `draft_essays`. **EEO safety:** demographic fields are
guarded out of the LLM path twice — `is_eeo_label` in `classify_custom`, and an
explicit branch in `build_plan` before the essay bucket; `needs_essay_pass` also
excludes them so metering never fires on a demographic-only form. The
`map_fields` price (in `pricing.py`, default 2 units) is charged **only** when the
essay pass actually runs. The plan is stored as JSON on `Job.application_plan`
(migration `aa13applyplan01`) and surfaced via `serialize()`. LLM drafting lives
in `job.draft_application_answers()` (grounded in `user.master_resume()`).

## Profile Schema Engine

`profile_tree.py` is the source of truth for profile structure: a recursive,
closed-vocabulary node tree (root → section → list/group → field). `User`
stores it as `profile_tree` inside `user_profile.data` and derives the legacy
typed attrs (`work_history`/`education`/`projects`/`skills`/contact/`hero`) from
it on every load via `tree_to_legacy`, so generation/rendering/UI are unchanged.
Legacy profiles are migrated once on load via `legacy_to_tree`. Job-search
metadata (target roles/salary, resume/md paths) stays as flat `data` keys, not
in the tree. **Known gap:** custom (non-`role`) sections are storable but do not
appear on generated documents until sub-project #4. **#4 updates:** `SectionNode` and `GroupNode` now have `locked: bool` and `prompt: str` fields; legacy `regen_lock` on groups migrates to `locked` via a before-validator. `FieldNode.regen_lock` is unchanged.

**Sub-project #4 updates (section/item authoring prompts):**
- `build_section_prompt(section)` in `profile_tree.py` assembles the canonical folded authoring prompt `[<SectionName>: <section.prompt> [<ItemName>: <item.prompt>] …]` (empty section/item prompts omitted; locked section → `""`; locked entries skipped). It is the single source of truth for the folded format and is mirrored byte-for-byte in JS by `buildFoldedPreview` in `PromptField.jsx`. Consumed by `core/section_generator.py`.
- `tree_to_legacy` now omits invisible sections, invisible list entries, and invisible header/summary/skills fields from the projected document dict.

**`_format_block` deduplication note:** `_format_block` in `core/section_generator.py` dedupes outputable fields by `key` across list entries, so differing per-entry `output_format` on the same key would only describe the first to the LLM (acceptable for current data).

**Sub-project #3 (per-section generation engine) is DONE:** ships `core/section_generator.py` — a schema-driven, per-section LLM generation engine. One call per section; locked list entries are kept as fixed context (never authored); sections with no `llm_output`-role fields are skipped (no LLM call); per-section failures fall back gracefully without crashing the whole document. Field roles (`llm_output` / `llm_input` / `regen_lock`) are used to decide which fields the model should fill vs. receive as context vs. carry through unchanged. `generate_resume_by_section(root, job_ctx, client, model, resolve=None)` skips locked sections entirely (no call), injects section/entry `prompt` into each built prompt, and applies `resolve` (e.g. token expansion) to the final prompt before the LLM call. `web/routers/dev.py` composes the resolver as `resolve_profile_tokens` + `_apply_template({"job": job})`.
  - **`profile_tree.resolve_profile_tokens(root, text)`** — resolves node-id tokens `{profile:<nodeId>}` (rename-safe): a field id → its value; a section/group id → "<name>: <value>" lines for all its fields; unknown ids left as-is. Helpers: `_node_by_id` (tree search), `_collect_fields` (field traversal, does not descend into list item templates).

**Sub-project 2C (graphical builder) is DONE:** ships drag-drop reorder of sections and list items (via `dnd-kit`) on top of the 2B editor, plus a recommended-section gallery (`SectionGallery.jsx` + `sectionCatalog.js`, 7 templates + Blank) replacing the old "+ Add section" button. `↑`/`↓` buttons are retained as the a11y fallback. No document rendering of custom sections — that is sub-project #4.

**Sub-project 2B (tree-driven editor) is DONE:** the React dashboard now renders
`ProfileTreeEditor` (consuming the 2A `GET`/`PUT /tree` endpoints) in place of
the flat doc-section accordions. The flat `update_profile` endpoint is retained
for name/job-preferences/onboarding writes — only the flat *doc-section editor
UI* was retired. Custom sections remain unrendered on generated documents until
sub-project #4.

**Sub-project 2A (write-path consolidation + tree API) is DONE:** `User._to_dict`
now uses `apply_flat_to_tree` (in-place overlay) instead of the former
`with_rebuilt_tree` (destructive rebuild). All write paths (`User.save`,
`update_profile`, parse-merge endpoint) go through
`merge_flat_into_stored`, which picks the stored tree as base (preserving node
`id`s, custom sections, `regen_lock`, `llm_instructions`, `llm_input`,
`bullet_style`, manual ordering) and overlays flat edits in place. A regression
test verifies that a custom section + a regen lock survive a save/load cycle.
`GET /api/config/profiles/{id}/tree` returns the tree (migrating legacy profiles
on first access); `PUT /api/config/profiles/{id}/tree` accepts a full tree,
validates it (`validate_tree_limits` — ≤ 500 nodes, ≤ 6 deep — then
`validate_tree`), derives flat fields via `tree_to_legacy`, stores both (non-
section metadata like `target_roles`, salary, and LLM/upload keys are preserved
via `{**existing, **derived, "profile_tree": ...}`), and returns the stored tree.
These endpoints are consumed by the 2B editor. Validation failures → HTTP 422.

`document_parser.py` parses both the canonical `document_assembler` output and the older free-form LLM markdown (experience entries split on `### ` **or** bold-only headings, `Title at Company`/`Title, Company` separators, one-line `**Name:**`/`**Name**:` projects).

**Known limitation:** Backfill via `document_parser.py` is lossy for fields the assembler does not render. Notably `ResumeProject.url` is absent from the rendered Markdown (and the PDF), so reconstructed projects come back with `url=""`.

**Note:** `core/scorer.py` and `core/profile_parser.py` were deleted — stale `.pyc` files remain in `__pycache__/` and can be ignored. Scoring logic moved into `job.py`.

## Routing Rules

| Task | File |
|---|---|
| Scoring a job (LLM call, score field updates) | `job.py` → `Job.score()` |
| Background resume/cover generation (daemon thread; own DB session, SSE emit, chains into refinement/ATS) | `intake_pipeline.run_resume_generation()` / `run_cover_generation()` (spawned by the 202 generate endpoints) |
| Generating resume markdown | `job.py` → `Job.generate_resume_md()` |
| Rendering resume PDF | `job.py` → `Job.generate_resume_pdf()` |
| Generating cover letter markdown | `job.py` → `Job.generate_cover_md()` |
| Rendering cover letter PDF | `job.py` → `Job.generate_cover_pdf()` |
| Evaluating resume quality (returns score + issues) | `job.py` → `Job.evaluate_resume_md()` |
| Evaluating cover letter quality | `job.py` → `Job.evaluate_cover_md()` |
| Rewriting resume to address eval issues | `intake_pipeline._run_resume_section_refinement` (per-section regen; no `Job` method) |
| Rewriting cover letter to address eval issues | `job.py` → `Job.refine_cover_md()` |
| Extracting structured job description fields | `job.py` → `Job.extract_description()` (also calls `match_profile_skills`) |
| Semantic skill-match cache (run/re-run after extraction) | `job.py` → `Job.match_profile_skills()` |
| Post-intake background extraction trigger | `job.py` → `Job.intake()` |
| Per-section LLM generation (skips locked, injects section prompt, resolves tokens before LLM) | `section_generator.py` → `generate_resume_by_section()` |
| Resolving node-id tokens `{profile:<nodeId>}` in prompts | `profile_tree.py` → `resolve_profile_tokens()` |
| User profile load/save/validation | `user.py` → `User` |
| Degree list for hallucination-detection context | `user.py` → `User.education_degrees` |
| Full profile render for prompt injection | `user.py` → `User.render_for_prompt()` |
| Master resume markdown for prompt injection | `user.py` → `User.master_resume()` |
| Prompt file resolution per type | `user.py` → `User.resolve_prompt()` |
| LLM client construction (active provider) | `llm.py` → `get_openai_client()` |
| LLM client for named provider | `llm.py` → `get_client_for_named_provider()` |
| LLM client from user profile config | `llm.py` → `get_client_for_profile()` |
| Single-turn LLM call helper | `llm.py` → `call_llm()` |
| Session LLM cost tracking | `session_cost.py` |
| Case-folded grouping key for a raw token (alias-aware) | `skill_analytics.py` → `skill_key()` |
| Normalizing a raw skill token to a canonical display name | `skill_analytics.py` → `normalize_skill()` |
| Aggregating skills into importance tiers (High/Med/Low) + categories | `skill_analytics.py` → `aggregate_skill_frequency()` |
| Mapping a skill to its tech category | `skill_analytics.py` → `tech_category()` |
| Testing if a job lists a skill (any extraction field) | `skill_analytics.py` → `job_has_skill()` |
| Seeding the `skill_aliases` table from the curated map | `skill_analytics.py` → `seed_alias_pairs()` |
| Shared utilities | `utils.py` |
| Pydantic models for structured document artifacts | `schemas.py` |
| Snapshot profile + join LLM prose to structured data (résumé/cover build) | `document_builder.py` → `build_resume_document()`, `build_cover_document()` |
| Apply a prose-only keyed patch to a stored `ResumeDocument` (refine path) | `document_builder.py` → `apply_resume_patch()` |
| Render a structured document to canonical Markdown | `document_assembler.py` → `assemble_resume_markdown()`, `assemble_cover_markdown()` |
| Reconstruct a structured document from rendered Markdown (inverse of the assembler) | `document_parser.py` → `reconstruct_resume_document_from_markdown()`, `reconstruct_cover_document_from_markdown()` |
| Structured (JSON) LLM call with strict-JSON hardening + one retry | `job.py` → `_llm_json_with_retry()` |
| Classifying a resolved apply URL to its ATS type; unwrapping LinkedIn safety-redirect wrappers | `ats.py` → `classify_ats()`, `unwrap_apply_url()` |
| ATS parseability gate (mechanical hard-block + LLM advisory) | `ats_gate.py` → `run_gate()` / `Job.run_ats_check()` |
| Mechanical ATS checks (contact, sections, skills, glyph-junk, text-layer) | `ats_gate.py` → `check_mechanical()` |
| Semantic ATS roundtrip check (LLM re-parse of extracted text) | `ats_gate.py` → `check_roundtrip()` |
| Canonical application-form field taxonomy + value resolvers | `application_fields.py` → `CANONICAL_FIELDS`, `resolve_canonical()`, `CanonicalField`, `ResolveContext` |
| Fixed-unit price card | `pricing.py` → `price_for()`, `unit_usd()`, `resolve_generate_action()` |
| Credit ledger: grants, prepaid fixed debit, refund, reconciliation | `credits.py` → `grant_credits()`, `debit_fixed()`, `refund_debit()`, `reconcile_balance()`, `signup_grant_for_tier()` |
| Per-action prepaid gate + debit settle around LLM calls | `metering.py` → `meter_action()` |
| Tier-aware credit pack pricing (multipliers, bulk discounts, fees, per-tier credits) | `payments.py` → `tier_multipliers()`, `price_tiers()`, `tier_visibility()`, `price_ids()`, `compute_credits()`, `packs_for_tier()`, `resolve_price_id()` |
| Stripe SDK calls (customer, Checkout session, price lookup, webhook signature verification) | `stripe_client.py` → `create_customer()`, `create_checkout_session()`, `construct_event()` |

## LLM Integration

See project memory note: the project uses the **OpenAI SDK** with multi-provider support (not the Anthropic SDK). Provider/model/API key are stored in the Config DB table and resolved at request time via `core/llm.py`.

`llm.py` supports three resolution paths:
1. **Active provider** (`get_openai_client`) — reads `llm_active_provider` from Config DB; API key from env `LLM_KEY_{PROVIDER_NAME}`.
2. **Named provider** (`get_client_for_named_provider`) — looks up a named entry from `named_providers` config; API key from env `LLM_KEY_{ID}`.
3. **User profile** (`get_client_for_profile`) — uses `user.llm_provider_type` / `user.llm_model`; API key from env `LLM_KEY_PROFILE_{user.id}`.

`call_llm` accumulates spend via `session_cost.add_cost(usage.cost)` on every response, and also calls `metering.record_call(usage.cost, model, prompt_tokens, completion_tokens)` — a no-op unless an action meter is open (see "Credits & Metering" below).

**Model allowlist (audit, 2026-07-18):** `allowed_models()` / `model_allowed(model)` gate which models tenants may select. `LLM_ALLOWED_MODELS` env (comma-separated) defines the set; if unset and `APP_ENV=production`, it fails safe to `{LLM_DEFAULT_MODEL}`; if unset locally, unrestricted (`allowed_models()` returns `None`). Enforced at `PUT /api/prompts/{profile_id}/{type_key}` (422) and in `get_client_for_profile`, which silently drops a disallowed `model_override` from a stale `Prompt` row and falls back to the platform default.

## Skill Matching and Hallucination Detection

- Skill matching between user skills and job requirements is **fully delegated to the LLM** — the full user skills list is injected into scoring/generation prompts via `{user.skills}` placeholders; no Python-side filtering occurs.
- **Semantic skill-match cache (`ext_skill_match` on `Job`)** — a JSON blob `{"matched":[...],"profile_hash":"..."}` set once at extraction time by `Job.match_profile_skills(user, client, model, db, prompt_content)`. The `matched` list contains the subset of the job's required/preferred/tech-stack skill chips that the full profile (skills + education + work history + projects) satisfies, determined via an LLM call using the `skill_match` prompt. Module-level helpers: `profile_skill_hash()` (stable hash of the full profile text used for staleness detection), `_skill_match_matched()` (parses the cached JSON), `_skill_match_stale()` (compares the stored `profile_hash` to the current profile). `Job.serialize()` exposes `matched_skills` (the matched list) and `skill_match_stale` (always `False` in serialize — it has no DB session, so stale detection is unavailable there; the UI ↻ button works regardless). The `skill_match` prompt is a DB-seeded `PromptDefault` (type key `"skill_match"`); like `ats_parse` it is **not** in `PROMPT_TYPE_KEYS` — not a per-profile override.
- **Manual live-prompt note:** the active `extraction` prompt DB row (per profile) must be manually re-seeded/edited to pick up the Task 9 seed-file cleanup; the seed-file change does **not** auto-apply to existing profile rows. Do **not** push a re-seed to the live hosted instance without explicit user approval.
- **Separate concern — analytics/UI skill grouping** (`skill_analytics.py`): grouping is case-folded (`FASTAPI`/`FastAPI` collapse) and resolved through an alias map. `skill_key`/`normalize_skill`/`aggregate_skill_frequency`/`job_has_skill` take an optional `aliases` dict; `None` falls back to the built-in `_ALIASES` map. At runtime `web/routers/stats.py` passes a merged map (`_ALIASES` base + DB `skill_aliases` overrides). This drives the In-Demand charts and the description chip ownership coloring — it does **not** affect what the LLM sees.
- Eval prompts receive `{user.education_degrees}` (via `User.education_degrees`) to supply ground-truth degree data for hallucination detection. Degrees are **excluded** from hallucination penalties — only skills/experience claims are checked.

## Structured Résumé / Cover Generation

Phase 3a introduced a structured generation path so that generated documents are stored as typed data, not only as flat Markdown files.

### Schemas (`core/schemas.py`)

- **`ResumeGeneration`** — the LLM output contract. JSON-only; contains prose keyed by ref (experience/project refs), skills, and profile section text. The résumé prompt was rewritten to this contract; a one-time migration (`_migrate_resume_prompt_v2`, gated by Config key `resume_prompt_v2`) force-updates the default and all profile résumé prompts on first `init_db` run.
- **`ResumeDocument` / `CoverDocument`** — stored artifact models. Serialized to `structured_json` in the `documents` table.
- Sub-models: `ResumeHeader`, `ResumeExperience`, `ResumeProject`, `ResumeSkillGroup`, `SignOff`, `ExperienceRef`, `ProjectRef`.

### Document Builder (`core/document_builder.py`)

Snapshots the user's profile at generation time and joins LLM prose to the structural profile data. No LLM calls; no rendering.

- **`build_resume_header`** — captures name, email, phone, location, and social links (github/linkedin/website) from the `config` table.
- **`build_resume_document`** — Experience = ALL work-history entries in profile order (most-recent-first as stored). An entry the LLM omitted is kept with an empty description. Projects = the LLM-selected subset in LLM order; out-of-range or duplicate refs are ignored (logged). Education is snapshotted from the profile.
- **`build_cover_document`** — same header snapshot; body prose from the LLM output.

### Document Assembler (`core/document_assembler.py`)

Pure module — no DB access, no LLM calls. Renders a `ResumeDocument` or `CoverDocument` to canonical-ordered Markdown.

Canonical section order: **Profile → Experience → Education → Projects → Skills**. Empty sections are omitted. Constants: `CANONICAL_SECTIONS`, `resume_section_order`.

### `generate_resume_md` / `generate_cover_md` (in `job.py`)

After the LLM call:
1. Parses the response into `ResumeGeneration`.
2. Calls `build_resume_document` / `build_cover_document` to produce the typed artifact.
3. Upserts the artifact into the `documents` table (`Document.upsert`) — this is the **source of truth**.
4. Assembles canonical Markdown via the document assembler and writes `generator/outputs/{profile_id}_{job_key}_resume.md` / `{profile_id}_{job_key}_cover.md` (YAML front matter sourced from the snapshot header). **All output artifacts are prefixed with `profile_id`** — `job_key` is unique only per profile, so an unprefixed name let two tenants collide on the same file (cross-tenant document leak). Any new output path (PDF, DOCX, turn snapshot) must keep the `{profile_id}_{job_key}_...` prefix.

### `_render_meta` snapshot behavior

`Job._render_meta(doc_type, db)` reads contact and education data from the stored `Document` snapshot when one exists, so re-rendering an old job uses generation-time data rather than the live profile. Falls back to `_frontmatter_data` (live profile) when no document row exists (e.g. jobs generated before Phase 3a).

### `documents` table

Defined in `db/database.py` as `Document`. Columns: `id`, `job_key`, `doc_type` ("resume"|"cover"), `structured_json`, `created_at`. Unique constraint on `(job_key, doc_type)`. Helpers: `Document.fetch(db, job_key, doc_type)`, `Document.upsert(db, job_key, doc_type, structured_json)` (upsert commits).

### Phase 3b: structured document as source of truth

The structured `Document` table is now the **single source of truth**; the `.md` is purely derived. The `.md` is written only by `write_resume_markdown` / `write_cover_markdown` (assemble from the document + snapshot front matter), which are invoked from generation, structured editing, and refine — never edited directly. `_refine_doc_md` is **cover-only**: it rewrites the cover body prose, re-persists, then re-derives `.md` + PDF (it takes `db` as a parameter). Résumé refinement does not use it — tree-v1 résumés are refined per-section by `intake_pipeline._run_resume_section_refinement`.

## ATS Gate (`core/ats_gate.py`)

Two-layer gate that validates the rendered résumé PDF before the application is submitted.

**Mechanical layer (`check_mechanical`)** — deterministic, hard-block on any critical issue:
- Contact presence and order (name → email → phone in the header)
- Required section headings present (Experience, Skills, etc.)
- Skills listed in the job's `ext_required_skills` survive in the extracted PDF text
- Glyph-junk detection (high ratio of non-ASCII / replacement characters)
- Text-layer check (pdfplumber; flags image-only PDFs that ATS systems cannot parse)

**Semantic layer (`check_roundtrip`)** — LLM re-parse via the existing client (advisory, non-blocking by default): asks the model to re-extract key fields from the raw PDF text and compares against the source document.

`run_gate(...) -> AtsReport` orchestrates both layers and produces a scored report. Entry point on `Job` is `Job.run_ats_check(db, user, client, model) -> AtsReport` (read-only). `Job.store_ats_report(report)` persists it to the `ats_passed` / `ats_score` / `ats_report_json` / `ats_checked_at` columns; `Job.ats_is_stale()` reports whether the résumé was re-rendered after the last check.

**When the gate runs (auto, after generation):** the gate runs automatically in a background thread after the résumé is finalized — i.e. after the refinement loop settles, or immediately after generation when refinement is off/0 turns (`web/intake_pipeline.run_resume_refinement` → `run_ats_gate`). It also re-runs after a manual résumé edit (`PUT /{job_key}/resume/document`). Both layers run on every auto-trigger. The report is stored on the job and surfaced in the tray UI (`serialize()` exposes `ats_passed` / `ats_score` / `ats_stale` / `ats_issues`).

**At apply (`POST /api/jobs/{job_key}/confirm-applied`, `web/routers/tray.py`):** the handler **trusts the stored report** — it does not re-run the gate:
- **HTTP 422** if no report exists yet or the report is stale (résumé changed since the last check).
- **HTTP 409** if the stored `AtsReport` has any critical (hard-block) issue.
- Advances state to `applied` only when the stored report passed and is current.

The `ats_parse` prompt used by the semantic layer is a DB-seeded `PromptDefault` (type key `"ats_parse"`). It is **not** in `PROMPT_TYPE_KEYS` — it is seeded directly by `init_db` and is not exposed for per-profile override.

## Application Field Taxonomy (`core/application_fields.py`)

**Task 1 of the field-mapping engine spec.** A pure, deterministic, zero-network module that defines a
canonical application-form field taxonomy mapping stable field keys to value resolvers.

**Schema:** `CanonicalField(key, kind, resolve)` where `kind` is one of:
- `"deterministic"` — user profile data (first_name, email, phone, links, location, resume_file)
- `"eligibility"` — user-supplied application answers (work_authorized, sponsorship, relocation, start_date, years_experience)
- `"eeo"` — user-supplied EEO self-identification (gender, race/ethnicity, veteran status, disability)
- `"essay"` — long-form text (cover letter body — future)
- `"unknown"` — unrecognized field

**CANONICAL_FIELDS dict:** 19 fields (deterministic + eligibility + EEO). Each resolver is a pure
function `(ResolveContext) → str | None` with no side effects. Resolvers read from:
- `ResolveContext.user` — `User` entity (`.first_name`, `.email`, `.phone`, `.linkedin`, `.github`, `.website`, `.location`)
- `ResolveContext.documents` — dict of document keys to rendered prose (e.g. `"resume_file"`, `"cover_letter_text"`)
- `ResolveContext.answers` — dict of application-answer groups (e.g. `answers["eligibility"]["work_authorized"]`)
- `ResolveContext.job` — `Job` entity (unused in Task 1, reserved for future)

**Entry point:** `resolve_canonical(key: str, ctx: ResolveContext) → str | None` looks up a field by
canonical key and resolves its value, or returns `None` if unknown/unset.

**Known gap:** Eligibility and EEO answers are not yet stored in the DB (no `application_answers` table
or profile section). Task 2 (mapper engine + profile section) will add this storage and populate
`ResolveContext.answers`.

## Credits & Metering (`core/pricing.py`, `core/credits.py`, `core/metering.py`)

Prepaid fixed-unit pricing (2026-07-16). `pricing.py` holds the price card:
`price_for(action)` returns an integer unit price from `DEFAULT_PRICES`
(`intake=2, generate_fresh=4, regenerate=2, score/extract/resume_parse/
ats/rematch/draft=1`), each overridable via `PRICE_<ACTION>` env; `unit_usd()`
(`CREDIT_UNIT_USD`, default $0.02) is the dollar value of one unit, used only
by the pack calculator (`payments.py`), not by debit sizing;
`resolve_generate_action(db, job, doc_type)` derives `generate_fresh` vs
`regenerate` server-side from an existing `Document` row or stored output
path.

`credits.py` holds ledger operations: `debit_fixed(db, profile_id, *, action,
job_key, price)` is a single atomic conditional `UPDATE …
credit_balance - price WHERE credit_balance >= price`, raising
`InsufficientCredits(balance, price, action)` if the row doesn't match — so
balances can never go negative and there's no separate gate-then-debit race.
`refund_debit(db, debit_row)` inserts a compensating `+price` ledger row.
`grant_credits` inserts a `CreditLedger` row and updates the cached
`Account.credit_balance` in the same transaction. `reconcile_balance`
recomputes the cached balance from `SUM(credit_ledger.delta)`.
`signup_grant_for_tier(tier)` (env `CREDIT_SIGNUP_GRANTS` JSON map, defaults
`standard` 20 / `friends_family` 50 / `beta` 200 units) sizes the signup
grant per tier. **`grant_credits`/`debit_fixed`/`reconcile_balance` are
no-ops (return `None`) when `get_account_for_profile` finds no `Account`
row** — i.e. local/dev/tray/test runs that have no authenticated account are
unaffected. Deleted: `credit_floor`, `debit_for_action`, `to_credits`,
`signup_grant_amount`.

`metering.py` provides `meter_action(db, profile_id, *, action, job_key,
price=None)`, the single chokepoint that wraps each billable `Job` method
call from `web/`:
- **Debit-first** — if the account is metered (`Account` exists, not admin,
  `credit_rate > 0`), it debits `price_for(action)` (or the explicit `price`
  override) via `debit_fixed` **before the body runs** — `InsufficientCredits`
  propagates as an HTTP 402 without ever executing the LLM call.
- **Record** — opens a `ContextVar` accumulator; every LLM call inside the
  `with` block appends its cost via `record_call(cost, model, prompt_tokens,
  completion_tokens)` (for raw-cost annotation only, not for billing). `call_llm`
  does this through `core.llm.record_usage`; direct
  `client.chat.completions.create` sites (extraction, skill-match) call
  `record_usage(response, model)` themselves.
- **Settle** — on success, annotates the already-debited ledger row with the
  summed raw cost + call metadata (models, token counts) for margin
  tracking; this never changes the charge. On any exception in the body, it
  refunds the debit (`refund_debit`) before re-raising — failed/no-op actions
  are never billed.
- A content-free `credits` SSE event (`_notify_credits_changed`, best-effort)
  fires on both debit and refund so the dashboard navbar refetches its
  balance instead of lagging until the next load/402.
- Unmetered accounts (no `Account` row, or `credit_rate == 0` — the developer
  tier) run the body ungated and record/debit nothing.

**Metering topology:** intake pipeline = **one** `intake` (2u) meter around
extract + score + skill-match (`web/intake_pipeline.py`); generate endpoints
(`web/routers/jobs.py`) resolve `generate_fresh` (4u) vs `regenerate` (2u) via
`resolve_generate_action` and bundle post-gen eval/refine turns under that
same debit (ATS free when part of a generate flow); standalone
score/extract/rematch/resume_parse/draft endpoints are 1u each; the ATS gate
is metered (1u) only when re-triggered by a manual document edit outside a
generate flow; the feedback-refine 202 endpoint does a fail-fast pre-check
then meters **one** `regenerate` (2u) for the background turn. Failed actions
(including tree-v1 no-op/failure paths) are refunded via the `meter_action`
exception path.

## Payments (`core/payments.py`, `core/stripe_client.py`)

`payments.py` is a pure tier-aware pricing **calculator** (no Stripe SDK
calls). Packs are now unit-denominated: `compute_credits(price_usd, tier) =
net(price_usd) / unit_usd() × tier_multiplier × (1 + bulk_discount)` — net
proceeds (price minus the Stripe fee model + tax buffer), converted to units
at `pricing.unit_usd()`, scaled by the tier multiplier and the bulk discount
for that price point. Public functions: `tier_multipliers()` (env
`CREDIT_TIER_MULTIPLIERS`, defaults `standard`×1 / `friends_family`×4 /
`beta`×10 — replaces the deleted `tier_margins`), `price_tiers()` (bulk
discount per dollar amount), `tier_visibility()`, `price_ids()` (dollar→Stripe
price id), `compute_credits()`, `packs_for_tier()`, `resolve_price_id()`. The
old `load_packs`/`credits_for_price`/`STRIPE_PACKS` flat map is retired in
favor of `STRIPE_PRICE_IDS` plus optional overrides
`CREDIT_TIER_MULTIPLIERS`/`CREDIT_PRICE_TIERS`/`CREDIT_TIER_VISIBILITY` and the
fee model `STRIPE_FEE_PCT`/`STRIPE_FEE_FIXED`/`TAX_RATE`. The admin
grant-budget stat is likewise reported in unit denomination. `stripe_client.py` wraps the
`stripe` SDK (v15.2.1) with `create_customer`, `create_checkout_session`,
and `construct_event` (webhook signature verification),
reading `STRIPE_SECRET_KEY`/`STRIPE_WEBHOOK_SECRET` from env lazily. Consumed
by `web/routers/payments.py`, which records `Purchase` rows and grants
credits via `grant_credits(reason="purchase")` on a verified
`checkout.session.completed` webhook. See `docs/ARCHITECTURE.md` → "Payments" and
`web/CONTEXT.md` for the route surface and the `window.__creditRate`
cross-widget read used by the navbar session-usage overlay.

## Failed scrapes (blank description)

A job whose raw `description` is blank (NULL or whitespace-only) is a failed
scrape. `Job.has_description()` is the single source of truth for the rule
(`bool((self.description or "").strip())`). Such jobs are neither extracted nor
scored: `run_pipeline` (`web/intake_pipeline.py`) short-circuits them on intake
and `Job.score()` raises `RuntimeError` defensively for any other caller
(manual/batch re-score). They are flagged with `unread_indicator='error'` +
`last_result_error="Scrape failed: empty description."`, which the dashboard
renders as the existing warning icon. To correct jobs mis-scored before this
rule existed, run `python -m scripts.flag_failed_scrapes` (dry run) then
`--confirm` (`--target live` for the hosted Postgres DB).

## Key Invariants

- `Job` methods that call the LLM receive an already-constructed client + model string — they do not read config themselves.
- All DB writes inside `Job` methods use the session passed in; callers are responsible for commit/rollback.
- The résumé refine + structured-edit paths pass `max_pages=1` to `generate_resume_pdf`; `render_pdf` auto-shrinks the print scale to fit one page (see `generator/CONTEXT.md`). (`web/routers/jobs.py` `put_document` also passes `max_pages=1`.)
- `_refine_doc_md` uses `max_tokens=32768` to avoid truncation on rewrites.
- `User.from_markdown` (résumé-parse LLM call, backing `from_pdf` and the parse/propose
  endpoint) uses `max_tokens=32768` and `timeout=90` — a long (4+ page) résumé produces
  large structured JSON that overflowed the former 8000-token cap, truncating the output
  (`finish_reason='length'`) and surfacing downstream as a confusing 422 "invalid JSON".
  It now checks `finish_reason == "length"` and raises a clear `ValueError`
  ("Résumé parse truncated…") instead of letting truncated JSON reach the parser.
- Structured résumé generate/refine call the LLM through `_llm_json_with_retry` (module-level in `job.py`): it appends a strict-JSON instruction (`_JSON_RETRY_SUFFIX`) and retries once with a corrective nudge when `parse_llm_json` fails. This guards against small/fast models breaking a markdown value out of its JSON string.
- Refinement settings are clamped server-side on `User._hydrate()` (audit, 2026-07-18): `resume_refine_max_turns` / `cover_refine_max_turns` → 0–`MAX_REFINE_TURNS` (5), pass scores → [0,1]. Refinement turns run unmetered inside the flat generation price, so client-supplied values must never expand them. Tests: `tests/core/test_refine_clamp.py`.
