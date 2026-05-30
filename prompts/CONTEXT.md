# prompts/ Context

LLM prompt templates used by scoring, generation, and extraction pipelines.

## Structure

```
prompts/
├── defaults/               # Canonical prompt defaults (read by the app at runtime)
│   ├── scoring.md
│   ├── resume.md
│   ├── resume_eval.md
│   ├── resume_refine.md
│   ├── cover.md
│   ├── cover_eval.md
│   ├── cover_refine.md
│   ├── extraction.md
│   └── resume_parse.md
└── [root-level files]      # Legacy / versioned iterations — NOT used by the app
```

**Important:** Only files in `prompts/defaults/` are the active defaults. Root-level files (`resume_1.md`, `cover_1.md`, `scoring_1.md`, `resume_parse_1.md`, etc.) are old versioning artifacts. They are not read at runtime and can be deleted once you confirm nothing references them.

## Per-Profile Overrides

Users can override any default prompt via the dashboard (ProfileDetail → Prompts accordion). Overrides are stored in the DB `Config` table, not in this directory. The app resolves prompts at request time: DB override → `prompts/defaults/{name}.md` fallback.

## Routing Rules

| Prompt | Default file |
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

Root-level files are not imported by any Python module. Before deleting, verify with:
```
grep -r "prompts/" web/ core/ --include="*.py"
```
