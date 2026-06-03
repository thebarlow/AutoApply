# prompts/ Context

LLM prompt templates used by scoring, generation, and extraction pipelines.

## Storage model (DB-backed)

Prompts live in the database, not in files. Two tables (defined in `db/database.py`):

- **`prompt_defaults`** — global factory defaults, one row per type (`type_key` → `content`).
- **`prompts`** — per-profile active slots, keyed by `(profile_id, type_key)`, holding `content` + a per-type `model` override.

`prompts/defaults/*.md` are **seed-only**: `init_db` (`db/seed.py` → `seed_prompt_defaults`) loads them into `prompt_defaults` when a row is missing, and they are **not read at runtime**. Editing a default `.md` only affects a fresh DB (or a `prompt_defaults` row that doesn't exist yet); to change an in-use default, edit the `prompt_defaults` row.

```
prompts/
├── defaults/               # SEED source for prompt_defaults (not read at runtime)
│   ├── scoring.md   resume.md   resume_eval.md   resume_refine.md
│   ├── cover.md     cover_eval.md   cover_refine.md
│   └── extraction.md   resume_parse.md
└── [root-level files]      # Dead legacy artifacts — unused, safe to delete
```

## Resolution & overrides

`core/user.py` `User.resolve_prompt(type_key)` reads the `prompts` row for the active profile. If the row is missing or its content is ≤ 10 words, it auto-repairs the row from `prompt_defaults` (within a SAVEPOINT), emits a `prompt_reset` SSE alert, and returns the default; it raises `PromptNotConfiguredError` when no usable default exists.

Per-profile editing is one slot per type (no file library): the dashboard (ProfileDetail → Prompts) edits a single prompt per type via the per-slot API in `web/routers/prompts.py` (`GET/PUT /api/prompts/{profile_id}/{type_key}`, `POST .../reset`, `GET /api/prompts/defaults/{type_key}`). The old file-upload / multi-file-library API and UI were removed. Existing file-based prompts were migrated into the `prompts` table by `db/seed.py` → `migrate_file_prompts_to_db`; leftover user `.md` files under `prompts/` are now unused.

## Routing Rules

| Prompt | type_key / seed file |
|---|---|
| Job scoring | `defaults/scoring.md` |
| Resume generation | `defaults/resume.md` |
| Resume evaluation (refinement loop) | `defaults/resume_eval.md` |
| Resume refinement (refinement loop) | `defaults/resume_refine.md` |
| Cover letter generation | `defaults/cover.md` |
| Cover letter evaluation (refinement loop) | `defaults/cover_eval.md` |
| Cover letter refinement (refinement loop) | `defaults/cover_refine.md` |
| Job description extraction | `defaults/extraction.md` |
| Resume parsing (profile ingestion) | `defaults/resume_parse.md` |

## Dead Files (safe to delete)

Root-level `prompts/*.md` files (and any per-profile override `.md` files left over from the pre-DB file model) are not imported by any Python module. Before deleting, verify with:
```
grep -r "prompts/" web/ core/ --include="*.py"
```
