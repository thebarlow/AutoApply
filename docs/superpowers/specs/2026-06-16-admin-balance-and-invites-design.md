# Admin System-Balance Display & Invite Flow — Design

**Date:** 2026-06-16
**Status:** Approved (pending spec review)

## Goal

Two related admin-only capabilities:

1. **Admin balance display** — admins draw from the platform (system) balance, not
   personal credits. Wherever a normal user sees their credit balance, an admin
   instead sees the total system balance, with a click that toggles between a
   dollar amount and the equivalent credit amount.
2. **Admin invite flow** — an Admin tab in the navbar (admin-only) linking to a
   page that invites new users: sends them an email and adds their address to the
   app's allowlist.

## Context / Existing Infrastructure

- `Account.is_admin` exists; admins are provisioned with `credit_rate = 0.0`, so
  they already never deplete personal credits. All LLM calls already use the
  platform OpenRouter key, so admins already effectively draw from the system
  pool. **Req 1 is therefore display-only — no ledger change.**
- `GET /api/admin/system-balance` (`web/routers/credits.py`) returns the
  OpenRouter remaining balance in USD, gated by `require_admin`.
- `CreditBalance.jsx` renders personal credits; it is shown in `UserHome` via
  `variant="settings"` (click → Buy modal). A separate `SystemBalancePanel` in
  `UserHome` already shows the system balance to admins.
- `getMe()` exposes `is_admin` to the frontend; `App` already fetches `me`.
- `is_allowed_email()` / `is_admin_email()` (`web/auth/identity.py`) read the
  `ALLOWED_EMAILS` / `ADMIN_EMAILS` **env vars** fresh on each login.
- `CREDITS_PER_DOLLAR = 1000` (`core/credits.py`).
- No email-sending infrastructure exists anywhere in the project.

## Design

### Part 1 — Admin balance display (display-only)

No ledger or pricing change. Admins keep `rate = 0`.

- `CreditBalance.jsx` becomes admin-aware. It already reads `me` indirectly; pass
  an explicit `isAdmin` prop (resolved in `UserHome` from `getMe()`), so the
  component does not fetch identity itself.
  - **Non-admin:** unchanged — shows `{balance} credits`, click → Buy modal.
  - **Admin:** fetches `getSystemBalance()` and shows the system balance instead
    of personal credits. Click does **not** open the Buy modal.
- **Unit toggle (admin only):** local component state `unit` ∈ {`usd`, `credits`}.
  - `usd` (default): `$X.XX` from `remaining`.
  - `credits`: `{round(remaining * 1000)} credits`.
  - Clicking the balance toggles between the two. No server round-trip.
- The standalone `SystemBalancePanel` in `UserHome` is **removed** — folded into
  the swapped `CreditBalance` so the system balance isn't shown twice.

### Part 2 — Allowlist moves to the DB

- New table `allowed_email`:
  - `id` (PK)
  - `email` (unique, lowercased)
  - `invited_by` (int, nullable — `account.id` of the inviting admin)
  - `created_at` (ISO string, matching existing convention)
- `is_allowed_email(email)` checks the `ALLOWED_EMAILS` env set **OR** a matching
  `allowed_email` row. The env var remains as the bootstrap mechanism (initial
  admins/allowlist); the table holds runtime invites. **Signature change:**
  `is_allowed_email` gains a `db: Session` parameter; update its single caller in
  `_resolve_or_provision`.
- Inserts are idempotent (ignore if the email already exists in the table).

### Part 3 — Invite backend

New router `web/routers/admin.py` (keeps `credits.py` focused), mounted in
`web/main.py`. All routes behind `require_admin` (imported from `credits.py` or
moved to a shared `web/auth/deps.py` — implementer's call; prefer importing the
existing one to avoid churn).

- `POST /api/admin/invite` — body `{ "email": str }`.
  - Normalize (strip, lowercase) and validate basic email shape.
  - Insert `allowed_email` row if absent (idempotent), `invited_by = admin.id`.
  - Call `core.email.send_invite(email)`.
  - Return `{ "email": ..., "already_invited": bool, "emailed": bool }`.
- `GET /api/admin/invites` — list invited emails (table rows) for display on the
  admin page: `[{ "email", "created_at" }]`.

### Part 4 — Email sending

New module `core/email.py`:

- `send_invite(to_email: str) -> bool`
  - Reads `ZOHO_SMTP_USER` and `ZOHO_SMTP_PASSWORD` from env.
  - If either is unset → log and return `False` (no send). This keeps the invite
    endpoint working in local/dev without SMTP configured; the allowlist insert
    still happens.
  - Otherwise connect via `smtplib.SMTP_SSL("smtp.zoho.com", 465)`, log in, and
    send a plain `email.message.EmailMessage`.
  - From: `ZOHO_SMTP_USER`. Subject: "You're invited to Auto Apply".
  - Body: invitation pointing to `https://autoapply.matthewbarlow.me`, instructing
    the recipient to sign in with this email address. **No token** — access is
    gated entirely by the allowlist + OAuth login.
  - App host configurable via `APP_BASE_URL` env (default the production URL).
- Config: `ZOHO_SMTP_USER`, `ZOHO_SMTP_PASSWORD` in `.env` (gitignored) and
  Railway env. Zoho requires an **app-specific password** when 2FA is enabled.

### Part 5 — Frontend

- `App.jsx` passes `me` to `<Navbar me={me} />`.
- `Navbar.jsx` renders an **Admin** link (to `/admin`) only when `me?.is_admin`.
- New route in `App.jsx`: `/admin` → `AdminPage.jsx`. Client-side guard: if
  `!me?.is_admin`, redirect/render nothing (server enforces via `require_admin`
  regardless).
- `AdminPage.jsx`:
  - Email input + "Send Invite" button → `inviteUser(email)`.
  - Inline success/error feedback (e.g. "Invited — email sent" vs
    "Added to allowlist (email not configured)" vs "Already invited").
  - List of existing invites from `getInvites()`, refreshed after a successful
    invite.
- `api.js`: add `inviteUser(email)` (POST) and `getInvites()` (GET).

### DB / Migration

- Alembic migration in `alembic/versions/` adding the `allowed_email` table,
  following the existing migration style (revision chained off the current head).
- `db/database.py` gains the `AllowedEmail` model.
- `init_db.py` remains idempotent for local SQLite (table auto-created via
  metadata / create_all path used by the other models).

## Testing

- `core/email.py`: with SMTP env unset → `send_invite` returns `False`, no
  network. With env set → `smtplib.SMTP_SSL` mocked; assert login + send called.
- Allowlist: `is_allowed_email` returns `True` for an env-listed address AND for a
  `allowed_email` table row; `False` otherwise.
- `POST /api/admin/invite`: 403 for non-admin; inserts row + sets `invited_by`;
  idempotent on repeat (`already_invited: true`, no duplicate row); invokes
  `send_invite`.
- `GET /api/admin/invites`: 403 for non-admin; returns inserted rows.
- Frontend (light): Admin link hidden when `me.is_admin` is false.

## Non-Goals / YAGNI

- No invite tokens, expiry, or revocation UI (allowlist + OAuth is the gate).
- No HTML email templates — plain text only.
- No change to admin credit ledger semantics (rate=0 already makes usage free).
- No bulk invite / CSV import.

## Affected Files

- `db/database.py` — `AllowedEmail` model.
- `alembic/versions/<new>.py` — migration.
- `web/auth/identity.py` — `is_allowed_email` checks DB; caller update.
- `web/routers/admin.py` — new router (invite, list).
- `web/main.py` — mount admin router.
- `core/email.py` — new SMTP module.
- `react-dashboard/src/App.jsx` — pass `me` to Navbar; `/admin` route.
- `react-dashboard/src/components/Navbar.jsx` — admin link.
- `react-dashboard/src/components/AdminPage.jsx` — new page.
- `react-dashboard/src/components/widgets/CreditBalance.jsx` — admin swap + toggle.
- `react-dashboard/src/components/widgets/UserHome.jsx` — drop `SystemBalancePanel`,
  pass `isAdmin` to `CreditBalance`.
- `react-dashboard/src/api.js` — `inviteUser`, `getInvites`.
- `.env` / Railway env — `ZOHO_SMTP_USER`, `ZOHO_SMTP_PASSWORD`, `APP_BASE_URL`.
