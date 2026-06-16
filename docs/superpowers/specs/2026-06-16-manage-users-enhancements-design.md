# Manage Users Enhancements — Design

**Date:** 2026-06-16
**Status:** Approved (pending spec review)

Extends the admin Manage Users console (`2026-06-16-admin-page-users-impersonation-design.md`)
with an admin badge, search, sortable/left-aligned columns, user revocation (ban),
and capped credit grants. Also fixes the admin-credits display mismatch.

## Goals (from request)

1. Admin badge next to admin emails.
2. **Bug fix:** the table shows an admin's leftover personal `credit_balance` (e.g.
   550), which admins never spend (they draw from the system balance). Show `—`
   for admin rows instead.
3. Search box above the users table.
4. Sortable columns (asc/desc) on Email, Tier, Credits.
5. Left-align all column headers and cells.
6. Revoke access: a red ✕ per (non-admin) row → confirm modal → ban the user and
   remove them from the allowlist. Reversible (restore).
7. Grant credits: click a (non-admin) user's Credits value → modal → grant free
   credits funded from the system balance, capped at the unclaimed system credits.

## Context

- `web/routers/admin.py` — admin endpoints behind `require_real_admin`:
  `GET /users` (returns `{profile_id, email, tier, credits, is_admin}`),
  `GET /users/{pid}/purchases`, `POST /impersonate/{start,stop}`.
- `web/routers/credits.py` — `admin_grant` (`POST /api/admin/credits/grant`,
  free `grant_credits(reason="admin_grant")`); `system_balance`
  (`GET /api/admin/system-balance`, reads OpenRouter via `LLM_API_KEY`, 503 if no
  key). `core/credits.py` has `grant_credits`, `CREDITS_PER_DOLLAR = 1000`.
- `web/auth/identity.py` — `_resolve_or_provision`: once an Identity row exists,
  login returns the account WITHOUT re-checking the allowlist. So removing an
  allowlist row does not lock out an existing user — a ban flag is required.
- `web/tenancy.py` — `current_profile_id` resolves the real account in production;
  the natural enforcement point to reject banned accounts mid-session.
- `react-dashboard/src/components/admin/ManageUsers.jsx` — invite form + users
  table + purchases modal.
- `db/database.py` `Account` — has `email, is_admin, profile_id, credit_balance,
  tier, banned?` (banned added here).

## Design

### Part 1 — `banned` flag (DB + enforcement)

- **Migration** `aa04bans01_add_account_banned`: add `account.banned BOOLEAN NOT
  NULL DEFAULT false`. `Account` model gains `banned = Column(Boolean,
  nullable=False, default=False)`.
- **Login enforcement** (`web/auth/identity.py`): in `_resolve_or_provision`,
  after resolving an existing identity to an account (the `if ident is not None`
  branch), raise `BetaAccessDenied(email)` if `account.banned`. This blocks future
  logins for banned users.
- **Session enforcement** (`web/tenancy.py`): in `current_profile_id`'s production
  branch, after resolving the real `acct`, raise `HTTPException(401)` if
  `acct.banned`. This blocks an already-logged-in banned user on their next API
  call. (Impersonation/admin paths are unaffected — admins are never banned; the
  ✕ is hidden on admin rows.)

### Part 2 — Access (ban/restore) endpoint

`POST /api/admin/users/{profile_id}/access` body `{banned: bool}`, behind
`require_real_admin`:
- 404 if no `Account` with that `profile_id`.
- 400 if the target account `is_admin` (admins cannot be banned).
- Set `target.banned = body.banned`.
- When banning (`banned=true`): also delete the `allowed_email` row matching the
  target's email (so returning requires a fresh invite). Restoring
  (`banned=false`) clears the flag only (the identity still exists, so login
  works again without re-adding to the allowlist).
- Return `{profile_id, banned}`.

### Part 3 — Grant budget + capped grant

**Shared balance helper** (`web/routers/credits.py`): extract the OpenRouter fetch
into `def openrouter_remaining() -> float | None` returning remaining USD, or
`None` when `LLM_API_KEY` is unset or the request fails. Refactor
`system_balance` to use it (preserving its existing 503/502 behavior). 

**`GET /api/admin/grant-budget`** (new, `require_real_admin`):
- `remaining = openrouter_remaining()`.
- If `remaining is None`: return `{system_credits: null, allocated, available:
  null}` (allocated still computed).
- Else: `system_credits = round(remaining * 1000)`;
  `allocated = sum(credit_balance) over non-admin accounts`;
  `available = max(system_credits - allocated, 0)`.
- Return `{system_credits, allocated, available}`.

**`POST /api/admin/users/{profile_id}/grant`** body `{amount: int}` (new,
`require_real_admin`):
- 404 unknown profile; 400 if target `is_admin`; 400 if `amount <= 0`.
- Recompute `available` server-side (as above). **Fail-closed:** if
  `available is None` (system balance unavailable) → 409 `{"error":
  "system_balance_unavailable"}`. If `amount > available` → 400 `{"error":
  "exceeds_grant_budget", "available": available}`.
- Otherwise `grant_credits(db, profile_id, amount, reason="admin_grant",
  created_by=admin.id)` and return `{granted: amount, balance: <new balance>}`.

This leaves the existing `/api/admin/credits/grant` untouched.

### Part 4 — `GET /api/admin/users` adds `banned`

Each row gains `banned` (bool). Ordering unchanged (profile_id asc).

### Part 5 — Frontend (`ManageUsers.jsx`)

State for `users`, `search`, `sortKey` (`email|tier|credits`), `sortDir`
(`asc|desc`), `grantFor` (profile_id|null), `revokeFor` (user|null), and
`budget` (from `grant-budget`).

- **Derived rows:** filter `users` by `search` (case-insensitive email substring),
  then sort by `sortKey`/`sortDir`. Admins sort by their displayed credits value
  treated as `-Infinity`/`0` consistently (admin credits = `—`, sort them to one
  end). Keep it simple: sort admins' credit value as `-1`.
- **Search input** above the table.
- **Headers** are buttons; clicking toggles `sortDir` (or switches `sortKey` and
  resets to `asc`); active header shows ▲/▼. All headers and cells **left-aligned**
  (`text-left`); the action column is left-aligned too.
- **Admin badge:** a gold `ADMIN` chip after the email when `u.is_admin`.
- **Credits cell:** admin rows render `—` (not clickable). Non-admin rows render
  the number as a button that opens the grant modal.
- **Banned rows:** dimmed (`opacity-60`) with a red `BANNED` tag near the email.
- **Revoke ✕:** shown only on non-admin rows. For an active user it's a red ✕
  opening the revoke modal; for a banned user it's a restore (↺) that calls
  `setUserAccess(pid, false)` directly (no modal needed) and refreshes.
- **Revoke modal:** "Revoke access for {email}? This bans their login and removes
  them from the allowlist." Cancel / Confirm (red). Confirm →
  `setUserAccess(pid, true)` → refresh users.
- **Grant modal:** shows `available` from `budget` ("Up to {available} credits
  available"). Amount input (positive integer, max = `available`) **defaults to
  `min(100, available)`** each time the modal opens (100 when the budget allows,
  clamped down if fewer credits are available). If
  `budget.available == null`, show "System balance unavailable — grants are
  disabled" and disable the submit. Submit → `grantCredits(pid, amount)` → on
  success refresh users + budget; on 400/409 show the returned error.

### Part 6 — API client (`api.js`)

- `setUserAccess(profileId, banned)` → POST `/api/admin/users/{id}/access`
  `{banned}`.
- `getGrantBudget()` → GET `/api/admin/grant-budget`.
- `grantCredits(profileId, amount)` → POST `/api/admin/users/{id}/grant`
  `{amount}`.

(`getUsers` already exists and now returns `banned`.)

## Data Shapes

- `GET /api/admin/users` → `[{profile_id, email, tier, credits, is_admin, banned}]`.
- `GET /api/admin/grant-budget` → `{system_credits: int|null, allocated: int,
  available: int|null}`.
- `POST /api/admin/users/{id}/grant` → `{granted, balance}` | error body.
- `POST /api/admin/users/{id}/access` → `{profile_id, banned}`.

## Testing

**Backend:**
- Migration parity (alembic vs model) for `account.banned`.
- Seam: banned real account → 401; non-banned → normal pid.
- Login: existing identity whose account is banned → `BetaAccessDenied`.
- `access`: bans + deletes allowlist row; restore clears flag; 404 unknown; 400 on
  admin target; 403 non-admin.
- `grant-budget`: with `openrouter_remaining` monkeypatched to a number →
  `available = system_credits - allocated` (allocated excludes admins); patched to
  `None` → `available null`.
- `users/{id}/grant`: success path grants + caps; `amount > available` → 400;
  `available None` → 409; admin target → 400; `amount<=0` → 400; non-admin → 403.
- `users` response includes `banned`.

**Frontend:** no JS test framework — `npm run build` + manual (badge shows; admin
credits `—`; search filters; headers sort with ▲/▼; left-aligned; ✕ bans via modal
and dims row; restore works; grant modal caps at available and refreshes).

## Non-Goals / YAGNI

- No bulk actions, no audit log, no email on ban.
- No editing tier from this table (separate endpoint already exists).
- Grant budget uses the live OpenRouter number; no persisted system-credit ledger.
- Search/sort are client-side (fine at current scale).

## Affected Files

- `db/database.py` — `Account.banned`.
- `alembic/versions/aa04bans01_add_account_banned.py` — migration.
- `web/auth/identity.py` — ban check on login.
- `web/tenancy.py` — ban check in the production seam.
- `web/routers/credits.py` — `openrouter_remaining` helper; refactor
  `system_balance`.
- `web/routers/admin.py` — `access`, `grant-budget`, `users/{id}/grant`; `banned`
  in `list_users`.
- `react-dashboard/src/api.js` — `setUserAccess`, `getGrantBudget`, `grantCredits`.
- `react-dashboard/src/components/admin/ManageUsers.jsx` — badge, search, sort,
  left-align, revoke modal + restore, grant modal, admin-credits `—`.

## Deployment Notes

Migration (`account.banned`) runs on startup. No new env vars. The grant cap is
enforced only where the system balance is readable (production with `LLM_API_KEY`);
in local dev without the key, grants are disabled (fail-closed).
