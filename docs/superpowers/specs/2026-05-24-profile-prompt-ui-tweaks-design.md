# Profile + Prompt Modal UI Tweaks

**Date:** 2026-05-24
**Scope:** `react-dashboard/src/components/widgets/ProfileDetail.jsx`

Three small UX improvements to the User Profile screen and its Prompt modal.

## 1. Accordion sections — closed by default with session-scoped memory

**Current behavior:** `AccordionSection` initializes `useState(true)` (open). State is lost whenever `ProfileDetail` unmounts.

**Target behavior:**
- Default `open = false` (closed) when no stored value exists.
- Open/closed state persists in `sessionStorage` under key `profile-accordion:<id>`.
- Persists across navigation between dashboard tabs and between profiles within a session.
- Resets on browser refresh (intentional — matches `sessionStorage` semantics).

**Implementation:**
- Add `id: string` prop to `AccordionSection`.
- On mount: read `sessionStorage.getItem('profile-accordion:' + id)`; if `'1'` → open, else closed.
- On toggle: write `'1'` or `'0'` to the same key.
- Update all call sites to pass a stable `id`. Required IDs:
  - `identity`, `skills`, `experience`, `education`, `projects`, `job-preferences`, `prompts`, `llm-config`
  - Any other `<AccordionSection>` usages discovered during implementation get a kebab-case id derived from their title.

## 2. Processed-description chip in PromptModal

**Current behavior:** `JOB_CHIPS` exposes `title`, `company`, `location`, `salary`, `description`, `full job`.

**Target behavior:** Add one chip: label `processed description`, token `{job.extracted_description}`. Insert immediately after the `description` entry. Same blue styling as the other Job chips.

**Backend note:** `{job.extracted_description}` is already supported by `core/job.py` (auto-runs the extraction LLM when the token appears in a rendered prompt). No backend work required.

## 3. Pop-out full-viewport editor for Prompt Text

**Current behavior:** The "Prompt Text" zone (Zone 4 in `PromptModal`) is a `<textarea rows={14}>` constrained to the modal's max width.

**Target behavior:** A pop-out icon button next to the "Prompt Text" label opens a full-viewport overlay containing the same editor plus the chip tray.

**Behavior details:**
- Pop-out overlay uses `fixed inset-0 z-[60]` (above PromptModal's `z-50`) with the same dark background.
- Renders the **same** `<textarea>` bound to the **same** `content` React state and the **same** `handleDrop` / `handleDragOver` handlers — so edits and chip drops in the pop-out automatically reflect in the underlying PromptModal on close.
- The pop-out's textarea fills the viewport (e.g., `flex-1 w-full h-full font-mono text-xs`), giving the user substantially more editing room.
- Chip tray (USER_CHIPS + JOB_CHIPS, including the new processed-description chip) is rendered inside the pop-out, identical markup to the existing tray. Hover tooltips on USER_CHIPS preserved.
- Header shows the prompt label (e.g., "Resume Generation — Full Editor") and a `×` close button. No Save button — closing returns to PromptModal where the existing Save handles persistence.
- The `textareaRef` is shared: when the pop-out is mounted, the ref points to the pop-out's textarea (so drag-drop position works). When closed, the ref returns to the inline textarea. Easiest implementation: a single `<textarea>` rendered in only one place at a time, switched via the `popOut` boolean.

**Component shape:**
```
PromptModal
├── (popOut ? null : inline Zone 4 textarea + chip tray in Zone 3)
└── (popOut ? <PromptTextOverlay /> : null)
       └── header + chip tray + full-viewport textarea
```

State: `const [popOut, setPopOut] = useState(false)` added to `PromptModal`. The pop-out button is a small icon in the Zone-4 label row that calls `setPopOut(true)`; the overlay's × calls `setPopOut(false)`.

## Out of scope
- Persisting accordion state across browser refresh (use localStorage).
- Other accordion behaviors (expand-all, remember-last, etc.).
- Changes to the prompt file picker, model override, upload, or chip tooltips.
- Any backend changes.
- Refactoring `ProfileDetail.jsx` (1195 lines) — targeted edits only.

## Testing
Manual verification in the dashboard:
1. Open profile screen → all sections closed.
2. Open Skills, navigate to another tab, navigate back → Skills still open.
3. Refresh the browser → all sections closed again.
4. Open Prompt modal for "Resume Generation" → drag `processed description` chip into the editor → token appears.
5. Click the pop-out button → full-viewport editor appears, content matches, chips are present and draggable.
6. Edit in pop-out, close, observe edits in the underlying modal, click Save → file persists.
