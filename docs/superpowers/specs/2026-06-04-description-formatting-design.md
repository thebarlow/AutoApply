# Description Formatting — Compact Processed View + Collapsible Raw

**Date:** 2026-06-04
**Scope:** Frontend only — `react-dashboard/src/components/widgets/Settings.jsx`. No backend, schema, or API changes.

## Problem

The job-detail **Description** tab shows the LLM-extracted ("processed") description with every field stacked vertically: each label on its own line, each list rendered as full-height vertical bullets. The result is very tall when it could fit on roughly one screen. The Raw/Processed toggle also hides the processed content behind a click.

## Goal

A single unified Description view:
1. Compact **processed content** on top.
2. A collapsible **"Raw Description"** section beneath (collapsed by default).

No Raw/Processed toggle.

## Data (unchanged)

`job.extraction` (parsed `extraction_json`) with fields:

- Meta (short single values): `seniority`, `role_type`, `domain`, `work_arrangement`, `employment_type`
- Keyword lists (short tokens): `required_skills`, `preferred_skills`, `tech_stack`
- Sentence lists: `key_responsibilities`, `company_signals`

`job.description` holds the raw text. `job.extraction_json_exists` indicates whether extraction has run.

## Design

### 1. Compact `ExtractionView` (Settings.jsx ~line 74)

Rewrite the component body. Three render groups, each skipped entirely when empty:

**Meta row** — one wrapping line, present values joined by ` · `:
```
Senior · Backend · Fintech · Remote · Full-time
```
Skip empty fields (no empty separators). If all five empty, render nothing.

**Keyword chips** — for each of `required_skills`, `preferred_skills`, `tech_stack`: a small dim label, then chips wrapping inline, multiple per line. Chip style: `inline-block rounded bg-white/10 px-1.5 py-0.5` (matches existing `code` aesthetic). Empty list → skip that block.

**Sentence bullets** — `key_responsibilities`, `company_signals` stay as `list-disc list-inside` bulleted lists (full sentences; inlining hurts readability). Empty → skip.

Visual order: meta row → keyword blocks → sentence blocks.

### 2. Unified Description tab (Settings.jsx ~line 672–704)

Remove:
- `descView` state (line 444) and its reset effect (line 491).
- The Raw/Processed `SubToggle` (lines 675–682).
- The two `descView === 'raw'` / `descView === 'extracted'` conditional branches.

Keep the Process/Reprocess `GatedButton` and `actionError` line.

New content area:
- **Processed (top):** `job.extraction ? <ExtractionView data={job.extraction} /> : <p>No extraction yet.</p>` (existing placeholder text).
- **Raw (bottom):** native `<details>` element, collapsed by default. `<summary>` styled as a dim clickable row labeled "Raw Description" with a chevron indicator. Body = current raw block: `<p className="text-xs text-space-dim leading-relaxed whitespace-pre-wrap">{job.description || 'No description available.'}</p>`.

Native `<details>` is used rather than a JS toggle — no extra state, simpler.

## Out of Scope

- Backend extraction fields, schemas, prompts.
- Salary display (`ext_salary_min/max`) — shown elsewhere, unchanged.
- Other content tabs (resume, cover, score).

## Testing

Manual verification in the dashboard:
- Job with full extraction: meta on one line, skills as inline chips, responsibilities as bullets; Raw collapsed below; expands on click.
- Job with no extraction: "No extraction yet." above, raw still available below.
- Job with partial/empty fields: empty groups omitted cleanly, no stray separators.
