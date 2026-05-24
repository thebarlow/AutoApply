# Profile + Prompt Modal UI Tweaks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make profile accordions closed-by-default with session-scoped memory, add a `processed description` chip to the PromptModal, and add a pop-out full-viewport editor for the Prompt Text field.

**Architecture:** Three localized changes inside one file (`react-dashboard/src/components/widgets/ProfileDetail.jsx`). No new files, no backend changes, no new dependencies. Shared React state and refs let the pop-out editor reuse the existing `content`/`textareaRef`/drag handlers so edits flow back to PromptModal on close.

**Tech Stack:** React 18 (function components + hooks), Vite, Tailwind CSS, `sessionStorage` Web API.

**Spec:** `docs/superpowers/specs/2026-05-24-profile-prompt-ui-tweaks-design.md`

**Manual-only testing:** This project has no React test runner configured. Verification is by running the dashboard (`npm --prefix react-dashboard run dev` or `start.bat`) and exercising the UI. Each task ends with explicit manual-check steps and a commit.

---

## Task 1: AccordionSection — closed by default with sessionStorage memory

**Files:**
- Modify: `react-dashboard/src/components/widgets/ProfileDetail.jsx:25-44` (AccordionSection)
- Modify: `react-dashboard/src/components/widgets/ProfileDetail.jsx` — every `<AccordionSection ...>` call site (currently lines 151, 226, 326, 409, 505, 594, 940, 1022)

- [ ] **Step 1: Replace the AccordionSection component**

Find the existing `function AccordionSection({ title, editButton, children }) { ... }` block (lines 25-44) and replace it with:

```jsx
function AccordionSection({ id, title, editButton, children }) {
  const storageKey = id ? `profile-accordion:${id}` : null
  const [open, setOpen] = useState(() => {
    if (!storageKey) return false
    try {
      return sessionStorage.getItem(storageKey) === '1'
    } catch {
      return false
    }
  })

  const toggle = () => {
    setOpen(prev => {
      const next = !prev
      if (storageKey) {
        try { sessionStorage.setItem(storageKey, next ? '1' : '0') } catch {}
      }
      return next
    })
  }

  return (
    <div className="border border-space-border rounded-lg overflow-hidden">
      <div
        className="flex items-center justify-between px-3 py-2.5 bg-white/[0.03] cursor-pointer select-none"
        onClick={toggle}
      >
        <span className="text-xs font-semibold uppercase tracking-widest text-space-dim">{title}</span>
        <div className="flex items-center gap-2">
          {editButton && <span onClick={e => e.stopPropagation()}>{editButton}</span>}
          <span className="text-space-dim">
            <ChevronDown open={open} />
          </span>
        </div>
      </div>
      {open && <div className="p-3">{children}</div>}
    </div>
  )
}
```

Notes:
- Defaults to closed when no `id` is given or when nothing is stored.
- `try/catch` around `sessionStorage` access protects against private-browsing edge cases that throw.

- [ ] **Step 2: Add `id` prop to every AccordionSection call site**

Update all eight call sites to add a stable kebab-case `id`. Use the Edit tool, one per call site:

| Line (approx) | Title (current) | id to add |
|---|---|---|
| 151 | `"Identity"` | `"identity"` |
| 226 | `"Skills"` | `"skills"` |
| 326 | `"Experience"` | `"experience"` |
| 409 | `"Education"` | `"education"` |
| 505 | `"Projects"` | `"projects"` |
| 594 | `"Job Preferences"` | `"job-preferences"` |
| 940 | `"Prompts"` | `"prompts"` |
| 1022 | `"LLM Config"` | `"llm-config"` |

For each, change e.g.

```jsx
<AccordionSection title="Identity" editButton={<EditBtn onClick={openModal} />}>
```

to

```jsx
<AccordionSection id="identity" title="Identity" editButton={<EditBtn onClick={openModal} />}>
```

(and so on for the others — keep `editButton` if present).

After editing, grep to confirm no `<AccordionSection ` remains without an `id`:

```bash
grep -n "<AccordionSection " react-dashboard/src/components/widgets/ProfileDetail.jsx
```

Expected: every line shows both `id="..."` and `title="..."`.

- [ ] **Step 3: Manual verification**

1. Start the dashboard if not running: `npm --prefix react-dashboard run dev` (or use `start.bat`).
2. Open the User Profile screen.
3. Confirm: all eight sections are collapsed on first load (only the title bars are visible).
4. Click Skills to open. Navigate to another dashboard tab, then back. Skills should still be open.
5. Open browser DevTools → Application → Session Storage. Confirm a key `profile-accordion:skills` with value `1` exists.
6. Click Skills again to close. Confirm value flips to `0`.
7. Refresh the page (F5). Confirm all sections are collapsed again (sessionStorage persists per tab — values `0` produce closed; this is fine).
8. Open Skills, then close the browser tab, then re-open the dashboard in a new tab. Confirm Skills is closed (session-scoped, not localStorage).

- [ ] **Step 4: Commit**

```bash
git add react-dashboard/src/components/widgets/ProfileDetail.jsx
git commit -m "[feat] Profile accordions closed by default with session memory"
```

---

## Task 2: Add `processed description` chip to JOB_CHIPS

**Files:**
- Modify: `react-dashboard/src/components/widgets/ProfileDetail.jsx:660-667` (JOB_CHIPS array)

- [ ] **Step 1: Add the new chip entry**

Find the current `JOB_CHIPS` constant:

```jsx
const JOB_CHIPS = [
  { label: 'title', token: '{job.title}' },
  { label: 'company', token: '{job.company}' },
  { label: 'location', token: '{job.location}' },
  { label: 'salary', token: '{job.salary}' },
  { label: 'description', token: '{job.description}' },
  { label: 'full job', token: '{job}' },
]
```

Replace it with:

```jsx
const JOB_CHIPS = [
  { label: 'title', token: '{job.title}' },
  { label: 'company', token: '{job.company}' },
  { label: 'location', token: '{job.location}' },
  { label: 'salary', token: '{job.salary}' },
  { label: 'description', token: '{job.description}' },
  { label: 'processed description', token: '{job.extracted_description}' },
  { label: 'full job', token: '{job}' },
]
```

- [ ] **Step 2: Manual verification**

1. Open the User Profile screen → expand Prompts → click any prompt card (e.g., Resume Generation).
2. In the PromptModal, confirm a `processed description` chip appears in the Job row, between `description` and `full job`. Same blue styling as siblings.
3. Drag the chip into the Prompt Text editor. Confirm the token `{job.extracted_description}` is inserted at the drop position.

- [ ] **Step 3: Commit**

```bash
git add react-dashboard/src/components/widgets/ProfileDetail.jsx
git commit -m "[feat] Add processed-description chip to prompt modal"
```

---

## Task 3: Pop-out full-viewport editor for Prompt Text

**Files:**
- Modify: `react-dashboard/src/components/widgets/ProfileDetail.jsx` — `PromptModal` component (lines ~698-926)

This task is one logical UI change. Build it incrementally: add the state and button first, then extract the editor + chip tray into a shared snippet rendered in either the inline or pop-out location.

- [ ] **Step 1: Add pop-out state to PromptModal**

In `PromptModal`, locate the existing `useState` block (just after `const label = PROMPT_TYPE_LABELS[typeKey]` around line 699-714). Add this line near the other `useState` declarations:

```jsx
const [popOut, setPopOut] = useState(false)
```

- [ ] **Step 2: Extract the chip tray and editor into render helpers**

Inside `PromptModal`, just above the `return (...)` statement (around line 798), add two render helpers so the same JSX can appear inline or inside the overlay. The chip tray currently lives at lines 841-881 (Zone 3); the editor at lines 883-901 (Zone 4).

```jsx
const renderChipTray = () => (
  <div className="flex flex-col gap-2">
    <label className="text-xs font-semibold uppercase tracking-widest text-space-dim">Insert Variable</label>
    <div className="flex flex-col gap-1.5">
      <p className="text-xs text-space-dim">User</p>
      <div className="flex flex-wrap gap-1.5">
        {USER_CHIPS.map(({ label: l, token }) => {
          const tipValue = resolveTokenValue(token, profileData)
          return (
            <div key={token} className="relative group">
              <div
                draggable
                onDragStart={(e) => e.dataTransfer.setData('text/plain', token)}
                className="px-2 py-0.5 rounded-full border border-purple-500/40 bg-purple-500/10 text-xs text-purple-300 cursor-grab active:cursor-grabbing select-none"
              >
                {l}
              </div>
              <div className="absolute bottom-full left-0 mb-1.5 z-50 w-56 bg-[#12121f] border border-space-border rounded-lg px-2.5 py-2 shadow-xl pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity duration-100">
                <p className="text-[10px] font-mono break-all text-space-text leading-relaxed">
                  {tipValue || <span className="italic text-space-dim/50">empty</span>}
                </p>
              </div>
            </div>
          )
        })}
      </div>
      <p className="text-xs text-space-dim mt-1">Job</p>
      <div className="flex flex-wrap gap-1.5">
        {JOB_CHIPS.map(({ label: l, token }) => (
          <div
            key={token}
            draggable
            onDragStart={(e) => e.dataTransfer.setData('text/plain', token)}
            className="px-2 py-0.5 rounded-full border border-blue-500/40 bg-blue-500/10 text-xs text-blue-300 cursor-grab active:cursor-grabbing select-none"
          >
            {l}
          </div>
        ))}
      </div>
    </div>
  </div>
)

const renderEditor = (extraTextareaClass = '') => {
  if (loadingContent) return <p className="text-xs text-space-dim">Loading…</p>
  if (contentError) return <p className="text-xs text-red-400">{contentError}</p>
  return (
    <textarea
      ref={textareaRef}
      rows={14}
      className={inputClass + ' resize-y font-mono text-xs ' + extraTextareaClass}
      value={content}
      onChange={(e) => setContent(e.target.value)}
      onDrop={handleDrop}
      onDragOver={handleDragOver}
      placeholder={selectedFile ? '' : 'Select a file above to edit'}
      disabled={!selectedFile}
    />
  )
}
```

Notes:
- Same `textareaRef` is used in both call sites. Because the textarea is rendered in only one place at a time (gated by `popOut`), React assigns the ref to whichever instance is mounted — drag-drop offset math keeps working.

- [ ] **Step 3: Replace inline chip tray (Zone 3) with helper, gated on `!popOut`**

Find Zone 3 (the `{/* Zone 3: Chip tray */}` block, lines ~841-881) and replace the **entire** block with:

```jsx
{/* Zone 3: Chip tray (hidden while pop-out is open) */}
{!popOut && renderChipTray()}
```

- [ ] **Step 4: Replace inline editor (Zone 4) with helper + pop-out button, gated on `!popOut`**

Find Zone 4 (the `{/* Zone 4: Editor */}` block, lines ~883-901) and replace the **entire** block with:

```jsx
{/* Zone 4: Editor (hidden while pop-out is open) */}
{!popOut && (
  <div className="flex flex-col gap-1.5 flex-1">
    <div className="flex items-center justify-between">
      <label className="text-xs font-semibold uppercase tracking-widest text-space-dim">Prompt Text</label>
      <button
        type="button"
        onClick={() => setPopOut(true)}
        title="Open full-viewport editor"
        className="text-space-dim hover:text-space-text p-1 rounded hover:bg-white/5 transition-colors"
      >
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
          <path d="M10 2h4v4" />
          <path d="M14 2L8.5 7.5" />
          <path d="M6 14H2v-4" />
          <path d="M2 14l5.5-5.5" />
        </svg>
      </button>
    </div>
    {renderEditor()}
  </div>
)}
```

- [ ] **Step 5: Render the pop-out overlay**

Find the closing `</div>` of the outermost PromptModal wrapper (the `<div className="fixed inset-0 z-50 ...">` that opens around line 800; its matching close is around line 924, just before the final `)`). Immediately after that closing tag and before the final `)`, add a sibling overlay so it sits above the modal in the DOM. The return becomes a fragment:

Change the opening `return (` and the structure from:

```jsx
return (
  <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
    {/* ... existing modal contents ... */}
  </div>
)
```

to:

```jsx
return (
  <>
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      {/* ... existing modal contents unchanged ... */}
    </div>
    {popOut && (
      <div className="fixed inset-0 z-[60] flex flex-col bg-[#0a0a14]">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-space-border shrink-0">
          <span className="text-sm font-semibold text-space-text">{label} — Full Editor</span>
          <button
            onClick={() => setPopOut(false)}
            className="text-space-dim hover:text-space-text text-lg leading-none"
            title="Close full editor"
          >
            ×
          </button>
        </div>
        {/* Body: chip tray + full-viewport editor */}
        <div className="flex-1 flex flex-col gap-3 p-4 min-h-0">
          {renderChipTray()}
          <div className="flex flex-col gap-1.5 flex-1 min-h-0">
            <label className="text-xs font-semibold uppercase tracking-widest text-space-dim">Prompt Text</label>
            {renderEditor('flex-1 !h-full')}
          </div>
        </div>
      </div>
    )}
  </>
)
```

Notes:
- `z-[60]` sits above PromptModal's `z-50` and any other overlays.
- `min-h-0` on flex children allows the textarea to actually fill remaining space instead of overflowing.
- `!h-full` overrides the `rows={14}` height so the textarea stretches to the parent's height in the pop-out only.
- No Save button — closing returns to PromptModal where existing Save handles persistence.

- [ ] **Step 6: Manual verification**

1. Open the User Profile screen → expand Prompts → click any prompt card (e.g., Resume Generation).
2. In the PromptModal, confirm a small pop-out icon appears in the upper-right of the Prompt Text label row.
3. Type some unique text (e.g., `SENTINEL_ABC`) in the inline editor.
4. Click the pop-out icon. The full-viewport overlay appears with the chip tray visible and the editor stretched to the viewport. `SENTINEL_ABC` is present.
5. In the pop-out, drag the `processed description` chip into the editor. Confirm `{job.extracted_description}` is inserted.
6. Add more typed text in the pop-out (e.g., `EDITED_IN_POPOUT`).
7. Click × to close the pop-out. The PromptModal reappears; inline editor shows both `SENTINEL_ABC`, the inserted token, and `EDITED_IN_POPOUT`.
8. Click Save. Confirm save succeeds (modal closes, no error). Re-open the same prompt and verify the new content is persisted on disk.
9. Verify the rest of the PromptModal (file selector, model override, upload) still works while the pop-out is closed.

- [ ] **Step 7: Commit**

```bash
git add react-dashboard/src/components/widgets/ProfileDetail.jsx
git commit -m "[feat] Add pop-out full-viewport editor to PromptModal"
```

---

## Done

Three commits land on the current branch (`feat/job-card-llm-indicators`). No backend changes, no schema migrations, no new files.
