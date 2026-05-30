# core/ Context

Shared business logic. No framework dependencies — used by `web/`, `scraper/`, and tests.

## Files

```
core/
├── job.py          # Job entity + all LLM-driven methods (score, generate, extract, eval, refine)
├── user.py         # User entity; profile load/save, prompt resolution, degree/skills helpers
├── llm.py          # LLM client construction and model resolution
├── utils.py        # Misc helpers (sanitization, path utilities, PDF rendering)
└── session_cost.py # Thread-safe accumulator for per-session LLM spend (from usage.cost)
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
| Shared utilities | `utils.py` |

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

## Key Invariants

- `Job` methods that call the LLM receive an already-constructed client + model string — they do not read config themselves.
- All DB writes inside `Job` methods use the session passed in; callers are responsible for commit/rollback.
- `refine_resume_md` passes `max_pages=None` to `generate_resume_pdf` — no page limit during refinement turns.
- `_refine_doc_md` uses `max_tokens=32768` to avoid truncation on rewrites.
