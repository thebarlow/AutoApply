# Extension Live/Local Server Toggle — Design

**Date:** 2026-07-19
**Status:** Approved (brainstorming complete)
**Branch:** `feat/ats-detection` (lands alongside the ATS-detection work so the extension
can be smoke-tested against a local server before that feature is deployed).

## Context

The browser extension's base URL is hardcoded to the live app
(`https://autoapply.matthewbarlow.me`) in two places: `popup/popup.js` (`const SERVER`)
and `background/service_worker.js` (`const SERVER`). There is no way to point the
extension at a locally-running server, so extension-dependent features (e.g. the new ATS
detection flow) cannot be exercised end-to-end until they are deployed to production.

This adds an **admin-only** toggle that switches where scraped jobs are sent — Live vs.
a local dev server — without touching identity/auth, which always stays Live.

## Goals

- Let an admin route `stage-job` / ATS-resolution requests to a local server
  (`http://localhost:8080`) instead of the live app, from the extension popup.
- Require login to use the extension at all (already enforced; preserved).
- Restrict the toggle to admin accounts; non-admins never see it and always target Live.
- No backend changes.

## Non-goals

- No editable/arbitrary base URL — the local target is the fixed `http://localhost:8080`
  (the port `start.bat` uses). A two-way Live/Local switch only.
- No local OAuth. Sign-in and identity are always resolved against the live server.
- No per-mode dedup. Mode-switch collisions are handled by the existing
  "Clear scrape history" popup button.
- No change to the ATS-detection backend or the sign-in/redirect flow.

## Key facts this design relies on

- `GET /api/ext/me` **already returns `is_admin`** (`web/auth/routes.py:398`) and is live
  on `main` today — so admin-gating needs no backend change and has no deploy bootstrap.
- The production auth gate only activates when `APP_ENV == "production"`
  (`web/auth/middleware.py:31`). A local server does **not** gate `/api/*`.
- `bearer_or_session_profile` (`web/auth/ext_token.py:119`) falls back to
  `current_profile_id` (session / dev stub) when **no** bearer token is present, but
  raises `401 {"error": "no_account"}` when a token **is** present but does not resolve.
  Therefore local requests must be sent **without** an `Authorization` header (a live
  token would fail to resolve on the local DB and 401).

## Architecture

### Stored state

One new key in `xb.storage.local`:

| Key | Values | Default | Meaning |
|---|---|---|---|
| `serverMode` | `"live"` \| `"local"` | `"live"` | Where scraped jobs are sent. Identity is always Live regardless. |

### Server resolver (pure)

A pure function maps mode → base URL, used by the service worker (and available to the
popup if needed):

```
resolveServerUrl(mode) -> string
  "local" -> "http://localhost:8080"
  otherwise -> "https://autoapply.matthewbarlow.me"   // "live" and any unknown value
```

Unknown/absent mode falls back to Live (fail-safe: never accidentally target localhost).
This is the one unit-tested piece; extract it so its logic is verifiable in isolation.

### Identity vs. job routing — the core split

- **Identity (always Live):** `SIGN_IN`, `signOut` revoke, and `GET /api/ext/me` always
  hit the live URL. `is_admin`, the greeting, and login enforcement are Live-derived.
- **Job routing (toggleable, admin-only):** only `POST /api/scraper/stage-job` and
  `PATCH /api/scraper/jobs/{job_key}/ats-resolution` honor `serverMode`.

This keeps "using the extension requires login" true: the toggle is unreachable until an
admin is signed in against Live.

## Component changes

### `popup/popup.html` + `popup/popup.js`

- The `SERVER` const in the popup remains the **live** URL — identity is Live-only.
- On render, the existing `/api/ext/me` response now also reads `is_admin`.
- **Non-admin (`is_admin` false/absent):** toggle stays hidden. No behavior change.
- **Admin:** render a Live / Local toggle (two radio inputs or a labeled control) in the
  signed-in section, initialized from `serverMode`. On change: write `serverMode` to
  storage and re-render. Show the current target (e.g. "Sending jobs to: localhost:8080").
- The toggle is only shown in the signed-in state (it is meaningless when signed out).

### `background/service_worker.js`

- Replace the hardcoded `const SERVER` **for job-submission calls** with an async
  `getServer()` that reads `serverMode` and applies `resolveServerUrl`.
- `SIGN_IN` (`/auth/ext/login/...`) continues to use the live URL unconditionally.
- In the `SCRAPE_JOB` / `stage-job` handler and the ATS-resolution `PATCH`:
  - **live mode:** unchanged — read `extToken`, send `Authorization: Bearer`, and keep the
    `no_account` short-circuit that blocks POSTing when no token exists.
  - **local mode:** send the request **without** an `Authorization` header, and **bypass**
    the `no_account` short-circuit so a tokenless POST proceeds. (The local server resolves
    the active profile via the dev-stub path.)

## Data flow

1. Admin opens popup → `/api/ext/me` (Live) returns `{ email, is_admin: true, ... }` →
   toggle renders, initialized from `serverMode`.
2. Admin flips to **Local** → `serverMode = "local"` stored.
3. Admin scrapes a job → service worker resolves base URL to `http://localhost:8080`,
   POSTs `stage-job` **without** an auth header → local server stages it under the
   dev-stub profile → (for external jobs) the ATS-resolution `PATCH` also goes to
   localhost, tokenless.
4. Admin flips back to **Live** → subsequent scrapes send the live token to the live app
   exactly as before. (Uses "Clear scrape history" if a job needs re-sending across modes.)

## Error handling / edge cases

- **Unknown/absent `serverMode`** → resolver returns Live (fail-safe).
- **Non-admin somehow has `serverMode="local"` stored** (e.g. was admin, then wasn't): the
  toggle is hidden, but the worker would still read `local`. Mitigation: the worker only
  honors `local` — acceptable, but the popup should reset `serverMode` to `"live"` when it
  renders for a non-admin, so a demoted account cannot silently keep targeting localhost.
- **Local server down** → the POST fails with a network error; the existing scrape-button
  error states ("✗ Timeout" / "✗ Server error") surface it. No special handling.
- **Cross-mode dedup collision** → "✗ Already staged"; resolved by "Clear scrape history".

## Testing

- **Unit:** `resolveServerUrl(mode)` — `"local"` → localhost, `"live"`/unknown/undefined →
  live. (The only automated test; extension DOM/flow follows the existing manual-smoke
  posture.)
- **Manual smoke test (maintainer, in Chrome/Firefox):**
  - Non-admin account: toggle is absent; scraping targets Live.
  - Admin account: toggle present; defaults to Live; live scraping unchanged.
  - Admin, Local mode: start the local server (`start.bat`), scrape a job, confirm it lands
    in the **local** DB with no auth error and no `Authorization` header sent (verify in the
    service-worker console / network panel).
  - Admin, Local mode, external job: confirm the ATS-resolution `PATCH` also reaches
    localhost tokenless.
  - Flip back to Live: confirm requests carry the bearer token and hit the live app.

## Open risks / accepted limitations

- **Demoted-admin residual mode** — handled by resetting `serverMode` to `"live"` on
  non-admin render (see edge cases).
- **Dedup across modes** — intentionally manual ("Clear scrape history").
- **No arbitrary URL / no LAN testing** — out of scope by choice; revisit only if needed.
