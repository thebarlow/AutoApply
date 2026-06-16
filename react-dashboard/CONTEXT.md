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
| Profile editor sections (Identity, Skills, Experience, Education, Projects, Preferences) | `src/components/widgets/ProfileDetail.jsx` |
| Prompts editor (scoring, resume, cover letter, extraction, resume parsing) | `src/components/widgets/ProfileDetail.jsx` — Prompts accordion |
| LLM config (provider type, model, API key) | `src/components/widgets/ProfileDetail.jsx` — LLM Config accordion |
| Default prompt text / prompt reset values | `src/components/widgets/ProfileDetail.jsx` — `DEFAULT_PROMPTS` object |
| Admin invite page (email input → `inviteUser`, lists invited emails) | `src/components/AdminPage.jsx` — admin-only, route `/admin` |
| First-run onboarding modal (single resume-upload step) | `src/components/Onboarding/Wizard.jsx` |
| Onboarding resume upload/parse step | `src/components/Onboarding/StepResume.jsx` |
| Docs viewer (markdown rendering, sidebar nav) | `src/components/Docs.jsx` |
| Inline docs markdown content | `src/docs-content/` |
| Prerequisite check hook (llmReady, resumeReady) | `src/hooks/usePrerequisites.js` |
| Form validation helpers (provider, prompt) | `src/validation.js` |
| Help icon tooltip component | `src/components/shared/HelpIcon.jsx` |
| Loading spinner component | `src/components/shared/Spinner.jsx` |
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

### ProfileCards.jsx
- Card grid for selecting and activating profiles
- Extracted from Settings.jsx; used inside UserHome and Settings User tab

### UserHome.jsx
- Stats dashboard shown in right panel home tab
- Rotating stat counter ("You've applied to {x} jobs"); clicking the highlighted phrase cycles Applied → Scraped → Resumes (`STAT_METRICS`), reading `stats.totals` from `/api/stats`
- In-Demand Skills recharts pie/bar charts; time-window selector (Today / Week / All Time) drives the counter via `getStats(win)`
- Embeds `ProfileCards` for quick profile switching

### Onboarding/Wizard.jsx
- Single-step "Upload Master Resume" modal; shown when `usePrerequisites.isFirstRun` is true (i.e. the active profile has no parsed résumé). The platform owns the LLM key via env, so onboarding no longer collects an API key (`StepLLM.jsx` was removed).
- Renders `StepResume` — uploads + parses the résumé against the already-provisioned active profile, then calls `setActiveProfile` so the dashboard resolves it (otherwise `UserHome` falls back to the profile picker).
- "Skip for now" just dismisses for the session (`setWizardSkipped`); the profile already exists, so nothing is created. The modal reappears on next login until a résumé is parsed.

### shared/GatedButton.jsx
- Wraps action buttons; disables + shows tooltip when prerequisites unmet
- Uses `usePrerequisites`; rule map keyed by action name (`score`, `generate`, `parse_resume`)

### ProfileDetail.jsx
- `AccordionSection` — collapsible section wrapper, reused for all 8 sections
- `ItemOverlay` — modal wrapper for inline item edits (experience, education, etc.)
- All saves go through `handleSave(field, value)` → `updateProfile` API → parent `setState`

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
