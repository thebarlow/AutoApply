# CONTEXT — `e2e/`

Playwright smoke + live-drive harness for the local dashboard. Usage lives in
`README.md`; this file records caveats and limitations only (don't duplicate the
how-to).

## What this is / isn't

- A lightweight **smoke** harness (page/button presence, screenshots) and a
  scaffold for ad-hoc live-drive via the Playwright MCP tools. **Not** a
  run-on-every-change regression suite — specs assert at presence/visibility
  level and never click destructive controls (delete / mark-applied / generate),
  so runs don't mutate data or burn LLM credits.
- **`e2e/extension/` is a separate Playwright project**, not part of this one.
  It loads the unpacked `browser-extension/` via a persistent Chromium context
  to exercise the MV3 service worker and (eventually) drive ATS autofill against
  local HTML fixtures (`e2e/extension/fixtures/`). Requires **headed** Chromium
  (MV3 service workers don't register headless) — run via
  `cd e2e/extension && npm test`. Its own config/fixtures live under
  `e2e/extension/`, separate `package.json`/`node_modules` from this harness.

## Caveats / known limitations

- **Runs against the real local dev DB (`auto_apply.db`), not a fixture.** Specs
  need a local profile to render — without one the SPA redirects to `/about`, so
  the dashboard/find-jobs specs fail. There is no seeding step; the harness
  assumes a populated dev DB.
- **Needs a logged-in session.** `global-setup.ts` calls `POST /api/dev/login`
  (see `web/routers/dev.py`) to mint a session and saves `storageState.json`;
  specs reuse it. The endpoint is **non-production only** and resolves the login
  account by `E2E_LOGIN_EMAIL` (default the owner's personal address) → admin →
  lowest-id account, so a normal run against the real local DB logs in as the
  owner. On an **empty DB** (the `new-user-test` clean slate) it provisions a
  throwaway account on a fresh empty profile, driving the new-user onboarding
  entry state instead of 404ing.
- **Worktree / migration skew.** When run from a git worktree branched off an
  older migration head, the checked-out code may be incompatible with the real
  dev DB's schema (the DB is shared across worktrees). Boot may fail or
  `dev-login` may error until the DB is migrated (`init_db.py`) or the worktree
  is rebased onto the current head.
- **Auth gate is off locally.** The gate only activates when
  `APP_ENV=production`, so no OAuth is exercised here; `dev-login` exists purely
  to satisfy the identity gate (`/api/me`), which has no dev bypass.
- Generated artifacts (`screenshots/`, `test-results/`, `playwright-report/`,
  `storageState.json`, `node_modules/`) are gitignored.
