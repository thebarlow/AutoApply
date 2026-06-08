# core/ Context

Shared business logic. No framework dependencies — used by `web/`, `scraper/`, and tests.

## Files

```
core/
├── job.py               # Job entity + all LLM-driven methods (score, generate, extract, eval, refine, ATS check)
├── user.py              # User entity; profile load/save, prompt resolution, degree/skills helpers
├── llm.py               # LLM client construction and model resolution
├── utils.py             # Misc helpers (sanitization, path utilities, PDF rendering)
├── session_cost.py      # Thread-safe accumulator for per-session LLM spend (from usage.cost)
├── skill_analytics.py   # Skill token normalization + frequency aggregation across jobs (no LLM)
├── schemas.py           # Pydantic models for structured résumé/cover generation (ResumeDocument, CoverDocument, ResumeGeneration, sub-models)
├── document_builder.py  # Snapshots profile data at generation time and joins LLM prose to structured profile data
├── document_assembler.py # PURE module — renders a structured document to canonical-ordered Markdown (no DB, no LLM)
└── ats_gate.py          # Two-layer ATS parseability gate over the rendered résumé PDF (mechanical + semantic)
```

**Note:** `core/scorer.py` and `core/profile_parser.py` were deleted — stale `.pyc` files remain in `__pycache__/` and can be ignored. Scoring logic moved into `job.py`.

## Routing Rules

| Task | File |
|---|---|
| Scoring a job (LLM call, score field updates) | `job.py` → `Job.score()` |
| Generating resume markdown | `job.py` → `Job.generate_resume_md()` |
| Rendering resume PDF | `job.py` → `Job.generate_resume_pdf()` |
| Generating cover letter markdown | `job.py` → `Job.generate_cover_md()` |
| Rendering cover letter PDF | `job.py` → `Job.generate_cover_pdf()` |
| Evaluating resume quality (returns score + issues) | `job.py` → `Job.evaluate_resume_md()` |
| Evaluating cover letter quality | `job.py` → `Job.evaluate_cover_md()` |
| Rewriting resume to address eval issues (+ re-renders PDF) | `job.py` → `Job.refine_resume_md()` |
| Rewriting cover letter to address eval issues | `job.py` → `Job.refine_cover_md()` |
| Extracting structured job description fields | `job.py` → `Job.extract_description()` |
| Post-intake background extraction trigger | `job.py` → `Job.intake()` |
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
| Structured (JSON) LLM call with strict-JSON hardening + one retry | `job.py` → `_llm_json_with_retry()` |
| ATS parseability gate (mechanical hard-block + LLM advisory) | `ats_gate.py` → `run_gate()` / `Job.run_ats_check()` |
| Mechanical ATS checks (contact, sections, skills, glyph-junk, text-layer) | `ats_gate.py` → `check_mechanical()` |
| Semantic ATS roundtrip check (LLM re-parse of extracted text) | `ats_gate.py` → `check_roundtrip()` |

## LLM Integration

See project memory note: the project uses the **OpenAI SDK** with multi-provider support (not the Anthropic SDK). Provider/model/API key are stored in the Config DB table and resolved at request time via `core/llm.py`.

`llm.py` supports three resolution paths:
1. **Active provider** (`get_openai_client`) — reads `llm_active_provider` from Config DB; API key from env `LLM_KEY_{PROVIDER_NAME}`.
2. **Named provider** (`get_client_for_named_provider`) — looks up a named entry from `named_providers` config; API key from env `LLM_KEY_{ID}`.
3. **User profile** (`get_client_for_profile`) — uses `user.llm_provider_type` / `user.llm_model`; API key from env `LLM_KEY_PROFILE_{user.id}`.

`call_llm` accumulates spend via `session_cost.add_cost(usage.cost)` on every response.

## Skill Matching and Hallucination Detection

- Skill matching between user skills and job requirements is **fully delegated to the LLM** — the full user skills list is injected into scoring/generation prompts via `{user.skills}` placeholders; no Python-side filtering occurs.
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
4. Assembles canonical Markdown via the document assembler and writes `generator/outputs/{job_key}_resume.md` / `{job_key}_cover.md` (YAML front matter sourced from the snapshot header).

### `_render_meta` snapshot behavior

`Job._render_meta(doc_type, db)` reads contact and education data from the stored `Document` snapshot when one exists, so re-rendering an old job uses generation-time data rather than the live profile. Falls back to `_frontmatter_data` (live profile) when no document row exists (e.g. jobs generated before Phase 3a).

### `documents` table

Defined in `db/database.py` as `Document`. Columns: `id`, `job_key`, `doc_type` ("resume"|"cover"), `structured_json`, `created_at`. Unique constraint on `(job_key, doc_type)`. Helpers: `Document.fetch(db, job_key, doc_type)`, `Document.upsert(db, job_key, doc_type, structured_json)` (upsert commits).

### Phase 3b: structured document as source of truth

The structured `Document` table is now the **single source of truth**; the `.md` is purely derived. The `.md` is written only by `write_resume_markdown` / `write_cover_markdown` (assemble from the document + snapshot front matter), which are invoked from generation, structured editing, and refine — never edited directly. `_refine_doc_md` now patches the structured document (via `apply_resume_patch` for résumés), re-persists it, then re-derives `.md` + PDF; it takes `db` as a parameter.

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

## Key Invariants

- `Job` methods that call the LLM receive an already-constructed client + model string — they do not read config themselves.
- All DB writes inside `Job` methods use the session passed in; callers are responsible for commit/rollback.
- `refine_resume_md` passes `max_pages=1` to `generate_resume_pdf`; `render_pdf` auto-shrinks the print scale to fit one page (see `generator/CONTEXT.md`). The structured-edit path (`web/routers/jobs.py` `put_document`) also passes `max_pages=1`.
- `_refine_doc_md` uses `max_tokens=32768` to avoid truncation on rewrites.
- Structured résumé generate/refine call the LLM through `_llm_json_with_retry` (module-level in `job.py`): it appends a strict-JSON instruction (`_JSON_RETRY_SUFFIX`) and retries once with a corrective nudge when `parse_llm_json` fails. This guards against small/fast models breaking a markdown value out of its JSON string.
