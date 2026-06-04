# Description Formatting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Description tab's Raw/Processed toggle with a single view: compact processed extraction on top, collapsible raw description beneath.

**Architecture:** Pure frontend change in one file (`react-dashboard/src/components/widgets/Settings.jsx`). Rewrite the `ExtractionView` component for a compact layout, then restructure the `description` content-tab JSX to drop the toggle and add a native `<details>` for raw text. No backend, schema, or data-shape changes.

**Tech Stack:** React 18, Tailwind CSS, Vite.

**Verification note:** This dashboard has no unit-test runner (only Playwright, no existing test files). Verification is via `npm run build` (catches syntax/JSX errors) plus manual inspection. Follow this established pattern — do not add a test framework.

---

### Task 1: Compact `ExtractionView`

**Files:**
- Modify: `react-dashboard/src/components/widgets/Settings.jsx:74-104` (the `ExtractionView` function)

- [ ] **Step 1: Replace the `ExtractionView` function**

Replace the entire existing function (lines 74-104) with this. Meta fields collapse to one ` · `-joined line, keyword lists become inline chips, sentence lists stay as bullets. Each group is skipped when empty.

```jsx
function ExtractionView({ data }) {
  const metaKeys = ['seniority', 'role_type', 'domain', 'work_arrangement', 'employment_type']
  const meta = metaKeys.map((k) => data[k]).filter((v) => v && String(v).trim())

  const chipGroups = [
    { key: 'required_skills', label: 'Required Skills' },
    { key: 'preferred_skills', label: 'Preferred Skills' },
    { key: 'tech_stack', label: 'Tech Stack' },
  ]
  const bulletGroups = [
    { key: 'key_responsibilities', label: 'Responsibilities' },
    { key: 'company_signals', label: 'Company Signals' },
  ]
  const asList = (v) => (Array.isArray(v) ? v.filter((x) => x && String(x).trim()) : [])

  return (
    <div className="flex flex-col gap-3">
      {meta.length > 0 && (
        <p className="text-xs text-space-text">{meta.join(' · ')}</p>
      )}

      {chipGroups.map(({ key, label }) => {
        const items = asList(data[key])
        if (items.length === 0) return null
        return (
          <div key={key}>
            <p className="text-xs font-semibold text-space-dim mb-1">{label}</p>
            <div className="flex flex-wrap gap-1">
              {items.map((v, i) => (
                <span key={i} className="inline-block rounded bg-white/10 px-1.5 py-0.5 text-xs text-space-text">{v}</span>
              ))}
            </div>
          </div>
        )
      })}

      {bulletGroups.map(({ key, label }) => {
        const items = asList(data[key])
        if (items.length === 0) return null
        return (
          <div key={key}>
            <p className="text-xs font-semibold text-space-dim mb-1">{label}</p>
            <ul className="list-disc list-inside text-xs space-y-0.5 text-space-text">
              {items.map((v, i) => <li key={i}>{v}</li>)}
            </ul>
          </div>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 2: Verify build**

Run: `cd react-dashboard && npm run build`
Expected: build succeeds, no errors.

- [ ] **Step 3: Commit**

```bash
git add react-dashboard/src/components/widgets/Settings.jsx
git commit -m "[refactor] Compact ExtractionView: meta inline, skills as chips"
```

---

### Task 2: Unified Description tab (drop toggle, add collapsible raw)

**Files:**
- Modify: `react-dashboard/src/components/widgets/Settings.jsx` — remove `descView` state (line 444), its reset (line 491), and rewrite the `description` content block (lines 672-705)

- [ ] **Step 1: Remove the `descView` state declaration**

Delete line 444:

```jsx
  const [descView, setDescView] = useState(() => job?.extraction_json_exists ? 'extracted' : 'raw')
```

- [ ] **Step 2: Remove the `descView` reset in the job-change effect**

Delete line 491:

```jsx
    setDescView(job?.extraction_json_exists ? 'extracted' : 'raw')
```

- [ ] **Step 3: Rewrite the `description` content block**

Replace the whole block (currently lines 672-705, `{contentTab === 'description' && ( ... )}`) with this. The Process/Reprocess button and `actionError` line are preserved; the `SubToggle` and `descView` branches are gone.

```jsx
      {contentTab === 'description' && (
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-end">
            <GatedButton
              action="score"
              onClick={handleAction}
              disabled={actionLoading || !promptOk}
              title={promptMissingTitle || undefined}
              className="px-3 py-1 rounded text-xs font-semibold transition-colors bg-purple-600 hover:bg-purple-500 text-white disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {actionLoading ? '…' : !promptOk ? 'Prompt not set' : job.extraction_json_exists ? 'Reprocess' : 'Process'}
            </GatedButton>
          </div>
          {actionError && <p className="text-xs text-red-400 break-words">{actionError}</p>}

          {job.extraction
            ? <ExtractionView data={job.extraction} />
            : <p className="text-xs text-space-dim">No extraction yet.</p>}

          <details className="border-t border-space-border pt-2">
            <summary className="text-xs font-semibold text-space-dim cursor-pointer select-none hover:text-space-text">
              Raw Description
            </summary>
            <p className="mt-2 text-xs text-space-dim leading-relaxed whitespace-pre-wrap">
              {job.description || 'No description available.'}
            </p>
          </details>
        </div>
      )}
```

- [ ] **Step 4: Verify no orphan references to `descView` remain**

Run: `cd react-dashboard && grep -rn descView src/`
Expected: no matches.

- [ ] **Step 5: Verify build**

Run: `cd react-dashboard && npm run build`
Expected: build succeeds, no errors.

- [ ] **Step 6: Manual check in the dashboard**

Run the app (`start.bat` from project root, or `cd react-dashboard && npm run dev`). Open a job's Description tab and confirm:
- Job with extraction: meta values on one line joined by ` · `, skills/tech as inline chips, responsibilities as bullets. "Raw Description" appears below, collapsed; clicking expands it.
- Job without extraction: "No extraction yet." shows above; raw still expandable below.
- No Raw/Processed toggle remains.

- [ ] **Step 7: Commit**

```bash
git add react-dashboard/src/components/widgets/Settings.jsx
git commit -m "[feat] Unified Description tab: processed view + collapsible raw"
```

---

## Self-Review

- **Spec coverage:** Meta inline (Task 1) ✓; keyword chips (Task 1) ✓; sentence bullets (Task 1) ✓; remove toggle + `descView` (Task 2 steps 1-3) ✓; processed-on-top + collapsible raw via `<details>` (Task 2 step 3) ✓; no-extraction placeholder (Task 2 step 3) ✓; empty-field skipping (Task 1 filters) ✓.
- **Placeholders:** none — all code blocks complete.
- **Type consistency:** `ExtractionView` keeps its `{ data }` prop; call site `<ExtractionView data={job.extraction} />` unchanged. `GatedButton`, `handleAction`, `actionLoading`, `promptOk`, `promptMissingTitle`, `actionError`, `job.extraction_json_exists` all reference existing identifiers in scope.
