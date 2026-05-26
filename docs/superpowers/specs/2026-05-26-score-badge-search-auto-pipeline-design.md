# Design: Score Badge, Search, and Auto Intake Pipeline

**Date:** 2026-05-26

---

## 1. Score Badge on Job Cards

### What
Display the `final_score` (float 0–1) as a color-coded percentage on each `JobCard`.

### Props
`JobCard` receives a new `score` prop (float or null/undefined). `Pipeline` passes `job.final_score` for each job.

### Rendering
- Positioned between the doc icons and the status icon in the existing flex row.
- Format: integer percentage, e.g. `75%`.
- Color thresholds:
  - ≥ 70% → `text-green-400`
  - 40–69% → `text-yellow-400`
  - < 40% → `text-red-400`
- Renders nothing when `score` is null or undefined (job not yet scored).

### No API changes needed
`final_score` is already included in `job.serialize()` and present in the jobs payload.

---

## 2. Search in Inbox and Archives Tabs

### What
A text input above the job list in `Pipeline`, filtering visible jobs by title and company.

### Behavior
- Per-tab state: each tab (Inbox, Archives) has independent search text.
- Search clears when switching tabs.
- Client-side filtering via `useMemo` on `tabJobs[activeTab]`.
- Match condition: lowercased `job.title` or `job.company` contains the lowercased query string.
- Placeholder: `"Search jobs…"`.

### Styling
Translucent dark input (`bg-white/5 border border-white/10 rounded-md`) consistent with existing UI.

### No API changes needed
All filtering is client-side.

---

## 3. Auto Intake Pipeline

### What
When a new job is ingested (via browser extension or API scraper), automatically run description extraction followed by scoring — without user intervention.

### New module: `web/intake_pipeline.py`

Single public function:

```python
def run_pipeline(job_key: str) -> None
```

Steps:
1. Open a new `SessionLocal()` DB session.
2. Load LLM client and config from DB.
3. Run description extraction (same logic as `extract_description` endpoint):
   - Uses `llm_status.start/finish(job_key, "description")` for SSE visibility.
   - Sets `job.unread_indicator = "error"` and `job.last_result_error` on failure.
   - Emits SSE after completion.
4. If description extraction succeeds, run scoring (same logic as `score_job_endpoint`):
   - Uses `llm_status.start/finish(job_key, "score")`.
   - Sets error state on failure.
   - Emits SSE after completion.
5. Description failure skips scoring gracefully (no crash).
6. Always closes the DB session in a `finally` block.

### Refactor in `web/routers/jobs.py`

Extract the inner LLM logic from `extract_description` and `score_job_endpoint` into private helpers that `intake_pipeline.py` can also call:

- `_do_extract_description(job, db) -> None`
- (scoring already has `_do_generate_resume`/`_do_generate_cover` as a pattern to follow)

Route handlers delegate to these helpers. No logic duplication.

### Integration points

**`web/routers/scraper.py` — `_run_in_background`:**
After `job.intake()` and SSE emit, call `run_pipeline(job.job_key)` in the same background thread (already off the request thread).

**`web/routers/scraper.py` — `stage_job`:**
After `job.intake()` and SSE emit, spawn a new `threading.Thread(target=run_pipeline, args=(job.job_key,), daemon=True)`.

### Error handling
- Per-step: failure in description extraction sets error state and skips scoring.
- Errors are surfaced via the existing `unread_indicator = "error"` + SSE pattern.
- No retry logic.

---

## Files Changed

| File | Change |
|---|---|
| `react-dashboard/src/components/shared/JobCard.jsx` | Add `score` prop, render color-coded percentage pill |
| `react-dashboard/src/components/widgets/Pipeline.jsx` | Pass `score`, add per-tab search state and input, filter job list |
| `web/intake_pipeline.py` | New module — `run_pipeline(job_key)` |
| `web/routers/jobs.py` | Extract `_do_extract_description` helper; route handlers delegate to it |
| `web/routers/scraper.py` | Call `run_pipeline` after intake in both code paths |
