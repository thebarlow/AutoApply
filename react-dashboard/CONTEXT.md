# react-dashboard CONTEXT.md

## Layout

Two-panel layout split 3:2 in a 5-column grid:

- **Left (col-span-3)** — `Pipeline.jsx`: job workflow tabs
- **Right (col-span-2)** — `Settings.jsx`: profile editor, task monitor, document preview
- **Wrapper** — `Dashboard.jsx`: framer-motion animated grid container, height = `100vh - 53px`
- **Header** — `Navbar.jsx`: branding, credits display, help button
- **Onboarding** — `Onboarding/Wizard.jsx`: single-step "Upload Master Resume" modal shown on first login (no parsed résumé yet); the platform owns the LLM key, so there is no API-key step — just resume upload/parse (`StepResume.jsx`)
- **Docs viewer** — `Docs.jsx`: full-page markdown docs viewer with sidebar nav; replaces dashboard when docs route active
- **User home** — `widgets/UserHome.jsx`: stats dashboard (bar/pie charts via recharts) + profile card grid; shown as right-panel home tab

---

## Routing Rules

| What you want to change | File |
|---|---|
| Top navbar (branding, credits, help button, Admin link for admins) | `src/components/Navbar.jsx` — shows an Admin link when `me.is_admin` |
| Credit balance display (navbar + User tab panel) | `src/components/widgets/CreditBalance.jsx` — fetches `/api/credits`; refetches on `auto-apply:credits-stale` event; `variant` prop: `nav`/`panel`; for admins shows the platform system balance (click toggles $/credits) instead of personal credits |
| Out-of-credits (HTTP 402) global signal | `src/api.js` — `_fetch` dispatches `auto-apply:credits-error` + `auto-apply:credits-stale`; toasted in `src/App.jsx` |
| Grid layout or viewport sizing | `src/components/Dashboard.jsx` |
| Job card appearance (title, company, status icon, doc badges) | `src/components/shared/JobCard.jsx` |
| Pipeline tabs (Inbox / Processing / Outbound / Archives) | `src/components/widgets/Pipeline.jsx` |
| Tab job-state filters | `src/components/widgets/Pipeline.jsx` — `TABS` config |
| Job detail preview (Description / Resume / Cover sub-tabs) | `src/components/widgets/Settings.jsx` — Preview tab section |
| Interactive document modal (hover-highlight, inline edit, per-item feedback) | `src/components/widgets/DocumentModal.jsx` + `src/components/widgets/document/` (`InteractiveResume`, `ResumeSection`, `items`, `ItemPopover`, `ItemEditor`, `CoverView`, `highlight.css`) — opened by the single pencil (✎) button on the Resume/Cover toolbar; `StructuredEditor.jsx` is retired |
| Process / Generate / Regenerate / Apply buttons | `src/components/widgets/Settings.jsx` — Preview tab |
| Action buttons gating / prerequisite enforcement | `src/components/shared/GatedButton.jsx` |
| User profile list, active profile selector, Create Profile modal | `src/components/widgets/Settings.jsx` — User tab |
| Profile card grid (select / set active profile) | `src/components/widgets/ProfileCards.jsx` |
| Stats dashboard (charts, job-state counts, time windows) | `src/components/widgets/UserHome.jsx` |
| Skill alias/own-skill modal (opened from In-Demand legend names + job-description chips) | `src/components/widgets/SkillChipModal.jsx` |
| Processed-description skill chips (3-state ownership color: green have / amber required-gap / neutral) | `src/components/widgets/Settings.jsx` — `ExtractionView` (fetches `getOwnedSkills`) |
| Tasks / processing jobs monitor | `src/components/widgets/Settings.jsx` — Tasks tab |
| Profile doc-section editor (header/summary/experience/education/projects/skills, tree-driven, whole-tree Save via `PUT /api/config/profiles/{id}/tree`) | `src/components/widgets/profile-tree/ProfileTreeEditor.jsx` — rendered inside `ProfileDetail.jsx`; the `profile-tree/` module contains `treeOps.js` (tree mutation helpers), `fieldWidgets.jsx` (text/markdown/bullets/taglist kind renderers), `structuralControls.jsx` (add-item, add-custom-section, rename, reorder, remove, visible toggle), and `TreeNode.jsx` (recursive node renderer) |
| Profile editor name/Prompts/Export/Reset | `src/components/widgets/ProfileDetail.jsx` — the flat doc-section accordions are retired; only Prompts accordion, Export Master button, and Reset Profile flow remain here |
| Prompts editor (scoring, resume, cover letter, extraction, resume parsing) | `src/components/widgets/ProfileDetail.jsx` — Prompts accordion |
| LLM config (provider type, model, API key) | `src/components/widgets/ProfileDetail.jsx` — LLM Config accordion |
| Default prompt text / prompt reset values | `src/components/widgets/ProfileDetail.jsx` — `DEFAULT_PROMPTS` object |
| Admin page shell (Docs-style top Navbar + left function nav; functions: Manage Users) | `src/components/AdminPage.jsx` — admin-only, route `/admin` |
| Admin user management (invite form + users table with view-as, ban/restore, capped credit grants, purchase-history modal) | `src/components/admin/ManageUsers.jsx` — rendered by `AdminPage.jsx` |
| Impersonation banner ("Viewing as {email} — Exit") | `src/App.jsx` — rendered when `me.impersonating` is set; calls `stopImpersonation` on exit |
| First-run onboarding modal (single resume-upload step) | `src/components/Onboarding/Wizard.jsx` |
| Onboarding resume upload/parse step | `src/components/Onboarding/StepResume.jsx` |
| Docs viewer (markdown rendering, sidebar nav) | `src/components/Docs.jsx` |
| Inline docs markdown content | `src/docs-content/` |
| Prerequisite check hook (llmReady, resumeReady) | `src/hooks/usePrerequisites.js` |
| Form validation helpers (provider, prompt) | `src/validation.js` |
| Help icon tooltip component | `src/components/shared/HelpIcon.jsx` |
| Loading spinner component | `src/components/shared/Spinner.jsx` |
| Admin ban/restore, grant-budget, credit grants | `src/api.js` — `setUserAccess`, `getGrantBudget`, `grantCredits` |
| API calls (jobs, profiles, providers, generate, apply, setup status) | `src/api.js` |
| Structured document fetch/save | `src/api.js` — `getDocument` / `putDocument` (replaced `putDocumentMarkdown`) |
| Global state (jobs list, selected job, processing keys, active tab) | `src/App.jsx` |
| SSE real-time job update subscription | `src/App.jsx` — `useEffect` with EventSource |
| Global CSS, background noise texture, dark theme base | `src/index.css` |
| App entry point / React root | `src/main.jsx` |

---

## Key Widget Internals

### Pipeline.jsx
- `TABS` maps tab label → job state filter
- `JobList` sub-component renders scrollable `JobCard` list
- Archive tab adds colored state badges (green/blue/red)

### Settings.jsx
- `settingsTab` prop controls User / Tasks / Preview top-level tabs
- Preview tab has three sub-tabs driven by local `previewTab` state
- `CreateProfile` inline modal lives here, not in ProfileDetail
- AnimatePresence handles slide transitions between User list and ProfileDetail
- Document editing is now handled entirely by the interactive `DocumentModal` (the `StructuredEditor` overlay and raw-Markdown overlay are retired). `MarkdownView` remains as a read-only derived preview.
- Resume/Cover toolbar (Settings Preview tab) now has a single pencil (✎) button (Edit/Expand removed); it opens the `DocumentModal` for hover-highlight / inline-edit / per-item feedback
- `SubToggle` and `MarkdownView` are now exported and reused by `DocumentModal`

### DocumentModal.jsx
- Interactive document view backed by `document/` widgets: `InteractiveResume` → `ResumeSection` → `items` (hover-highlight per item, `ItemPopover`/`ItemEditor` for inline edit + per-item feedback), `CoverView` for cover letters; styling in `highlight.css`
- Clicking an item opens the `ItemPopover` (Edit | Feedback) **to the right** of the item. `ItemEditor` commits on the **Save** button (disabled until edited), on **Enter** (Shift+Enter = newline in textareas), or on click-out
- **Section-level feedback:** clicking a section title (Experience/Education/Projects/Skills) opens a Feedback-only popover + a whole-section note box; section notes submit alongside item notes
- Feedback is a controlled `notes` store on the modal keyed `section:index` (or `section:section`); `collected` gathers non-empty notes for the footer "Regenerate with feedback (N)" button
- Submitting feedback runs a one-shot refine via `POST /{doc_type}/feedback`
- **Escape handling:** a capture-phase listener keeps Escape inside the modal — it exits an open inline edit/feedback first (via a shared `escapeRef` consumer set by `InteractiveResume`/`CoverView`), and only closes the modal (back to job details, *not* the app-level "deselect → User view" handler in `App.jsx`) when nothing is open
- `TurnEntry` labels user-feedback turns "Your feedback"

### ManageUsers.jsx

- Search box filters users by email; columns (Email / Tier / Credits) are sortable and left-aligned.
- Admins get an `ADMIN` badge; their credits cell shows `—` (non-clickable) to prevent self-grants.
- Clicking a non-admin's credits cell opens a **grant modal**: amount defaults to `min(100, available)`, capped at the `available` figure from `getGrantBudget`; submits via `grantCredits`.
- **BANNED** tag appears on banned rows. Revoke ✕ opens a confirm modal → `setUserAccess({banned:true})`; Restore ↺ calls `setUserAccess({banned:false})` directly.

### ProfileCards.jsx
- Card grid for selecting and activating profiles
- Extracted from Settings.jsx; used inside UserHome and Settings User tab

### UserHome.jsx
- Stats dashboard shown in right panel home tab
- Rotating stat counter ("You've applied to {x} jobs"); clicking the highlighted phrase cycles Applied → Scraped → Resumes (`STAT_METRICS`), reading `stats.totals` from `/api/stats`
- In-Demand Skills recharts pie/bar charts; time-window selector (Today / Week / All Time) drives the counter via `getStats(win)`
- Embeds `ProfileCards` for quick profile switching

### Onboarding/Wizard.jsx
- "Create your User Profile" modal; shown when `usePrerequisites.isFirstRun` is true (i.e. the active profile has no parsed résumé). The platform owns the LLM key via env, so onboarding no longer collects an API key (`StepLLM.jsx` was removed).
- Two tabs under the "Skip for now" line: **"Use existing Resume"** (default) renders `StepResume`; **"Manual Entry"** shows a blurb + a **"Try it out"** link. Each tab shows a one-sentence explainer.
- **No Finish button.** The modal auto-closes on: a successful résumé parse (`StepResume` calls `onFinish` → page reload), "Skip for now" (`setWizardSkipped`), or "Try it out".
- `StepResume` uploads + parses the résumé against the already-provisioned active profile, calls `setActiveProfile` so the dashboard resolves it, then `onFinish` (reload). It fetches the full profile via `getProfile` before attaching the upload (the `getProfiles` list omits `data`).
- **Reopen-after-skip:** when skipped, `UserHome`'s header swaps to "Ready to set up" / **"your profile"** (clickable) while `isFirstRun`. Clicking dispatches the `auto-apply:open-wizard` window event; `App.jsx` listens and re-shows the wizard (`setWizardSkipped(false)`).
- **Manual Entry → Try it out:** `App.jsx`'s `onManual` handler dismisses the wizard, sets the User tab active, and dispatches `auto-apply:edit-profile`; `Settings.jsx` listens, resolves the active profile, and opens `ProfileDetailView` (manual editor). Entering experience/education/skills/projects flips `setup-status` `resume_parsed` true, so the header returns to "Welcome back".
- The Profile view's **Reset Profile** button (`ProfileDetail.jsx`) calls `POST /api/config/profiles/{id}/reset`, which empties `User.data` (keeping the row, jobs, and generated documents). This flips `setup-status` `resume_parsed` to false, so reloading re-shows this wizard. Confirmation requires typing `Reset my Profile`.

### shared/GatedButton.jsx
- Wraps action buttons; disables + shows tooltip when prerequisites unmet
- Uses `usePrerequisites`; rule map keyed by action name (`score`, `generate`, `parse_resume`)

### ProfileDetail.jsx
- `AccordionSection` — collapsible section wrapper, reused for Prompts and any future sections
- Doc-section editing (header/summary/experience/education/projects/skills) is now handled entirely by `ProfileTreeEditor` (tree-driven); the flat `ItemOverlay`/`EditBtn`/section component UI is retired
- Remaining responsibilities: Prompts accordion (scoring/resume/cover/extraction/resume_parse prompt slots + refinement), Export Master button, Reset Profile flow
- The flat `update_profile` endpoint is retained for name/job-preferences/onboarding writes; only the doc-section editor UI was retired

### profile-tree/ (new in 2B, extended in 2C)
- `ProfileTreeEditor.jsx` — root component; loads tree via `GET /api/config/profiles/{id}/tree`, manages dirty state, explicit Save (`PUT /api/config/profiles/{id}/tree`), Discard, and 422 error surfacing. **2C:** owns the section-level `DndContext` (drag-drop reorder of sections via `dnd-kit`); `↑`/`↓` buttons retained as a11y fallback.
- `TreeNode.jsx` — recursive node renderer; dispatches ops (setValue, rename, toggleVisible, remove, move, addItem, addField, reorder) to parent. **2C:** `ListView` owns a per-list `DndContext` (drag-drop reorder of list entries); each entry gets a `"Drag to reorder item"` handle; `↑`/`↓` `MoveButtons` retained as a11y fallback. `SectionView` accepts an optional `dragHandle` prop so `ProfileTreeEditor` can inject the section drag handle without breaking 2B unit tests.
- `SectionGallery.jsx` — **2C:** recommended-section gallery (7 templates + Blank) that replaces the old "+ Add section" button; consumed by `ProfileTreeEditor`.
- `sectionCatalog.js` — **2C:** catalog of the 7 section templates + Blank; each entry has a `type`, `label`, and `buildFn` that calls `buildSectionFromTemplate`.
- `fieldWidgets.jsx` — per-kind field renderers: `TextWidget`, `MarkdownWidget`, `BulletsWidget`, `TaglistWidget`
- `structuralControls.jsx` — structural mutation controls: add list item, add custom section + fields, rename, reorder, remove, visibility toggle
- `treeOps.js` — pure tree mutation helpers: `updateNode`, `removeNode`, `moveNode`, `addField`, `addListItem`, `addCustomSection`, `reorderSiblings`, `renumber`, `isPresetSection`, `makeField`, `cloneWithFreshIds`

### Test suite
- Vitest + React Testing Library + jsdom; run `npm run test` from `react-dashboard/`
- 9 test files, 57 tests covering: API wrappers, treeOps helpers, sectionCatalog, SectionGallery, TreeNode rendering (including drag handle), fieldWidgets, structuralControls, ProfileTreeEditor integration, smoke

---

## Job States (Pipeline filter mapping)

| Tab | States |
|---|---|
| Inbox | `new`, `pending_review` |
| Processing | jobs in `processingKeys` set |
| Outbound | `ready` |
| Archives | `applied`, `contact`, `rejected` |

---

## Styling Conventions

- Dark space theme: `space-bg` (#0a0a1a), `space-text`, `space-dim`, `space-border`
- Primary accent: `purple-400` / `purple-500` / `purple-600`
- Status colors: `green-400` (applied), `blue-400` (contact), `red-400` (rejected), `yellow-*` (new)
- Animations: framer-motion `motion.div` + `AnimatePresence` throughout
- Consistent input styling via shared `inputClass` string in Settings/ProfileDetail
