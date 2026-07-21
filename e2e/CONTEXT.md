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

## Caveats / known limitations

- **Runs against the real local dev DB (`auto_apply.db`), not a fixture.** Specs
  need a local profile to render — without one the SPA redirects to `/about`, so
  the dashboard/find-jobs specs fail. There is no seeding step; the harness
  assumes a populated dev DB.
- **Needs a logged-in session.** `global-setup.ts` calls `POST /api/dev/login`
  (see `web/routers/dev.py`) to mint a session and saves `storageState.json`;
  specs reuse it. The endpoint is **non-production only** and picks the sole
  account (or the admin account if several exist), so which profile the specs
  see depends on the local DB's accounts.
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
