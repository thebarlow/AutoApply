# 4B-2 — Per-section résumé refinement engine (Profile Schema Engine #4B-2)

**Date:** 2026-06-23
**Status:** Design approved, spec under review
**Parent:** Profile Schema Engine #4 (full tree swap) → 4B (production wiring) → 4B-2
**Prior:** 4B-1 (tree-v1 in production) — `docs/superpowers/specs/2026-06-22-4b-tree-v1-production-wiring-design.md`
**Release constraint:** merges to LOCAL `main` only — do NOT push `main` until the whole swap (#4–#6 and #5) is complete.

## Problem

4B-1 wired tree-v1 résumés into production but left refinement on an **interim** strategy:
`_refine_doc_md` re-authors **every** `llm_output` section on each refine turn, driven by the
existing whole-document eval (`_evaluate_body` → `EvalResponse{score, issues}`, one LLM call
over the whole résumé → a single score + a flat issues list). That wastes tokens re-writing
sections that are already good and gives the generator no section-targeted critique.

4B-2 replaces the interim strategy with a **per-section** engine for tree-v1 résumés: one
sectioned-eval call scores each regenerable section, and only sub-threshold sections are
regenerated (with their own issues injected as critique). Cover letters and legacy
`ResumeDocument` rows keep the existing whole-document loop unchanged.

## Scope

- **In:** the eval-driven **auto-refine loop** for tree-v1 résumés (`_run_doc_refinement`'s
  résumé path).
- **Out — stays on the 4B-1 interim path / deferred:**
  - **User feedback-refine** (`run_user_feedback_refine` → `_refine_doc_md`): node-targeted,
    UI-driven. It belongs with the tree-aware DocumentModal — **deferred to 4D**. 4B-2 does
    not change `_refine_doc_md`.
  - **Cover letters:** always whole-document eval/refine. Untouched.
  - **Legacy `ResumeDocument` résumé rows:** no tree → whole-document loop. Untouched.
  - Per-section threshold configuration/UI (4B-2 reuses the existing single knob).
  - Per-section best-turn restore (4B-2 restores the best **whole-document** turn).

## Decisions (from brainstorming)

- **Stop rule:** the loop stops when **every regenerable section ≥ threshold**, or `max_turns`
  is reached.
- **Overall score:** the turn's recorded score is the **min** of the regenerable sections'
  scores. Best-turn restore picks the turn with the **highest min**.
- **Threshold:** every section uses the existing single user knob
  `resume_refine_pass_score` (default 0.80). No new config, no migration.
- **Section identity / mapping:** by **section name** (the tree `SectionNode.name`, which is
  the `## Heading` the renderer emits and is unique within a résumé). Results map back to tree
  sections by name.
- **Scored set:** only **regenerable** sections — those with at least one unlocked
  `llm_output` field (`_outputable` per `core/section_generator.py`). Non-regenerable sections
  (contact/header, education — not `llm_output`) are never scored or regenerated.
- **Sectioned-eval prompt:** a **new** prompt key (`resume_eval_sectioned`), seeded in
  `prompts/defaults/`. `resume_eval` is untouched (still used by legacy résumé eval + cover).

## Components

### 1. Schemas (`core/schemas.py`)

```python
class SectionScore(BaseModel):
    section: str = ""              # matches a tree SectionNode.name
    score: float = 0.0            # clamped to [0,1] via the existing validator pattern
    issues: list[Issue] = Field(default_factory=list)

class SectionEvalResponse(BaseModel):
    sections: list[SectionScore] = Field(default_factory=list)
```

Reuses the existing `Issue` model and the `[0,1]` clamp validator used by `EvalResponse`.

### 2. Sectioned-eval prompt (`prompts/defaults/resume_eval_sectioned.md`)

Mirrors `resume_eval`'s job/credential context and rubric, but:
- receives `{current_document}` (the rendered résumé markdown, `## Section` headings intact),
- receives `{sections_to_score}` — a newline list of the regenerable section names,
- returns `{"sections": [{"section": "<name>", "score": 0.0, "issues": [{"category","description"}]}]}`,
  one entry per name in `{sections_to_score}`.

Seeded the same way other defaults are (DB-backed; `prompts/defaults/` is seed-only). The new
key must be resolvable via `user.resolve_prompt("resume_eval_sectioned")`; add it to the prompt
seed/registry exactly like the existing `resume_eval`.

### 3. Eval method (`core/job.py`)

`evaluate_resume_sections(self, eval_prompt, user, client, model) -> dict[str, dict]`:
- loads the rendered résumé body (same source as `_evaluate_doc_md`),
- computes the regenerable section-name set from the **stored tree-v1 doc**
  (`deserialize_document_tree` → sections with an unlocked `llm_output` field),
- substitutes `{current_document}` and `{sections_to_score}`, runs one `call_llm`, parses
  `SectionEvalResponse`,
- returns `{section_name: {"score": float, "issues": list[dict]}}` for the scored sections,
  dropping any returned name not in the regenerable set (defensive).

### 4. Regeneration filter + critique (`core/section_generator.py`)

Extend `generate_resume_by_section` with two **optional** params (defaults preserve current
behavior, so 4B-1's callers are unaffected):

```python
def generate_resume_by_section(
    root, job_ctx, client, model, resolve=None,
    only_sections: "set[str] | None" = None,        # regenerate only these section names
    critiques: "dict[str, list[dict]] | None" = None,  # per-section issues to fix
) -> dict[str, Value]:
```

- When `only_sections` is given, sections whose `name` is not in it are skipped (not authored).
- When `critiques[section.name]` exists, the section/list prompt gains a
  `FIX THESE ISSUES:\n- …` block built from the issue descriptions, instructing a targeted
  rewrite. (Added in `_build_scalar_prompt`/`_build_list_prompt` via an optional `critique`
  arg.)

### 5. Authored-value carry-forward helper

`authored_values_from_tree(root: RootNode) -> dict[str, Value]`: walk a (document) tree and
return `field_id → value` for every `llm_output` field. Used to **seed** the cumulative
`authored` map so that, when only failing sections are regenerated, passing sections keep their
current (already-refined) text. Lives next to the tree code (`core/document_tree.py` or a small
sibling) and is pure.

### 6. Orchestrator (`web/intake_pipeline.py`)

`_run_doc_refinement` dispatches: when `doc_type == "resume"` and the stored row is tree-v1, it
calls a new `_run_resume_section_refinement(...)`; otherwise the existing whole-document loop
runs unchanged. The per-turn snapshot + best-turn-restore helpers (currently closures in
`_run_doc_refinement`) are reused — extract the parts the new routine needs to module level
(e.g. a `_save_turn_snapshot(job_key, doc_type, n, profile_id)` and the restore/render path,
which already partly exists as `_render_doc_from_json` from 4B-1). No behavior change to the
existing loop beyond the dispatch + any pure extraction.

## Data flow (per turn) — `_run_resume_section_refinement`

1. Seed `authored = authored_values_from_tree(deserialize_document_tree(stored_row))`.
2. Snapshot turn 0 (the initially generated tree). 
3. For turn = 1..max_turns:
   a. `scores = job.evaluate_resume_sections(...)` → `{section: {score, issues}}`.
   b. `min_score = min(s["score"] for s in scores.values())` (or 0 if no regenerable sections —
      then there is nothing to refine: stop). Record `min_score` in the eval log; set the job's
      `resume_eval_score`, turns, log; emit.
   c. `failing = {name for name, s in scores.items() if s["score"] < pass_score}`.
   d. If `failing` is empty → success, stop.
   e. If `turn == max_turns` → stop (restore best below).
   f. `critiques = {name: scores[name]["issues"] for name in failing}`.
   g. `new_vals = generate_resume_by_section(root, job_ctx, client, model, resolve=resolve,
      only_sections=failing, critiques=critiques)`; `authored.update(new_vals)`.
   h. `doc_tree = build_resume_document_tree(root, authored)`; persist `serialize_document_tree`
      under tree-v1; re-render (`write_resume_markdown` + `generate_resume_pdf`).
   i. Snapshot turn N.
4. Restore the best-by-min turn (re-persist that snapshot + re-render), as the existing loop's
   `_restore_best` does, keyed on the recorded min score.

`job_ctx` is built the same way 4B-1's generation does — `build_resume_prompt(user,
prompt_content, db)` with the `{job.extracted_description}` token — so refine and generation
share context. `resolve` is the same `resolve_profile_tokens` + `_apply_template` closure.

## Error handling

- **Per-section regen failure:** `generate_resume_by_section` already swallows a failed
  section's LLM call and contributes nothing for it — that section keeps its carried-forward
  value. Never crashes the turn.
- **Eval call failure / unparseable JSON:** abort the turn, restore best, mark
  `last_result_error` + emit — mirrors the existing loop's exception path.
- **No regenerable sections:** nothing to refine — record the (possibly trivial) state and
  stop without error.
- **A section returned by the eval that isn't a current regenerable section name:** dropped
  (defensive; rename/hallucination safety).

## Back-compat

- Cover and legacy `ResumeDocument` résumé rows: unchanged whole-document loop.
- `resume_eval` prompt and `EvalResponse` schema: unchanged.
- `generate_resume_by_section`'s existing call sites (4B-1 generation + interim `_refine_doc_md`)
  keep working via the defaulted new params. (4B-1's `_refine_doc_md` interim re-author-all
  remains for feedback-refine until 4D; the auto-loop no longer reaches it for tree-v1.)

## Testing

- **Schema:** `SectionEvalResponse` parses a per-section JSON; scores clamp to `[0,1]`.
- **Eval method:** `evaluate_resume_sections` maps results to section names, requests only
  regenerable sections, and drops unknown returned names.
- **Regen filter:** `generate_resume_by_section(only_sections={"Summary"})` authors only
  `Summary`'s field ids; other sections' ids are absent from the result. With
  `critiques={"Summary":[…]}`, the built prompt contains the fix-these-issues block (assert on
  the prompt string via the existing prompt-builder seam).
- **Carry-forward:** `authored_values_from_tree` returns every `llm_output` field's value and
  nothing else.
- **Engine:** a 2-regenerable-section fixture (A scores ≥ threshold, B below) with stubbed
  eval + stubbed `generate_resume_by_section`: turn 1 regenerates **only B**; once B passes the
  loop stops; the recorded turn score is the **min**; best-by-min restore picks the highest-min
  turn. Assert the persisted row stays tree-v1 and the `.md` is frontmatter-free.
- **Back-compat:** a cover and a legacy `ResumeDocument` résumé still run the whole-document
  loop (the dispatch does not route them to the section engine).

## Out of scope

- Per-section threshold config / UI; per-section best-turn restore.
- Tree-aware user feedback-refine (4D).
- ATS gate rework (4C).
- Cover-letter sectioning.
