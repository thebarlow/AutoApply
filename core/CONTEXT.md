# core/ Context

Shared business logic. No framework dependencies — used by `web/`, `scraper/`, and tests.

## Files

```
core/
├── job.py               # Job entity + all LLM-driven methods (score, generate, extract, eval, refine)
├── user.py              # User entity; profile load/save, prompt resolution, degree/skills helpers
├── llm.py               # LLM client construction and model resolution
├── utils.py             # Misc helpers (sanitization, path utilities, PDF rendering)
├── session_cost.py      # Thread-safe accumulator for per-session LLM spend (from usage.cost)
├── skill_analytics.py   # Skill token normalization + frequency aggregation across jobs (no LLM)
├── schemas.py           # Pydantic models for structured résumé/cover generation (ResumeDocument, CoverDocument, ResumeGeneration, sub-models)
├── document_builder.py  # Snapshots profile data at generation time and joins LLM prose to structured profile data
└── document_assembler.py # PURE module — renders a structured document to canonical-ordered Markdown (no DB, no LLM)
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
| Normalizing a raw skill token to canonical form | `skill_analytics.py` → `normalize_skill()` |
| Aggregating skills into importance tiers (High/Med/Low) + categories | `skill_analytics.py` → `aggregate_skill_frequency()` |
| Mapping a skill to its tech category | `skill_analytics.py` → `tech_category()` |
| Testing if a job lists a skill (any extraction field) | `skill_analytics.py` → `job_has_skill()` |
| Shared utilities | `utils.py` |
| Pydantic models for structured document artifacts | `schemas.py` |
| Snapshot profile + join LLM prose to structured data (résumé/cover build) | `document_builder.py` → `build_resume_document()`, `build_cover_document()` |
| Render a structured document to canonical Markdown | `document_assembler.py` → `assemble_resume_markdown()`, `assemble_cover_markdown()` |

## LLM Integration

See project memory note: the project uses the **OpenAI SDK** with multi-provider support (not the Anthropic SDK). Provider/model/API key are stored in the Config DB table and resolved at request time via `core/llm.py`.

`llm.py` supports three resolution paths:
1. **Active provider** (`get_openai_client`) — reads `llm_active_provider` from Config DB; API key from env `LLM_KEY_{PROVIDER_NAME}`.
2. **Named provider** (`get_client_for_named_provider`) — looks up a named entry from `named_providers` config; API key from env `LLM_KEY_{ID}`.
3. **User profile** (`get_client_for_profile`) — uses `user.llm_provider_type` / `user.llm_model`; API key from env `LLM_KEY_PROFILE_{user.id}`.

`call_llm` accumulates spend via `session_cost.add_cost(usage.cost)` on every response.

## Skill Matching and Hallucination Detection

- Skill matching between user skills and job requirements is **fully delegated to the LLM** — the full user skills list is injected into scoring/generation prompts via `{user.skills}` placeholders; no Python-side filtering occurs.
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

Defined in `db/database.py` as `Document`. Columns: `id`, `job_key`, `doc_type` ("resume"|"cover"), `structured_json`, `created_at`. Unique constraint on `(job_key, doc_type)`. Helpers: `Document.fetch(job_key, doc_type, db)`, `Document.upsert(job_key, doc_type, model, db)`.

### Known Issues / Phase 3a Caveat

A manual `.md` edit, eval, or refine mutates the flat `.md` file but does **not** update the stored `Document` — they diverge. This is the same trade-off as today's refine path diverging from the original generation. **Phase 3b** resolves this: field-level editing + structured eval/refine will make the structured document the single source of truth, with `.md` as a purely derived output.

## Key Invariants

- `Job` methods that call the LLM receive an already-constructed client + model string — they do not read config themselves.
- All DB writes inside `Job` methods use the session passed in; callers are responsible for commit/rollback.
- `refine_resume_md` passes `max_pages=1` to `generate_resume_pdf`; `render_pdf` auto-shrinks the print scale to fit one page (see `generator/CONTEXT.md`). The manual-edit path (`web/routers/jobs.py` `_put_document_markdown_sync`) also passes `max_pages=1`.
- `_refine_doc_md` uses `max_tokens=32768` to avoid truncation on rewrites.
