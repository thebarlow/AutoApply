# react-dashboard CONTEXT.md

## Layout

Two-panel layout split 3:2 in a 5-column grid:

- **Left (col-span-3)** — `Pipeline.jsx`: job workflow tabs
- **Right (col-span-2)** — `Settings.jsx`: profile editor, task monitor, document preview
- **Wrapper** — `Dashboard.jsx`: framer-motion animated grid container, height = `100vh - 53px`
- **Header** — `Navbar.jsx`: branding, credits display, help button

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
| Process / Generate / Regenerate / Apply buttons | `src/components/widgets/Settings.jsx` — Preview tab |
| User profile list, active profile selector, Create Profile modal | `src/components/widgets/Settings.jsx` — User tab |
| Tasks / processing jobs monitor | `src/components/widgets/Settings.jsx` — Tasks tab |
| Profile editor sections (Identity, Skills, Experience, Education, Projects, Preferences) | `src/components/widgets/ProfileDetail.jsx` |
| Prompts editor (scoring, resume, cover letter, extraction, resume parsing) | `src/components/widgets/ProfileDetail.jsx` — Prompts accordion |
| LLM config (provider type, model, API key) | `src/components/widgets/ProfileDetail.jsx` — LLM Config accordion |
| Default prompt text / prompt reset values | `src/components/widgets/ProfileDetail.jsx` — `DEFAULT_PROMPTS` object |
| API calls (jobs, profiles, providers, generate, apply) | `src/api.js` |
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
