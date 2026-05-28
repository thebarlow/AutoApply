# User Tab Refactor Design

**Date:** 2026-05-27  
**Status:** Approved

## Overview

Refactor the User tab in the Settings panel to show a personalized home view when an active profile is selected. The home view displays a welcome message, activity graphs with time controls, and a Switch User button. If no active profile exists, the existing profile list (ProfileCards) is shown unchanged.

## Layout & UX

When an active profile is set, the User tab renders `UserHome`:

```
┌─────────────────────────────────┐
│  Welcome back, Matthew Barlow   │  ← profile.first_name + profile.last_name
│                                 │
│  [Session] [Today] [Week] [All] │  ← time control toggle
│                                 │
│  Bar chart: scraped / resumes / covers (grouped bars, one group per date bucket)
│                                 │
│  Pie chart: jobs by state
│                                 │
│  [Switch User]                  │  ← bottom, secondary button style
└─────────────────────────────────┘
```

**Switch User** replaces the UserHome content with the existing `ProfileCards` component (profile list + Create Profile button). A back arrow in the header returns to UserHome.

**No active profile:** renders `ProfileCards` directly — no change to current behavior.

**Time controls:**
- **Session** — since server start (server-side timestamp, mirrors session cost behavior)
- **Today** — current calendar day (UTC)
- **Week** — last 7 days, daily buckets
- **All Time** — all days with activity, daily buckets

Session and Today return a single aggregate bucket. Week and All Time return one entry per day with activity.

## Data & Backend

### New DB columns on `Job`

Two nullable String columns added to `core/job.py`:
- `resume_generated_at` — ISO UTC string, set when `resume_path` is written
- `cover_generated_at` — ISO UTC string, set when `cover_path` is written

SQLite auto-migrates on app start (via `Base.metadata.create_all`). No explicit migration script needed.

Generator code (`_do_generate_resume`, `_do_generate_cover` in `web/routers/jobs.py`) sets these timestamps when writing the path.

### New endpoint

`GET /api/stats?window=session|today|week|all_time`

**Response shape:**
```json
{
  "bars": [
    {"label": "May 25", "scraped": 4, "resumes": 2, "covers": 1}
  ],
  "by_state": {
    "new": 8, "pending_review": 3, "ready": 2,
    "applied": 5, "contact": 1, "rejected": 2, "deleted": 0
  }
}
```

- `scraped` count: jobs where `scraped_at` falls in the window
- `resumes` count: jobs where `resume_generated_at` falls in the window
- `covers` count: jobs where `cover_generated_at` falls in the window
- `by_state`: counts across **all** jobs (not filtered by window — represents current pipeline state)

Session start time is retrieved from the same in-memory variable used by `session_cost_router.py`.

New file: `web/routers/stats.py`, registered in `web/app.py`.

### Frontend API

New function in `react-dashboard/src/api.js`:
```js
export const getStats = (window) => _fetch(`/api/stats?window=${window}`)
```

## Charts Library

Add `recharts` to `react-dashboard/package.json`. Used for:
- `BarChart` + `Bar` — grouped bars for scrape/resume/cover activity
- `PieChart` + `Pie` + `Cell` — jobs by state with color per state

## Components

### New: `react-dashboard/src/components/widgets/UserHome.jsx`

Props: `activeProfile` (profile object with top-level `first_name`, `last_name`, `name`), `onSwitchUser` (callback)

State: `window` (one of `session|today|week|all_time`), `stats` (fetched data), `loading`, `error`

Behavior:
- Fetches `/api/stats?window=<window>` on mount and on window change
- Renders welcome heading, time toggle, bar chart, pie chart, Switch User button
- Bar chart: grouped bars (scraped=purple, resumes=blue, covers=teal), X axis = date labels from `bars[].label`
- Pie chart: one slice per state, uses existing state label map, colored by state (applied=green, rejected=red, new=purple, others=gray variants)

### Changed: `react-dashboard/src/components/widgets/Settings.jsx`

- `ProfileCards` fetch already returns `active_id`. Fetch the active profile object to get `first_name`/`last_name` for the welcome message.
- When `view === 'main' && activeTab === 'User'`: render `UserHome` if active profile exists, else `ProfileCards`.
- `onSwitchUser` callback sets a local state flag that renders `ProfileCards` within the User tab. Back arrow returns to `UserHome`.
- Header back-arrow label: "Switch User" → "User" (existing back-arrow pattern already in Settings).

### No changes to

- `App.jsx` — jobs array does not need to be passed to Settings (stats are fetched independently by UserHome)
- `ProfileDetailView` — untouched
- `Navbar.jsx` — untouched

## Error Handling

- Stats fetch failure: show a muted inline error ("Could not load stats") inside UserHome; charts are hidden.
- Missing `first_name`/`last_name`: welcome heading falls back to profile `name` field.
- Empty `bars` array: bar chart renders empty state ("No activity yet").

## Out of Scope

- Clicking a pie slice to filter the job pipeline
- Export or download of stats
- Per-profile stats (stats are global across all jobs in the DB)
