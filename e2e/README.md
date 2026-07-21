# e2e — Playwright smoke + live-drive harness

Lightweight harness for driving the local dashboard: confirm pages/buttons work
and capture screenshots. **Not** a run-on-every-change regression suite.

The app runs open locally (the auth gate only activates when
`APP_ENV=production`), so no OAuth is needed. Dashboard/Find-Jobs pages need a
local profile in `auto_apply.db` to render — without one the SPA redirects to
`/about`.

## Setup (once)

```bash
cd e2e
npm install
npx playwright install chromium
```

## Committed smoke scripts

```bash
cd e2e
npm test              # headless
npm run test:headed   # watch it drive the browser
npm run report        # open the last HTML report
npm run deck          # build an HTML slide deck from screenshots/*.png, open it
```

`playwright.config.ts` auto-boots the stack if it isn't already running
(uvicorn `:8080` from repo root via `.venv`, Vite `:5173` from
`react-dashboard/`) and **reuses** an existing dev stack — so `start.bat dev` in
another window is picked up instead of double-booting. Base origin is the Vite
dev server, which proxies `/api` and `/auth` to the backend.

Screenshots land in `e2e/screenshots/` (gitignored). Specs assert at
presence/visibility level against the real local dev DB and never click
destructive controls (delete / mark-applied / generate) — so runs don't mutate
data or burn LLM credits.

`landing.spec.ts` captures a full-page shot; the landing hero/sections fade and
slide in on load and scroll, so the spec scrolls the whole page, awaits
`document.getAnimations()` to settle, and adds a short paint delay before the
shot (rather than a blind sleep). It waits on visible content, not
`networkidle` — Vite's HMR websocket never lets the network go idle in dev.

## Presenting screenshots (`npm run deck`)

`scripts/deck.mjs` builds a single self-contained HTML slide deck from every
`screenshots/*.png` and opens it in one browser window (`npm run deck`). Pass a
filter to show just one shot: `node scripts/deck.mjs landing`.

| Spec | Covers |
|---|---|
| `tests/landing.spec.ts` | `/about` renders |
| `tests/dashboard.spec.ts` | Main board loads; nav links visible; Find Jobs routes |
| `tests/find-jobs.spec.ts` | Find Jobs search UI present |

## Live-drive workflow (ad hoc, via Claude)

For anything not covered by a committed spec, Claude drives the *running* app
directly with the Playwright MCP tools — no test files needed:

1. Start the stack: `start.bat dev` (or let a spec run boot it).
2. Ask Claude to drive it, e.g. *"open the dashboard, click the Résumé tab on
   the selected job, and screenshot it."* Claude uses
   `mcp__playwright__browser_navigate` / `browser_snapshot` / `browser_click` /
   `browser_take_screenshot` against `http://localhost:5173`.

Prefer `browser_snapshot` (accessibility tree) over screenshots for locating
elements; use screenshots for visual confirmation.
