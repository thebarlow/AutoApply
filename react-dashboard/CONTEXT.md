# react-dashboard CONTEXT.md

## Layout

Two-panel layout split 3:2 in a 5-column grid:

- **Left (col-span-3)** — `Pipeline.jsx`: job workflow tabs
- **Right (col-span-2)** — `Settings.jsx`: profile editor, task monitor, document preview
- **Wrapper** — `Dashboard.jsx`: framer-motion animated grid container, height = `100vh - 53px`
- **Header** — `Navbar.jsx`: branding, credits display, help button
- **Onboarding** — `Onboarding/Wizard.jsx`: first-run wizard shown when prerequisites are unmet; steps: LLM config (`StepLLM.jsx`) then resume upload/parse (`StepResume.jsx`)
- **Docs viewer** — `Docs.jsx`: full-page markdown docs viewer with sidebar nav; replaces dashboard when docs route active
- **User home** — `widgets/UserHome.jsx`: stats dashboard (bar/pie charts via recharts) + profile card grid; shown as right-panel home tab

---

## Routing Rules

| What you want to change | File |
|---|---|
| Top navbar (branding, credits, help button) | `src/components/Navbar.jsx` |
| Grid layout or viewport sizing | `src/components/Dashboard.jsx` |
| Job card appearance (title, company, status icon, doc badges) | `src/components/shared/JobCard.jsx` |
| Pipeline tabs (Inbox / Processing / Outbound / Archives) | `src/components/widgets/Pipeline.jsx` |
| Tab job-state filters | `src/components/widgets/Pipeline.jsx` — `TABS` config |
| Job detail preview (Description / Resume / Cover sub-tabs) | `src/components/widgets/Settings.jsx` — Preview tab section |
| Structured per-section document form editor (overlay) | `src/components/widgets/StructuredEditor.jsx` — loads via `getDocument`, saves via `putDocument` |
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
| First-run onboarding wizard (LLM + resume steps) | `src/components/Onboarding/Wizard.jsx` |
| Onboarding LLM configuration step | `src/components/Onboarding/StepLLM.jsx` |
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
- Document editing now uses the structured `StructuredEditor` overlay; the raw-Markdown editing overlay (`DocumentEditOverlay`) is retired. `MarkdownView` remains as a read-only derived preview.

### ProfileCards.jsx
- Card grid for selecting and activating profiles
- Extracted from Settings.jsx; used inside UserHome and Settings User tab

### UserHome.jsx
- Stats dashboard shown in right panel home tab
- Recharts bar + pie charts; time-window selector (Session / Today / Week / All Time)
- Embeds `ProfileCards` for quick profile switching

### Onboarding/Wizard.jsx
- Multi-step first-run wizard; shown when `usePrerequisites` reports unmet prerequisites
- Step 1: `StepLLM` — provider type, model, API key
- Step 2: `StepResume` — paste or upload resume for parsing
- Skip exits early but still creates the profile if LLM was configured

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
