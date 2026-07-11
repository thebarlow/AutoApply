# react-dashboard CONTEXT.md

## Layout

Two-panel layout split 3:2 in a 5-column grid:

- **Left (col-span-3)** — `Pipeline.jsx`: job workflow tabs
- **Right (col-span-2)** — `Settings.jsx`: profile editor, task monitor, document preview
- **Wrapper** — `Dashboard.jsx`: framer-motion animated grid container, height = `100vh - 53px`
- **Header** — `Navbar.jsx`: branding, credits display, help button
- **Onboarding** — `Onboarding/Wizard.jsx`: single-step "Upload Master Resume" modal shown on first login (no parsed résumé yet); the platform owns the LLM key, so there is no API-key step — just resume upload/parse (`StepResume.jsx`)
- **Onboarding tour** (`src/components/Onboarding/`): a single **action-gated**
  react-joyride walkthrough. `TourController.jsx` mounts one controlled
  `<Joyride>`; `tourSteps.js` holds one linear `TOUR_STEPS` array
  (profile editor → sections/lock/visibility/prompt → job inbox → open the demo
  job → score → generate → credits). Steps carry two custom fields read by the
  controller: `openEvent` (dispatched to open a panel the step needs) and
  `advanceOn` (a window event the user must fire to advance a "gated" step, which
  hides the Next button; `spotlightClicks` lets them click the highlighted control
  through the overlay). `useOnboardingTour.js` is the state machine
  (`unstarted → part1_done → completed`, `skipped`); state persists via
  `PATCH /api/onboarding/tour` and is read from `GET /api/setup-status`
  (API key `onboarding_tour`, mapped to `prereqs.onboardingTour` in
  `usePrerequisites.js`). The tour auto-launches after the résumé wizard finishes/skips
  and drives against a pre-seeded **demo job** (`core/demo_data.py`, inserted at
  profile creation) so the score/open/generate steps have real content. Targets are
  `data-tour="…"` attributes. "Take a tour" in the navbar dispatches
  `auto-apply:tour-replay`.
- **Docs viewer** — `Docs.jsx`: full-page markdown docs viewer with sidebar nav; replaces dashboard when docs route active
- **Find Jobs** — `FindJobs.jsx`: navbar-level full-page view (like `Docs.jsx`, renders its own `<Navbar>`), reached via a "Find Jobs" navbar link and the `/find-jobs` route. Searches remote job boards (Remotive + RemoteOK) server-side; results render as candidate cards (reusing `shared/JobCard.jsx`) with checkbox multi-select and a sticky Scrape bar. Border color follows a precedence order — applied (green) > scraped (yellow) > viewed (gray) > none/new (blue) — via `findjobs/borderStatus.js` (`effectiveStatus`, `BORDER_CLASS`); applied/scraped/none are computed server-side per search, while "viewed" is client-only (set when the user opens a card's in-app detail preview; in-memory, clears on reload).
- **Landing / About page** (`src/components/landing/`): public marketing page shown to
  logged-out visitors (all routes redirect to `/about`) and reachable at `/about` for
  logged-in users via the navbar "About" link. Pure frontend, no API calls. The old
  `LoginScreen.jsx` was retired — its OAuth buttons + beta-closed message live in
  `landing/SignInCard.jsx`.
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
| Processed-description skill chips (3-state ownership color: green have / amber required-gap / neutral) | `src/components/widgets/Settings.jsx` — `ExtractionView` (fetches `getOwnedSkills(skills, jobKey)`, passing the current job key so the cached semantic match is merged into owned chips) |
| Re-check skill ownership button (↻ beside "Required Skills") | `src/components/widgets/Settings.jsx` — `ExtractionView`; calls `rematchSkills(jobKey)` (`POST /api/jobs/{job_key}/rematch-skills`) to recompute the semantic cache, then re-fetches owned skills |
| Tasks / processing jobs monitor | `src/components/widgets/Settings.jsx` — Tasks tab |
| Profile doc-section editor (header/summary/experience/education/projects/skills, tree-driven, whole-tree Save via `PUT /api/config/profiles/{id}/tree`) | `src/components/widgets/profile-tree/ProfileTreeEditor.jsx` — rendered inside `ProfileDetail.jsx`; the `profile-tree/` module contains `treeOps.js` (tree mutation helpers), `fieldWidgets.jsx` (text/markdown/bullets/taglist kind renderers), `structuralControls.jsx` (add-item, add-custom-section, rename, reorder, remove, visible toggle), and `TreeNode.jsx` (recursive node renderer) |
| Profile editor name/Prompts/Export/Reset | `src/components/widgets/ProfileDetail.jsx` — the flat doc-section accordions are retired; only Prompts accordion, Export Master button, and Reset Profile flow remain here |
| Prompts editor (scoring, resume, cover letter, extraction, resume parsing) | `src/components/widgets/ProfileDetail.jsx` — Prompts accordion |
| LLM config (provider type, model, API key) | `src/components/widgets/ProfileDetail.jsx` — LLM Config accordion |
| Default prompt text / prompt reset values | `src/components/widgets/ProfileDetail.jsx` — `DEFAULT_PROMPTS` object |
| Admin page shell (Docs-style top Navbar + left function nav; functions: Manage Users, Résumé Compare) | `src/components/AdminPage.jsx` — admin-only, route `/admin` |
| Admin user management (invite form + users table with view-as, ban/restore, capped credit grants, purchase-history modal) | `src/components/admin/ManageUsers.jsx` — rendered by `AdminPage.jsx` |
| Dev-only résumé comparison view (section-aligned Model 1 vs Model 2 with eval scores) | `src/components/admin/ResumeCompare.jsx` — rendered by `AdminPage.jsx` when `active === 'resume-compare'`; calls `POST /api/dev/resume-compare/{job_key}` via `resumeCompare(jobKey)` in `api.js`. Renders a two-column grid: one row per top-level section (union of both models' headings, case-insensitive, model1 order then model2-only appended). Each cell renders its section's HTML inside an isolated `<iframe srcDoc>` carrying the returned `resume.css` (so it looks as it would in the PDF — no Chromium/PDF generation); paired iframes are height-equalized on load so headings line up across models. Missing section → "— not present —"; errored model column → "— error —". See `docs/superpowers/specs/2026-06-29-resume-compare-section-alignment-design.md`. |
| Impersonation banner ("Viewing as {email} — Exit") | `src/App.jsx` — rendered when `me.impersonating` is set; calls `stopImpersonation` on exit |
| First-run onboarding modal (single resume-upload step) | `src/components/Onboarding/Wizard.jsx` |
| Onboarding resume upload/parse step | `src/components/Onboarding/StepResume.jsx` |
| Docs viewer (markdown rendering, sidebar nav) | `src/components/Docs.jsx` |
| Find Jobs page (search remote boards, candidate cards, checkbox multi-select, sticky Scrape bar, viewed-on-preview) | `src/components/FindJobs.jsx` |
| Find Jobs border-status precedence (applied > scraped > viewed > none) | `src/components/findjobs/borderStatus.js` — `effectiveStatus`, `BORDER_CLASS` |
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

### parse/ParsePreview.jsx

Customization checklist rendered during intake (onboarding `StepResume` and the new-profile wizard step 2 in `Settings`). Props: `proposal`, `profileId`, `onApply`, `onCancel`, `applying`.

- Each section shows a checkbox (the `customize` flag). Checking a section reveals its **Tailoring prompt** textarea.
- The prompt textarea is editable directly, or can be filled via the **Draft from questions** affordance: a `<details>`/`<summary>` panel that collects "purpose" and "tailoring" answers, then calls `POST /api/parse/draft-section-prompt` (`draftSectionPrompt` in `api.js`) with `profileId` and writes the returned `prompt` into the textarea.
- The **Finish** button calls `onApply({ ...proposal, sections: rows })` — no add/replace/skip logic; only the `customize` flag and `prompt` field matter downstream.
- **Known follow-up:** the per-section generator (`apply_parse` → `set_section_customize`) can author field *values* but cannot reorder or drop list entries — it only writes into the existing item slots.

### Onboarding/Wizard.jsx
- "Create your User Profile" modal; shown when `usePrerequisites.isFirstRun` is true (i.e. the active profile has no parsed résumé). The platform owns the LLM key via env, so onboarding no longer collects an API key (`StepLLM.jsx` was removed).
- Two tabs under the "Skip for now" line: **"Use existing Resume"** (default) renders `StepResume`; **"Manual Entry"** shows a blurb + a **"Try it out"** link. Each tab shows a one-sentence explainer.
- **No Finish button.** The modal auto-closes on: a successful résumé parse (`StepResume` calls `onFinish` → page reload), "Skip for now" (`setWizardSkipped`), or "Try it out".
- `StepResume` uploads + parses the résumé against the already-provisioned active profile (resolved from `getProfiles`' `active_id`, which the tenant seam returns), then `onFinish` (reload). It fetches the full profile via `getProfile` before attaching the upload (the `getProfiles` list omits `data`).
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

### profile-tree/ (new in 2B, extended in 2C, field roles added in #3, section/item prompts in #4)
- `ProfileTreeEditor.jsx` — root component; loads tree via `GET /api/config/profiles/{id}/tree`, manages dirty state, explicit Save (`PUT /api/config/profiles/{id}/tree`), Discard, and 422 error surfacing. **2C:** owns the section-level `DndContext` (drag-drop reorder of sections via `dnd-kit`); `↑`/`↓` buttons retained as a11y fallback.
- `TreeNode.jsx` — recursive node renderer; dispatches ops (setValue, rename, toggleVisible, remove, move, addItem, addField, reorder) to parent. **2C:** `ListView` owns a per-list `DndContext` (drag-drop reorder of list entries); each entry gets a drag-handle-only reorder. `SectionView` accepts an optional `dragHandle` prop so `ProfileTreeEditor` can inject the section drag handle without breaking 2B unit tests. **#4:** List entries are first-class: each has lock (🔒) / visibility (👁) / prompt (💬) controls (always shown — no longer hidden when the parent section is locked), a double-click-rename name (falls back to `Entry N`), and body-click expand. The chip tray uses per-entry sub-folders for list sections (one folder per entry: a whole-entry pill + its field pills). Preset sections now allow add/remove fields. **Field-level prompts:** an LLM-written field (`llm_output=true`) shows a 💬 control opening `PromptEditorModal` bound to its `llm_instructions` (the old inline "How should the LLM write this field?" textarea was retired); `PromptEditorModal` accepts an explicit `value`+`label` to drive section/item/field prompts uniformly. **Layout:** `GroupView` packs single-line `text` fields two-to-a-row (Company|Title, Start|End); multi-line kinds span full width. The prompt glyph is 💬 (chat bubble) everywhere.
- `SectionGallery.jsx` — **2C:** recommended-section gallery (7 templates + Blank) that replaces the old "+ Add section" button; consumed by `ProfileTreeEditor`.
- `sectionCatalog.js` — **2C:** catalog of the 7 section templates + Blank; each entry has a `type`, `label`, and `buildFn` that calls `buildSectionFromTemplate`.
- `fieldWidgets.jsx` — per-kind field renderers: `TextWidget`, `MarkdownWidget`, `BulletsWidget`, `TaglistWidget`. **#4:** `MarkdownWidget` has a pop-out (⤢) large-editor modal for long text values (no chip injection).
- `PromptField.jsx` — **#4:** shared contenteditable pill prompt editor for section/item prompts. Tokens are node-id based (`{profile:<nodeId>}`) and `{job.<field>}`; each renders as a non-editable pill showing a human-readable label, while the stored value keeps raw tokens. Exports `buildChipGroups`, `buildLabelMap`, `splitSegments`, `serializeNode`, `renderHtml`, `ChipTray` (collapsible folder tray with Job + per-section/field chips), `PromptField`, and `buildFoldedPreview` (mirrors `build_section_prompt` in Python byte-for-byte). Injected pills render green (`.prompt-chip` in `src/index.css`) and drop at the release point (`caretRangeFromPoint`, feature-detected with fallback). Chips are draggable or click-to-insert. **Folder drag:** each profile folder (section / list entry) carries its own node-id `token`, so dragging the *folder header* injects the whole node's data — there is no "(whole section)/(whole entry)" pill; drag the Experience folder for all jobs, or open it and drag one entry. `PromptField` is a two-column 3:1 layout (editor left, chip tray right) with no pop-out — the host `PromptEditorModal` (widened) is the full surface; `PopOutEditor` was removed.
- `structuralControls.jsx` — structural mutation controls: add list item, add custom section + fields, rename (double-click), reorder, remove (bordered confirm dismissed on outside pointer-down), visibility toggle (`VisibleToggle`, eye), and section/item lock icons (🔒/🔓) gating LLM authoring (`locked` on `SectionNode`/`GroupNode`). **#4:** Section/item/field prompts are edited ONLY via `PromptEditorModal` (opened by the 💬 control on a section, list entry, or LLM-written field); inline prompt fields/textareas were retired. The chip tray + pill editor live inside that modal. `MoveButtons` remains exported but is no longer rendered (↑/↓ move buttons and ▸/▾ expand-arrow buttons were removed from sections and entries). Field lock/eye icons unchanged.
- `treeOps.js` — pure tree mutation helpers: `updateNode`, `removeNode`, `moveNode`, `addField`, `addListItem`, `addCustomSection`, `reorderSiblings`, `renumber`, `isPresetSection`, `makeField`, `cloneWithFreshIds`, `toggleLlmWritten`/`isLlmWritten` (lock), `setLlmInstructions`, and `deepEqual` (effective-change detection for the Save/Discard bar). `SectionView` takes `initialCollapsed` so newly added sections open by default; clicking a section bar toggles collapse.
- `ProfileEditorModal.jsx` — **#4:** modal editor for user profile name/pronouns/location; opened from the user's name click in `Settings.jsx` (the flat pushed `profileDetail` view was removed).

### Test suite
- Vitest + React Testing Library + jsdom; run `npm run test` from `react-dashboard/`
- 10 test files, 65 tests covering: API wrappers, treeOps helpers, sectionCatalog, SectionGallery, TreeNode rendering (including drag handle), fieldWidgets, structuralControls, ProfileTreeEditor integration, ResumeCompare, smoke

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
