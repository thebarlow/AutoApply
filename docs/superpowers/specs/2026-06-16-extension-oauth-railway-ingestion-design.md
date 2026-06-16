# Extension OAuth + Railway Ingestion — Design

**Date:** 2026-06-16
**Status:** Approved (brainstorming) → ready for implementation plan
**Sub-project:** A of two. Sub-project B (professional packaging & store publishing for
Chrome Web Store + Firefox AMO) is deferred to its own spec, to be written only after
A "works well on both" browsers.

## Problem

The browser extension already injects a "Scrape" button on LinkedIn **and** Indeed and
POSTs scraped jobs to `POST /api/scraper/stage-job`. But it targets a **configurable
localhost URL with no authentication** (`browser-extension/background/service_worker.js`).
The app is now a deployed multi-tenant SaaS at `https://autoapply.matthewbarlow.me` where
every API request must resolve a tenant (`web/tenancy.py:current_profile_id`) and the prod
auth gate (`web/auth/middleware.py`) 401s any unauthenticated `/api/*`. The extension has
no way to (a) reach the live server or (b) prove which account a scraped job belongs to.

Two prior assumptions were corrected during brainstorming:
1. Indeed support is **not** missing — it exists (`content/indeed.js`, manifest matches,
   button renders). The open question is whether its **selectors still extract correctly**
   against current Indeed DOM.
2. This is therefore an **auth + ingestion rework**, not an "add Indeed" task.

## Goals

- Scraping works against the live Railway server for **both** LinkedIn and Indeed.
- Each scraped job is associated with the correct account via **in-extension OAuth**
  (Google/GitHub), the same providers as the website.
- A user with no AutoApply account who signs in via the extension is **rejected** with a
  clear message ("Cannot find AutoApply account — sign up at the website first"). The
  website remains the single sign-up / onboarding front door.
- One extension codebase runs on **Chrome and Firefox**.
- No regression to the main web app's session-cookie security (CSRF posture unchanged).

## Non-Goals (this sub-project)

- Store packaging, signing, store-listing assets, publishing (→ sub-project B).
- Auto-mark-as-applied on submission (separate future item in extension `CONTEXT.md`).
- Provisioning new tenants from the extension (explicitly rejected — Option B).
- Changing the website's own OAuth/session behavior.

## Decisions (locked during brainstorming)

| Decision | Choice |
|---|---|
| Auth mechanism | **OAuth inside the extension** via `identity.launchWebAuthFlow`, exchanged for a backend-minted bearer token |
| Credential carried on requests | **Opaque extension token** (`Authorization: Bearer`), *not* the website session cookie (keeps session `SameSite=Lax`, no CSRF regression) |
| Token lifetime | **Long-lived, revocable** — no expiry; invalidated on sign-out or admin ban |
| New users from the extension | **Rejected** (resolve-only; no provisioning) |
| Browser targets | **Chrome + Firefox** (thin `browser.*` shim) |

## Architecture

### Auth flow (happy path)

```
Popup: [Sign in with Google] / [Sign in with GitHub]
   │  browser.identity.launchWebAuthFlow({ url, interactive:true })
   │  url = https://autoapply.matthewbarlow.me/auth/ext/login/{provider}
   │        ?redirect_uri=<ext redirect URL>
   ▼
Backend GET /auth/ext/login/{provider}
   │  validate redirect_uri against EXTENSION_REDIRECT_URLS allowlist
   │  stash redirect_uri + ext-mode flag in OAuth session
   │  run existing Google/GitHub authorize_redirect
   ▼
Provider consent → Backend GET /auth/callback/{provider}
   │  _fetch_claims (unchanged)
   │  ext-mode? → resolve_existing_account(db, claims)   # NO provisioning
   │     ├─ no account / banned → 302 ext_redirect#error=no_account
   │     └─ account found       → mint extension token, store hash
   │        302 ext_redirect#token=<opaque token>
   ▼
Extension extracts token from returned URL → browser.storage.local
   │  GET /api/me-equivalent for display email (reuse bearer-authed identity echo)
   ▼
Scrape → service_worker POST /api/scraper/stage-job
         Authorization: Bearer <token>
```

### Why a token instead of the session cookie

Reusing the website session cookie cross-origin from the extension would require
`SameSite=None; Secure`, which weakens CSRF protection for the *entire* API (delete jobs,
spend credits). A dedicated extension token isolates the extension's authority to exactly
the requests it makes and is independently revocable.

### Open-redirect guard (mandatory)

The token is delivered to whatever `redirect_uri` the login request specifies. Without an
allowlist this is a token-exfiltration hole. `redirect_uri` MUST exactly match an entry in
the `EXTENSION_REDIRECT_URLS` env var (comma-separated), which holds both:
- Chrome: `https://<chrome-extension-id>.chromiumapp.org/`
- Firefox: the value of `browser.identity.getRedirectURL()` for the pinned Firefox id

A non-matching `redirect_uri` → `400`, no OAuth started.

## Components

### Backend

**New table `extension_token`** (Alembic migration; SQLite + Postgres):

| column | type | notes |
|---|---|---|
| `id` | int PK | |
| `account_id` | int FK → account.id | |
| `token_hash` | str, unique, indexed | sha256 of the opaque token; raw token never stored |
| `created_at` | str (ISO) | |
| `last_used_at` | str (ISO), nullable | updated on use (best-effort) |
| `revoked` | bool, default False | |

**`web/auth/identity.py`** — add a pure, resolve-only function:

```
resolve_existing_account(db, claims) -> Account
```
Mirrors `_resolve_or_provision` **minus** provisioning:
- identity exists → its account (reject if banned)
- else account exists by verified email → **link** the new identity, return it
  (same person, already has an account; no allowlist gate needed since they're already in)
- else → raise `NoExtensionAccount` (new exception) — do NOT provision.
Unverified email → raise (reuse `BetaAccessDenied` semantics or a shared guard).

**`web/auth/ext_token.py`** (new) — token lifecycle + dependency:
- `mint_token(db, account_id) -> str` — generate `secrets.token_urlsafe(32)`, store sha256, return raw.
- `resolve_token(db, raw) -> Account | None` — hash, look up unrevoked row, reject banned account, bump `last_used_at`.
- `revoke_token(db, raw) -> None`.
- FastAPI dependency `profile_from_extension_token(request, db) -> int` — reads
  `Authorization: Bearer`, resolves, returns `profile_id`; `401 {"error":"no_account"}` on miss.

**`web/auth/routes.py`**:
- `GET /auth/ext/login/{provider}` — validate `redirect_uri`, stash `{ext_redirect, ext_mode}` in `request.session`, run `authorize_redirect`.
- `auth_callback` — branch on `request.session.pop("ext_mode", ...)`:
  - ext-mode: `resolve_existing_account`; on success mint token + `RedirectResponse(ext_redirect + "#token=" + raw)`;
    on `NoExtensionAccount`/denied → `RedirectResponse(ext_redirect + "#error=no_account")`.
  - normal mode: unchanged (sets `account_id` session, redirects `/`).
- `POST /auth/ext/revoke` — bearer-authed; revokes the presented token. (Exempt from cookie gate.)
- Identity echo for the popup: either extend `/api/me` to accept a bearer token, **or** add
  `GET /api/ext/me` (bearer-authed) returning `{email}`. Decision: add `GET /api/ext/me`
  to avoid entangling the cookie-only `/api/me`.

**`web/routers/scraper.py`** — `stage-job` dependency becomes "bearer token **or** session":
a small combined dependency that tries `profile_from_extension_token` first and falls back
to `current_profile_id` (preserving local-dev/tray session + dev-stub behavior). `/run` is
unchanged (dormant, session-only).

**`web/auth/middleware.py`** — add `/api/scraper/stage-job`, `/api/ext/me`, `/auth/ext/login`,
`/auth/ext/revoke` to `_EXEMPT_PATHS` (the `/auth/*` paths already pass; `stage-job` and
`/api/ext/*` need exemption because they are bearer-authed, not cookie-authed — same pattern
as the Stripe webhook exemption).

**Env / config:** `EXTENSION_REDIRECT_URLS` (comma-separated allowlist). Documented in
`.env.example` and Railway. No secret value.

### Extension

**`manifest.json`**:
- Add `"identity"` permission.
- Pin a **stable extension id**: Chrome `"key"` (public key), Firefox `gecko.id` (already
  present) — required so the `chromiumapp.org` / Firefox redirect URLs are deterministic and
  can be allowlisted server-side.
- `host_permissions`: `https://autoapply.matthewbarlow.me/*` (default). Keep an optional dev
  override path but remove the user-facing raw-URL field.

**Browser-API shim** (`content/browser_shim.js` or similar): tiny wrapper exposing the subset
used — `identity`, `storage`, `runtime` — bridging `chrome.*` (callback) vs `browser.*`
(promise). Hand-rolled per the stdlib-first preference; `webextension-polyfill` only if the
shim grows unwieldy.

**`popup/`**:
- Sign-in buttons (Google / GitHub) → `launchWebAuthFlow` → parse `#token`/`#error` from the
  returned URL → store token / show error.
- Signed-in state: show account email (via `GET /api/ext/me`), "Sign out" (delete local token
  + best-effort `POST /auth/ext/revoke`).
- Keep "clear dedup history". Remove the FastAPI base-URL input.

**`background/service_worker.js`**:
- Read token from storage; attach `Authorization: Bearer`.
- No token or `401` → return a typed result `{ok:false, error:"no_account"}`.
- Success path unchanged (dedup + status).

**`content/injector.js`**: add an inline button state **"✗ Sign in required"** when
`error === "no_account"`, surfacing the auth failure where the user clicked (the on-screen
error the user requested).

## Indeed verification (treated as untested, not assumed-working)

The button renders, but `indeed.js` selectors (`.job_seen_beacon`, `.companyName`,
`.companyLocation`, `#jobDescriptionText`) are dated. The plan includes a **live end-to-end
smoke test** against current Indeed DOM:
- `www.indeed.com/jobs` search card: title, company, location, URL, `jk` job_key, description.
- `myjobs.indeed.com` saved job card: same fields.
- Repair selectors if any field is wrong/empty. Record stable selectors + any positional
  fragility in `browser-extension/CONTEXT.md` (mirroring the existing LinkedIn notes).

A parallel LinkedIn smoke test against prod confirms no regression from the auth rework.

**Constraint:** driving a logged-in LinkedIn/Indeed browser cannot be automated here; the
maintainer runs the smoke checklist manually and reports field-by-field results, which feed
any selector repairs.

## Error handling

| Condition | Backend | Extension UX |
|---|---|---|
| `redirect_uri` not allowlisted | `400`, no OAuth | login fails silently in popup; log + generic "Sign-in failed" |
| OAuth provider error | `302 ext_redirect#error=auth` | popup: "Sign-in failed, try again" |
| Verified-email check fails | treated as no_account | `#error=no_account` |
| No AutoApply account / banned | `302 ext_redirect#error=no_account` | popup: "Cannot find AutoApply account — sign up at autoapply.matthewbarlow.me" |
| `stage-job` with bad/absent token | `401 {"error":"no_account"}` | button: "✗ Sign in required" |
| Duplicate job | `200 {"status":"duplicate"}` | button: "✓ Already staged" (unchanged) |

## Testing

**Backend (pytest, monkeypatch `_fetch_claims` per existing auth tests):**
- `mint_token` / `resolve_token` / `revoke_token` round-trip; only the hash is persisted.
- `resolve_existing_account`: identity hit; email-link of a second provider; brand-new email
  → `NoExtensionAccount`; banned account → rejected.
- `redirect_uri` allowlist: matching passes, non-matching → `400`.
- ext-mode callback: success → `#token=` redirect to the right URL; no account → `#error=no_account`.
- `stage-job`: authorized via bearer; authorized via session (dev/test); rejected with no creds.
- middleware: exempt paths reachable without a cookie; non-exempt `/api/*` still 401.

**Extension:** manual smoke checklist (no JS test harness exists). Sign-in on both browsers,
token persistence, scrape success, signed-out rejection state, sign-out/revoke.

## Migration / rollout

- Alembic migration for `extension_token` (runs on Railway startup, per existing pattern).
- Set `EXTENSION_REDIRECT_URLS` on Railway before deploy.
- Extension distributed as unpacked/temporary load during this sub-project (pinned ids);
  store publishing is sub-project B.

## Open risks

- **Pinned Chrome id without store publish:** the `"key"` in `manifest.json` fixes the id for
  unpacked loads so `chromiumapp.org` matches the allowlist. When B publishes to the store,
  the assigned id must match (or the allowlist must be updated). Note this in B's spec.
- **Indeed/LinkedIn DOM drift:** selectors may already be broken; repair is in-scope but
  depends on manual live inspection.
