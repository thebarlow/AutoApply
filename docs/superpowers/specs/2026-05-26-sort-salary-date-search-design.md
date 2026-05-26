# Design: Sort, Salary Parsing, Date/Salary on Cards, Search Persistence

**Date:** 2026-05-26

---

## 1. DB / Model Changes

### New columns on `Job`
- `ext_salary_min` (Float, nullable) — parsed salary lower bound from LLM extraction
- `ext_salary_max` (Float, nullable) — parsed salary upper bound from LLM extraction

### `applied_at` in serialize
`applied_at` already exists on the model but is absent from `serialize()`. Add it.

### Migration
Manual `ALTER TABLE` on `auto_apply.db` (per existing convention in `db/CONTEXT.md`):
```sql
ALTER TABLE jobs ADD COLUMN ext_salary_min REAL;
ALTER TABLE jobs ADD COLUMN ext_salary_max REAL;
```

---

## 2. Salary Parsing — Backend (`web/routers/jobs.py`)

`_do_extract_description` already parses a JSON blob from the LLM. Add parsing for two new fields:

```python
job.ext_salary_min = data.get("salary_min")   # float or None
job.ext_salary_max = data.get("salary_max")   # float or None
```

The user's extraction prompt must be updated to instruct the LLM to return `salary_min` and `salary_max` as floats (annual, USD or null for undisclosed). The backend code is permissive — if the fields are absent from the JSON, they remain null.

---

## 3. Salary Parsing — Frontend Fallback (`Pipeline.jsx`)

A `parseSalary(str)` utility function handles the raw scraped `salary` string when `ext_salary_min` is null.

### Parsing rules
- Extract all numbers (strip `$`, `,`, convert `k`/`K` → ×1000)
- If two numbers found → `{ min, max }`
- If one number found → `{ min: n, max: n }`
- If no numbers (e.g. "Competitive", "Undisclosed", "") → `null`

### Display priority
```
resolvedMin = ext_salary_min ?? parseSalary(job.salary)?.min ?? null
resolvedMax = ext_salary_max ?? parseSalary(job.salary)?.max ?? null
```

### Formatting
- Range: `$80K–$100K`
- Flat: `$90K`
- Nothing: render nothing on the card

---

## 4. Sort Control (`Pipeline.jsx`)

### State
`sortBy`: `'score' | 'date' | 'salary'`, default `'score'`. Tab-independent (single value).

### UI
Three buttons rendered above the search input, labeled Score / Date / Salary. Active button uses `text-purple-400 border-b border-purple-400`, inactive uses `text-space-dim hover:text-space-text`.

### Sort logic (applied via `useMemo` on `tabJobs[activeTab]` BEFORE search filtering)

**Score** (default): `final_score` descending, nulls last.

**Date**: Resolve date as `applied_at || scraped_at`. Sort descending (most recent first). Both fields are ISO 8601 strings — string comparison is correct.

**Salary**: Resolve salary as `ext_salary_min ?? parseSalary(job.salary)?.min ?? null`. Sort descending, nulls last.

### Pipeline data flow
```
tabJobs[activeTab]
  → sortedJobs   (sortBy useMemo)
  → visibleJobs  (search filter useMemo, depends on sortedJobs)
```

---

## 5. Job Card Metadata Row (`JobCard.jsx`)

Add a second metadata line below the company name showing salary and date.

### Date display
- If `applied_at` is set: `Applied MM/DD/YY`
- Else if `scraped_at` is set: `Added MM/DD/YY`
- Else: nothing
- Parse using `new Date(isoString)` → `.toLocaleDateString('en-US', { month: 'numeric', day: 'numeric', year: '2-digit' })`

### Salary display
- Use resolved salary (ext > scraped fallback) per section 3
- Show `$80K–$100K` or `$90K`
- If null: show nothing

### Layout
```
[title                              ]
[company          ]
[salary (if any)         date (if any)]
```
Salary and date both `text-xs text-space-dim`. They sit in a flex row with `justify-between`.

### Props added to `JobCard`
- `appliedAt`: string or null
- `scrapedAt`: string or null
- `salaryMin`: float or null (ext_salary_min)
- `salaryMax`: float or null (ext_salary_max)
- `salaryRaw`: string or null (raw job.salary)

`Pipeline` passes these from the job object.

---

## 6. Search Persistence on Tab Switch

Remove the two `setSearchInbox('')` and `setSearchArchives('')` calls from `handleTabChange` in `Pipeline.jsx`. Each tab retains its own search query when the user switches.

---

## Files Changed

| File | Change |
|---|---|
| `core/job.py` | Add `ext_salary_min`, `ext_salary_max` Float columns; add `applied_at`, `ext_salary_min`, `ext_salary_max` to `serialize()` |
| `web/routers/jobs.py` | Parse `salary_min`/`salary_max` from extraction JSON in `_do_extract_description` |
| `react-dashboard/src/components/shared/JobCard.jsx` | Add salary/date metadata row; accept new props |
| `react-dashboard/src/components/widgets/Pipeline.jsx` | Add sort control + `sortedJobs` useMemo; pass new props to JobCard; remove search-clear-on-tab-switch |
| `auto_apply.db` | Manual migration: add `ext_salary_min`, `ext_salary_max` columns |
