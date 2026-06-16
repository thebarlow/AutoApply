# Admin Page — User Management & Impersonation — Design

**Date:** 2026-06-16
**Status:** Approved (pending spec review)

Builds on `2026-06-16-admin-balance-and-invites-design.md` (admin tab, invite flow,
`allowed_email` table, `require_admin`). This spec expands the admin page into a
multi-function console with a user table and read-only impersonation.

## Goals

1. Make the **Admin navbar tab** visually prominent (gold background).
2. Restructure the **Admin page** to mirror the Help/Docs layout: top navbar + a
   left sub-nav listing admin functions (currently just "Manage Users") + a
   content panel.
3. **Manage Users** function: keep the invite form, add a scrollable users table
   (email, tier, credits) with a per-row "view as" (eyeball) and "purchase
   history" button.
4. **Impersonation** ("view the app from a user's perspective"), **read-only**:
   the admin sees the target user's dashboard; all write/metered actions are
   blocked; a persistent banner shows who is being viewed with an Exit control.

## Context / Existing Infrastructure

- `web/tenancy.py` — `current_profile_id(request, db)` resolves the active tenant.
  In production it reads `request.session["account_id"]` → `Account.profile_id`;
  outside production it returns the dev tenant. `scoped()` filters all
  tenant-scoped reads by `profile_id`. **This is the seam impersonation hooks
  into** — overriding the resolved profile_id transparently re-points every
  scoped read (jobs, documents, stats, purchases, credits).
- `Account` columns include `email`, `is_admin`, `profile_id`, `credit_balance`,
  `tier`.
- `web/routers/admin.py` — admin router (prefix `/api/admin`) behind
  `require_admin` (from `web/routers/credits.py`); currently `POST /invite`,
  `GET /invites`.
- `web/routers/payments.py` — `GET /api/payments/history` returns purchases for
  the current tenant (`Purchase` rows: stripe_session_id, credits, amount_usd,
  status, created_at).
- `web/auth/routes.py` — `GET /api/me` returns `{email, is_admin, profile_name}`.
- `web/auth/middleware.py` — existing pure-ASGI auth gate (pattern reference for
  the new read-only guard).
- `react-dashboard/src/components/Docs.jsx` — Help page: top `<Navbar/>`, a left
  `<nav>` ToC (`w-64`), and a content `<article>`. **Layout reference** for the
  admin page.
- `react-dashboard/src/components/AdminPage.jsx`, `Navbar.jsx`, `App.jsx`,
  `api.js` — created/modified in the prior spec.

## Design

### Part 1 — Gold Admin tab

In `Navbar.jsx`, the `me?.is_admin` "Admin" `<Link>` becomes a gold pill:
`bg-amber-400 text-black font-semibold rounded-md px-2.5 py-1 hover:bg-amber-300`
(instead of the dim text-link styling). Still only rendered when `me?.is_admin`.

### Part 2 — Admin page layout (Docs-style)

`AdminPage.jsx` is restructured to:
- Render `<Navbar/>` at the top (same as Docs).
- A left sub-nav (`w-56 shrink-0`, styled like the Docs ToC) listing admin
  **functions**. A `FUNCTIONS` array drives it: `[{ key: 'users', label: 'Manage
  Users' }]`. Selecting one sets local `active` state. The active item is
  highlighted (same active/inactive classes Docs uses).
- A content area that renders the active function's panel. For `users`, render
  `<ManageUsers/>`.
- Keep the existing client-side admin guard: `getMe()` → if not `is_admin`,
  render the "Not authorized" message; else render the console.

This is built to extend: adding a function = one `FUNCTIONS` entry + one panel
component + one case in the content switch.

### Part 3 — Manage Users panel (`ManageUsers` component)

A new component (own file:
`react-dashboard/src/components/admin/ManageUsers.jsx`) containing:

1. **Invite form** — the email input + "Send Invite" + status message + invited
   list currently in `AdminPage.jsx`, moved here unchanged in behavior.
2. **Users table** — fetches `GET /api/admin/users` on mount. Renders a table
   with a header row and a scrollable body (`max-h-[<~5 rows>] overflow-y-auto`,
   e.g. `max-h-60`). Columns:
   - **Email**
   - **Tier**
   - **Credits** (`credit_balance`, `toLocaleString()`)
   - **Actions**: an eyeball button (view as → `impersonate(profile_id)`) and a
     purchases button (opens the purchases modal for that `profile_id`).
   Rows keyed by `profile_id`.
3. **Purchases modal** — when a row's purchases button is clicked, fetch
   `GET /api/admin/users/{profile_id}/purchases` and show a modal listing
   purchases (date, credits, $amount, status), or "No purchases." Close button.
   Reuses the app's existing modal styling conventions (dark panel, border).

The "view as" action calls `startImpersonation(profile_id)` then redirects to `/`
(`window.location.href = '/'`) so the dashboard reloads under the impersonated
tenant.

### Part 4 — Impersonation (read-only)

**Seam (`web/tenancy.py`):** add a helper and extend `current_profile_id`:

```
def _impersonated_profile_id(request, db) -> int | None:
    # Honor session['impersonate_profile_id'] ONLY if the real logged-in
    # account is an admin (re-checked every request). Returns the target
    # profile_id or None.
```

`current_profile_id` (production branch): after resolving the real account, if
the account `is_admin` and `request.session.get("impersonate_profile_id")` is
set, return that profile_id; otherwise return the account's own profile_id. The
non-production/dev branch is unchanged (no session login in dev). Admin status is
re-verified every request — a stale session flag from a demoted account is
ignored.

**Endpoints (`web/routers/admin.py`, admin-only):**
- `POST /api/admin/impersonate/start` body `{profile_id:int}` — validate the
  target profile exists (an `Account` with that `profile_id`); set
  `request.session["impersonate_profile_id"] = profile_id`. Return `{ok: true}`.
- `POST /api/admin/impersonate/stop` — pop the session key. Return `{ok: true}`.
  **This route must be reachable while impersonating** (see read-only guard
  allowlist). It uses `require_admin`, which is evaluated via the **real**
  account — `require_admin` depends on `current_profile_id`, which during
  impersonation returns the *target* pid, so `require_admin` would resolve the
  target account, not the admin. To avoid this, `impersonate/stop` and
  `impersonate/start` must resolve the admin from `request.session["account_id"]`
  directly (a dedicated `require_real_admin` dependency that ignores
  impersonation), NOT via `require_admin`. Define `require_real_admin` in
  `web/routers/admin.py`.

**`require_real_admin`:** resolves `request.session["account_id"]` → `Account`;
403 unless `is_admin`. Used by ALL admin endpoints in this spec (users,
purchases, impersonate start/stop) so they keep working while impersonating and
always authorize against the real admin, never the impersonated user. (The prior
spec's `invite`/`invites` may keep `require_admin`; they're not used during
impersonation, but switching them to `require_real_admin` for consistency is
acceptable and low-risk.)

**Read-only guard (new middleware):** a pure-ASGI or FastAPI HTTP middleware in
`web/` registered in `web/main.py`. While
`request.session.get("impersonate_profile_id")` is set, reject any request whose
method is in `{POST, PUT, PATCH, DELETE}` with **403** and a JSON body
`{"error":"impersonation_read_only"}`, EXCEPT an allowlist of exact paths:
`/api/admin/impersonate/stop` (so the admin can exit) and `/auth/logout`. Safe
methods (GET/HEAD/OPTIONS) always pass. Because the session is only read, this
needs `SessionMiddleware` to have run — register the guard so it executes after
session is available (i.e., inside the app, as a Starlette `@app.middleware
("http")` or an ASGI layer added after `SessionMiddleware`). The guard does not
itself check admin (the seam already ensures only an admin's session carries the
flag).

**`/api/me` (`web/auth/routes.py`):** add an `impersonating` field. When the real
account is admin and `impersonate_profile_id` is set, resolve the target
`Account` and return
`impersonating: {profile_id, email}`; else `impersonating: null`. Keep existing
fields. Note: `/api/me` must report the **real** admin identity in `email`/
`is_admin` (resolved from `session["account_id"]`), with the impersonation target
in the `impersonating` field — so the banner can show "you (admin) are viewing
X". Verify the current `/api/me` resolves from `session["account_id"]` (it does)
and is a safe GET (not blocked by the guard).

### Part 5 — Frontend impersonation banner

`App.jsx` already fetches `me`. Extend handling: when `me.impersonating` is set,
render a persistent top banner (gold, above the navbar or fixed at top):
"Viewing as {impersonating.email} — Exit". The Exit button calls
`stopImpersonation()` then `window.location.href = '/'`. The banner renders on
the main app routes. (The admin page itself is unreachable for *writes* but
readable; entering impersonation redirects to `/`, so the banner shows on the
dashboard.)

### Part 6 — API client (`api.js`)

Add:
- `getUsers()` → `GET /api/admin/users`
- `getUserPurchases(profileId)` → `GET /api/admin/users/{profileId}/purchases`
- `startImpersonation(profileId)` → `POST /api/admin/impersonate/start`
- `stopImpersonation()` → `POST /api/admin/impersonate/stop`

## Data Shapes

- `GET /api/admin/users` → `[{profile_id, email, tier, credits, is_admin}]`
  (`credits` = `Account.credit_balance`). Ordered by `profile_id` asc.
- `GET /api/admin/users/{profile_id}/purchases` →
  `[{stripe_session_id, credits, amount_usd, status, created_at}]` newest-first
  (same shape as `/api/payments/history`, but for an arbitrary profile_id).
- `GET /api/me` → `{email, is_admin, profile_name, impersonating}` where
  `impersonating` is `{profile_id, email} | null`.

## Testing

**Backend:**
- Seam: with an admin account in session + `impersonate_profile_id` set,
  `current_profile_id` returns the target pid; with a NON-admin account + the
  flag set, it returns the non-admin's own pid (flag ignored); with no flag,
  returns own pid.
- `require_real_admin`: 403 when session account is non-admin or missing; passes
  for admin even when `impersonate_profile_id` points elsewhere.
- Read-only guard: while impersonating, a POST to a normal endpoint → 403
  `impersonation_read_only`; POST `/api/admin/impersonate/stop` → allowed; GET →
  allowed. Without impersonation, POST passes through.
- `GET /api/admin/users`: 403 for non-admin; returns rows with
  email/tier/credits/is_admin; ordered.
- `GET /api/admin/users/{pid}/purchases`: 403 for non-admin; returns that
  profile's purchases (seed a Purchase row for a non-active profile to prove it's
  not scoped to the admin).
- `impersonate/start`: 403 non-admin; 404 unknown profile_id; sets session;
  `impersonate/stop` clears it.
- `/api/me`: `impersonating` null normally; populated (target email) when an
  admin is impersonating.

**Frontend:** no JS test framework — verify via `npm run build` + manual smoke
(gold tab visible; left nav shows Manage Users; table lists users with
tier/credits; eyeball enters read-only view with banner; Exit restores; purchases
modal lists rows).

## Non-Goals / YAGNI

- No editing users from the table (no inline tier/credit edits here — admin grant
  / set-tier endpoints already exist separately).
- No pagination/search on the users table (scroll only; fine at current scale).
- No write/act-as impersonation; read-only only.
- No audit log of impersonation sessions (could add later).
- No additional admin functions yet (structure supports them; none built).

## Affected Files

- `web/tenancy.py` — impersonation-aware `current_profile_id` + helper.
- `web/routers/admin.py` — `require_real_admin`, `users`, `users/{pid}/purchases`,
  `impersonate/start`, `impersonate/stop`.
- `web/middleware_impersonation.py` (new) — read-only guard; registered in
  `web/main.py`.
- `web/main.py` — register the guard middleware.
- `web/auth/routes.py` — `/api/me` gains `impersonating`.
- `react-dashboard/src/components/Navbar.jsx` — gold Admin pill.
- `react-dashboard/src/components/AdminPage.jsx` — Docs-style layout + left
  function nav.
- `react-dashboard/src/components/admin/ManageUsers.jsx` (new) — invite form +
  users table + purchases modal.
- `react-dashboard/src/App.jsx` — impersonation banner.
- `react-dashboard/src/api.js` — `getUsers`, `getUserPurchases`,
  `startImpersonation`, `stopImpersonation`.

## Deployment Notes

No new env vars, no migration (all columns already exist). Impersonation is
session-backed; `SessionMiddleware` is already configured. Effective in
production (OAuth/session); in local dev (no login) the admin page/table work via
the dev tenant but impersonation is a no-op path.
