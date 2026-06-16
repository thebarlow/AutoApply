# Extension OAuth + Railway Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the browser extension scrape jobs from LinkedIn and Indeed straight into the live Railway server, authenticated per-account via in-extension Google/GitHub OAuth exchanged for a long-lived revocable bearer token.

**Architecture:** The extension runs OAuth via `identity.launchWebAuthFlow` against a new backend ext-login route, which reuses the existing Google/GitHub flow and — for already-existing accounts only — mints an opaque token delivered to the extension's allowlisted redirect URL. The extension stores the token and sends it as `Authorization: Bearer` on `/api/scraper/stage-job`, which the backend resolves to a tenant. The main web app's cookie/session security is untouched.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Authlib (existing), pytest; WebExtensions MV3 (Chrome + Firefox) with a hand-rolled `browser.*` shim.

## Global Constraints

- Token credential only — never loosen the website session cookie (stays `SameSite=Lax`). Copied from spec.
- New users from the extension are **rejected**, not provisioned (Option B). The website is the only sign-up surface.
- Token is **long-lived, revocable** — no expiry; dies on sign-out or admin ban.
- Store **only** the sha256 hash of the token; the raw token is never persisted.
- `redirect_uri` MUST exactly match an entry in env `EXTENSION_REDIRECT_URLS` (comma-separated) or the request is rejected `400` before any OAuth starts.
- Both Chrome and Firefox supported from one codebase via a `browser.*` shim (subset: `identity`, `storage`, `runtime`).
- Production base URL: `https://autoapply.matthewbarlow.me`.
- Python: type hints, black formatting, Google-style docstrings. Commit format `[type] Imperative subject`.
- Alembic migrations run on Railway startup; current head is `aa05invitetype01`.

---

## File Structure

**Backend**
- `db/database.py` — add `ExtensionToken` model.
- `alembic/versions/aa06exttoken01_add_extension_token.py` — new migration (down_revision `aa05invitetype01`).
- `web/auth/ext_token.py` — NEW: mint/resolve/revoke + `profile_from_extension_token` dependency + `bearer_or_session_profile` combined dependency.
- `web/auth/identity.py` — add `resolve_existing_account` + `NoExtensionAccount`.
- `web/auth/routes.py` — add `/auth/ext/login/{provider}`, ext-mode branch in `auth_callback`, `/auth/ext/revoke`, `/api/ext/me`; add `EXTENSION_REDIRECT_URLS` allowlist helper.
- `web/auth/middleware.py` — extend `_EXEMPT_PATHS`.
- `web/routers/scraper.py` — `stage-job` uses combined bearer-or-session dependency.
- `.env.example` — document `EXTENSION_REDIRECT_URLS`.
- `web/CONTEXT.md` — document new endpoints/table.

**Extension**
- `browser-extension/lib/browser_shim.js` — NEW: `chrome.*`/`browser.*` bridge.
- `browser-extension/manifest.json` — `identity` perm, pinned ids, host_permissions.
- `browser-extension/popup/popup.html` + `popup.js` — sign-in/out UI.
- `browser-extension/background/service_worker.js` — bearer header + typed auth error.
- `browser-extension/content/injector.js` — "Sign in required" button state.
- `browser-extension/CONTEXT.md` — selector + auth notes.

---

## Task 1: `ExtensionToken` model + migration

**Files:**
- Modify: `db/database.py` (after the `Identity` class, ~line 156)
- Create: `alembic/versions/aa06exttoken01_add_extension_token.py`
- Test: `tests/web/test_ext_token_model.py`

**Interfaces:**
- Produces: `ExtensionToken` ORM model with columns `id, account_id, token_hash, created_at, last_used_at, revoked`.

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_ext_token_model.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import Base, ExtensionToken


def test_extension_token_persists():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    tok = ExtensionToken(account_id=1, token_hash="abc", created_at="2026-06-16T00:00:00+00:00")
    session.add(tok)
    session.commit()
    row = session.query(ExtensionToken).filter_by(token_hash="abc").first()
    assert row.account_id == 1
    assert row.revoked is False
    assert row.last_used_at is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/web/test_ext_token_model.py -v`
Expected: FAIL with `ImportError: cannot import name 'ExtensionToken'`

- [ ] **Step 3: Add the model**

In `db/database.py`, after the `Identity` class:

```python
class ExtensionToken(Base):
    """A long-lived, revocable bearer token for the browser extension.

    Stores only the sha256 hash of the issued token; the raw value is returned
    once at mint time and never persisted.
    """

    __tablename__ = "extension_token"

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("account.id"), nullable=False)
    token_hash = Column(String, nullable=False, unique=True, index=True)
    created_at = Column(String, nullable=False)
    last_used_at = Column(String, nullable=True)
    revoked = Column(Boolean, nullable=False, default=False)
```

- [ ] **Step 4: Create the Alembic migration**

```python
# alembic/versions/aa06exttoken01_add_extension_token.py
"""add extension_token

Revision ID: aa06exttoken01
Revises: aa05invitetype01
Create Date: 2026-06-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "aa06exttoken01"
down_revision: Union[str, Sequence[str], None] = "aa05invitetype01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "extension_token",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("account.id"), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("last_used_at", sa.String(), nullable=True),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_extension_token_token_hash", "extension_token", ["token_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_extension_token_token_hash", table_name="extension_token")
    op.drop_table("extension_token")
```

- [ ] **Step 5: Run test + alembic check**

Run: `python -m pytest tests/web/test_ext_token_model.py -v`
Expected: PASS
Run: `python -m alembic heads`
Expected: single head `aa06exttoken01`

- [ ] **Step 6: Commit**

```bash
git add db/database.py alembic/versions/aa06exttoken01_add_extension_token.py tests/web/test_ext_token_model.py
git commit -m "[feat] Add extension_token model + migration"
```

---

## Task 2: Token lifecycle + auth dependencies (`web/auth/ext_token.py`)

**Files:**
- Create: `web/auth/ext_token.py`
- Test: `tests/web/test_ext_token_lifecycle.py`

**Interfaces:**
- Consumes: `ExtensionToken`, `Account` from `db.database`; `get_db`, `current_profile_id`.
- Produces:
  - `hash_token(raw: str) -> str`
  - `mint_token(db: Session, account_id: int) -> str` (returns raw token)
  - `resolve_token(db: Session, raw: str) -> Account | None` (None if missing/revoked/banned; bumps `last_used_at`)
  - `revoke_token(db: Session, raw: str) -> None`
  - `profile_from_extension_token(request, db) -> int` (FastAPI dependency; raises `HTTPException(401, {"error":"no_account"})`)
  - `bearer_or_session_profile(request, db) -> int` (tries bearer, else falls back to `current_profile_id`)

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_ext_token_lifecycle.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import Base, Account, ExtensionToken
from web.auth import ext_token


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    s.add(Account(id=5, email="u@x.com", profile_id=9, created_at="t"))
    s.commit()
    yield s
    s.close()


def test_mint_stores_hash_not_raw(db):
    raw = ext_token.mint_token(db, account_id=5)
    assert raw and len(raw) > 20
    row = db.query(ExtensionToken).one()
    assert row.token_hash != raw
    assert row.token_hash == ext_token.hash_token(raw)


def test_resolve_returns_account(db):
    raw = ext_token.mint_token(db, account_id=5)
    acct = ext_token.resolve_token(db, raw)
    assert acct.id == 5
    assert db.query(ExtensionToken).one().last_used_at is not None


def test_resolve_rejects_unknown(db):
    assert ext_token.resolve_token(db, "garbage") is None


def test_resolve_rejects_revoked(db):
    raw = ext_token.mint_token(db, account_id=5)
    ext_token.revoke_token(db, raw)
    assert ext_token.resolve_token(db, raw) is None


def test_resolve_rejects_banned(db):
    raw = ext_token.mint_token(db, account_id=5)
    db.query(Account).filter_by(id=5).update({"banned": True})
    db.commit()
    assert ext_token.resolve_token(db, raw) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/web/test_ext_token_lifecycle.py -v`
Expected: FAIL with `ModuleNotFoundError: web.auth.ext_token`

- [ ] **Step 3: Implement the module**

```python
# web/auth/ext_token.py
"""Browser-extension bearer tokens: mint, resolve, revoke, and FastAPI deps.

Tokens are opaque random strings; only their sha256 hash is stored. They are
long-lived and revocable (no expiry), invalidated by revoke or an account ban.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from db.database import Account, ExtensionToken, get_db
from web.tenancy import current_profile_id


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def mint_token(db: Session, account_id: int) -> str:
    """Create and persist a token for an account; return the raw token once."""
    raw = secrets.token_urlsafe(32)
    db.add(ExtensionToken(account_id=account_id, token_hash=hash_token(raw), created_at=_now()))
    db.commit()
    return raw


def resolve_token(db: Session, raw: str) -> Account | None:
    """Return the active account for a token, or None if invalid/revoked/banned."""
    if not raw:
        return None
    row = db.query(ExtensionToken).filter_by(token_hash=hash_token(raw), revoked=False).first()
    if row is None:
        return None
    acct = db.query(Account).filter_by(id=row.account_id).first()
    if acct is None or acct.banned:
        return None
    row.last_used_at = _now()
    db.commit()
    return acct


def revoke_token(db: Session, raw: str) -> None:
    row = db.query(ExtensionToken).filter_by(token_hash=hash_token(raw)).first()
    if row is not None:
        row.revoked = True
        db.commit()


def _bearer(request: Request) -> str:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return ""


def profile_from_extension_token(request: Request, db: Session = Depends(get_db)) -> int:
    acct = resolve_token(db, _bearer(request))
    if acct is None:
        raise HTTPException(status_code=401, detail={"error": "no_account"})
    return acct.profile_id


def bearer_or_session_profile(request: Request, db: Session = Depends(get_db)) -> int:
    """Resolve the tenant from an extension bearer token if present, else the
    session/dev-stub path (so local dev, tests, and the tray app keep working)."""
    raw = _bearer(request)
    if raw:
        acct = resolve_token(db, raw)
        if acct is None:
            raise HTTPException(status_code=401, detail={"error": "no_account"})
        return acct.profile_id
    return current_profile_id(request, db)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/web/test_ext_token_lifecycle.py -v`
Expected: PASS (all 5)

- [ ] **Step 5: Commit**

```bash
git add web/auth/ext_token.py tests/web/test_ext_token_lifecycle.py
git commit -m "[feat] Add extension token mint/resolve/revoke + auth deps"
```

---

## Task 3: Resolve-only account lookup (`identity.py`)

**Files:**
- Modify: `web/auth/identity.py` (add exception + function)
- Test: `tests/web/test_resolve_existing_account.py`

**Interfaces:**
- Consumes: `Claims`, `Account`, `Identity` from existing module.
- Produces:
  - `class NoExtensionAccount(Exception)`
  - `resolve_existing_account(db: Session, claims: Claims) -> Account` — returns an existing account (linking a new provider on a known verified email), never provisions; raises `NoExtensionAccount` for unknown email/unverified/banned.

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_resolve_existing_account.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import Base, Account, Identity
from web.auth.identity import Claims, resolve_existing_account, NoExtensionAccount


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def _acct(db, email="u@x.com", banned=False):
    a = Account(email=email, profile_id=7, created_at="t", banned=banned)
    db.add(a); db.commit()
    return a


def test_existing_identity_returns_account(db):
    a = _acct(db)
    db.add(Identity(account_id=a.id, provider="google", provider_subject="sub1", created_at="t")); db.commit()
    out = resolve_existing_account(db, Claims("google", "sub1", "u@x.com", True))
    assert out.id == a.id


def test_known_email_new_provider_links_identity(db):
    a = _acct(db)
    out = resolve_existing_account(db, Claims("github", "gh99", "u@x.com", True))
    assert out.id == a.id
    assert db.query(Identity).filter_by(provider="github", provider_subject="gh99").count() == 1


def test_unknown_email_rejected(db):
    with pytest.raises(NoExtensionAccount):
        resolve_existing_account(db, Claims("google", "subX", "nobody@x.com", True))


def test_unverified_email_rejected(db):
    _acct(db)
    with pytest.raises(NoExtensionAccount):
        resolve_existing_account(db, Claims("google", "subX", "u@x.com", False))


def test_banned_account_rejected(db):
    _acct(db, banned=True)
    with pytest.raises(NoExtensionAccount):
        resolve_existing_account(db, Claims("github", "gh1", "u@x.com", True))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/web/test_resolve_existing_account.py -v`
Expected: FAIL with `ImportError: cannot import name 'resolve_existing_account'`

- [ ] **Step 3: Implement**

In `web/auth/identity.py`, after the `BetaAccessDenied` class:

```python
class NoExtensionAccount(Exception):
    """Raised when an extension login has no existing AutoApply account to bind to."""
```

Add this function (near `resolve_or_provision_account`):

```python
def resolve_existing_account(db: Session, claims: Claims) -> Account:
    """Map OAuth claims to an EXISTING account; never provision (Option B).

    Links a new provider identity onto a known verified email. Raises
    NoExtensionAccount for unverified email, no matching account, or a banned
    account — the extension is a companion to a website-created account, not a
    sign-up surface.
    """
    if not claims.email or not claims.email_verified:
        raise NoExtensionAccount("email not verified")
    email = claims.email.lower()

    ident = (
        db.query(Identity)
        .filter_by(provider=claims.provider, provider_subject=claims.subject)
        .first()
    )
    if ident is not None:
        acct = db.query(Account).filter_by(id=ident.account_id).first()
        if acct is None or acct.banned:
            raise NoExtensionAccount(email)
        return acct

    acct = db.query(Account).filter_by(email=email).first()
    if acct is None or acct.banned:
        raise NoExtensionAccount(email)
    db.add(Identity(
        account_id=acct.id, provider=claims.provider,
        provider_subject=claims.subject, created_at=_now(),
    ))
    db.commit()
    return acct
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/web/test_resolve_existing_account.py -v`
Expected: PASS (all 5)

- [ ] **Step 5: Commit**

```bash
git add web/auth/identity.py tests/web/test_resolve_existing_account.py
git commit -m "[feat] Add resolve-only account lookup for extension auth"
```

---

## Task 4: Ext OAuth routes + redirect allowlist (`routes.py`)

**Files:**
- Modify: `web/auth/routes.py`
- Test: `tests/web/test_ext_auth_routes.py`

**Interfaces:**
- Consumes: `resolve_existing_account`, `NoExtensionAccount` (Task 3); `mint_token`, `revoke_token`, `profile_from_extension_token` (Task 2); existing `oauth`, `_fetch_claims`, `_PROVIDERS`.
- Produces routes:
  - `GET /auth/ext/login/{provider}?redirect_uri=...` → `400` if `redirect_uri` not in `EXTENSION_REDIRECT_URLS`, else stashes `ext_redirect`/`ext_mode` in session and runs `authorize_redirect`.
  - `auth_callback` ext-mode branch → `302 {ext_redirect}#token=...` on success, `#error=no_account` / `#error=auth` otherwise.
  - `POST /auth/ext/revoke` (bearer) → revokes presented token, `{ "ok": true }`.
  - `GET /api/ext/me` (bearer) → `{ "email": ... }`, `401` if invalid.
- Helper: `_allowed_ext_redirects() -> set[str]` reading env `EXTENSION_REDIRECT_URLS`.

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_ext_auth_routes.py
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import Base, Account, get_db
from web.main import app
import web.auth.routes as routes
from web.auth.identity import Claims
from web.auth import ext_token

REDIR = "https://abc.chromiumapp.org/"


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    s.add(Account(id=3, email="u@x.com", profile_id=4, created_at="t"))
    s.commit()
    yield s
    s.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def client(db_session, monkeypatch):
    monkeypatch.setenv("EXTENSION_REDIRECT_URLS", REDIR)
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_ext_login_rejects_bad_redirect(client):
    r = client.get("/auth/ext/login/google?redirect_uri=https://evil.com/", follow_redirects=False)
    assert r.status_code == 400


def test_ext_callback_mints_token_for_existing_account(client, db_session, monkeypatch):
    async def fake_claims(provider, request):
        return Claims("google", "sub1", "u@x.com", True)
    monkeypatch.setattr(routes, "_fetch_claims", fake_claims)
    # simulate the session state the login route would have stashed
    with client as c:
        c.cookies.clear()
        # prime session via a request that sets it:
        # call login first (it stashes + 302s to provider; we ignore provider hop)
        c.get(f"/auth/ext/login/google?redirect_uri={REDIR}", follow_redirects=False)
        r = c.get("/auth/callback/google", follow_redirects=False)
    assert r.status_code in (302, 307)
    loc = r.headers["location"]
    assert loc.startswith(REDIR + "#token=")
    token = loc.split("#token=")[1]
    assert ext_token.resolve_token(db_session, token).id == 3


def test_ext_callback_no_account_returns_error_fragment(client, monkeypatch):
    async def fake_claims(provider, request):
        return Claims("google", "subX", "nobody@x.com", True)
    monkeypatch.setattr(routes, "_fetch_claims", fake_claims)
    with client as c:
        c.get(f"/auth/ext/login/google?redirect_uri={REDIR}", follow_redirects=False)
        r = c.get("/auth/callback/google", follow_redirects=False)
    assert r.headers["location"] == REDIR + "#error=no_account"


def test_ext_me_requires_valid_token(client, db_session):
    raw = ext_token.mint_token(db_session, account_id=3)
    ok = client.get("/api/ext/me", headers={"Authorization": f"Bearer {raw}"})
    assert ok.status_code == 200 and ok.json()["email"] == "u@x.com"
    bad = client.get("/api/ext/me", headers={"Authorization": "Bearer nope"})
    assert bad.status_code == 401


def test_ext_revoke(client, db_session):
    raw = ext_token.mint_token(db_session, account_id=3)
    r = client.post("/auth/ext/revoke", headers={"Authorization": f"Bearer {raw}"})
    assert r.status_code == 200
    assert ext_token.resolve_token(db_session, raw) is None
```

> Note for implementer: the `auth_callback` ext-mode branch must read `ext_mode`/`ext_redirect` from `request.session` (set by `/auth/ext/login`) and must NOT require a real provider token exchange when `_fetch_claims` is monkeypatched — mirror the existing `test_auth_routes.py` pattern.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/web/test_ext_auth_routes.py -v`
Expected: FAIL (`404` on `/auth/ext/login/...`)

- [ ] **Step 3: Implement routes**

Add near the top of `web/auth/routes.py` imports:

```python
from web.auth.identity import NoExtensionAccount, resolve_existing_account
from web.auth.ext_token import mint_token, profile_from_extension_token, resolve_token, revoke_token, _bearer
from fastapi import Depends
```

Add helper:

```python
def _allowed_ext_redirects() -> set[str]:
    return {u.strip() for u in os.getenv("EXTENSION_REDIRECT_URLS", "").split(",") if u.strip()}
```

Add the ext-login route:

```python
@router.get("/auth/ext/login/{provider}")
async def auth_ext_login(provider: str, request: Request, redirect_uri: str = ""):
    if provider not in _PROVIDERS:
        raise HTTPException(status_code=404)
    if redirect_uri not in _allowed_ext_redirects():
        raise HTTPException(status_code=400, detail="redirect_uri not allowed")
    request.session["ext_mode"] = True
    request.session["ext_redirect"] = redirect_uri
    return await oauth.create_client(provider).authorize_redirect(
        request, _redirect_uri(request, provider)
    )
```

Modify `auth_callback` — at the very start of the body (after the provider check), branch on ext-mode:

```python
@router.get("/auth/callback/{provider}", name="auth_callback")
async def auth_callback(provider: str, request: Request, db: Session = Depends(get_db)):
    if provider not in _PROVIDERS:
        raise HTTPException(status_code=404)
    ext_mode = request.session.pop("ext_mode", False)
    ext_redirect = request.session.pop("ext_redirect", "")
    if ext_mode:
        try:
            claims = await _fetch_claims(provider, request)
        except Exception:
            return RedirectResponse(url=f"{ext_redirect}#error=auth")
        try:
            acct = resolve_existing_account(db, claims)
        except NoExtensionAccount:
            return RedirectResponse(url=f"{ext_redirect}#error=no_account")
        token = mint_token(db, acct.id)
        return RedirectResponse(url=f"{ext_redirect}#token={token}")
    # --- existing website flow unchanged below ---
    try:
        claims = await _fetch_claims(provider, request)
    except Exception:
        return RedirectResponse(url="/?auth_error=1")
    try:
        acct = resolve_or_provision_account(db, claims)
    except BetaAccessDenied:
        return RedirectResponse(url="/?beta=closed")
    request.session["account_id"] = acct.id
    return RedirectResponse(url="/")
```

> The implementer must also add `from web.auth.identity import resolve_or_provision_account, BetaAccessDenied` if not already imported (it is — keep existing import line).

Add revoke + ext-me routes:

```python
@router.post("/auth/ext/revoke")
def auth_ext_revoke(request: Request, db: Session = Depends(get_db)):
    revoke_token(db, _bearer(request))
    return {"ok": True}


@router.get("/api/ext/me")
def api_ext_me(profile_id: int = Depends(profile_from_extension_token), request: Request = None, db: Session = Depends(get_db)):
    acct = resolve_token(db, _bearer(request))
    return {"email": acct.email}
```

> `profile_from_extension_token` already 401s invalid tokens, so `api_ext_me` only runs when the token is valid; `resolve_token` re-reads the account for its email.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/web/test_ext_auth_routes.py -v`
Expected: PASS (all 5)

- [ ] **Step 5: Run the existing auth route tests (no regression)**

Run: `python -m pytest tests/web/test_auth_routes.py tests/web/test_identity.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add web/auth/routes.py tests/web/test_ext_auth_routes.py
git commit -m "[feat] Add extension OAuth login/callback/revoke + /api/ext/me"
```

---

## Task 5: Middleware exemptions

**Files:**
- Modify: `web/auth/middleware.py:19`
- Test: `tests/web/test_ext_middleware_exempt.py`

**Interfaces:**
- Consumes: `AuthGateMiddleware`.
- Produces: `/api/scraper/stage-job`, `/api/ext/me` reachable without a session cookie in production; non-exempt `/api/*` still 401.

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_ext_middleware_exempt.py
import pytest
from fastapi.testclient import TestClient

from web.main import app


@pytest.fixture
def prod_client(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    return TestClient(app)


def test_stage_job_not_gated_by_cookie(prod_client):
    # No session cookie, no bearer -> route's own auth runs (401 no_account), NOT the gate's generic 401
    r = prod_client.post("/api/scraper/stage-job", json={})
    assert r.status_code in (401, 422)  # 422 if body invalid, 401 from route auth — never the gate
    # the gate's body is {"detail":"Not authenticated"}; ensure we did NOT get gated before validation
    if r.status_code == 401:
        assert r.json().get("detail") != "Not authenticated"


def test_ext_me_not_gated(prod_client):
    r = prod_client.get("/api/ext/me")
    assert r.json().get("detail") != "Not authenticated"


def test_other_api_still_gated(prod_client):
    r = prod_client.get("/api/jobs")
    assert r.status_code == 401
    assert r.json()["detail"] == "Not authenticated"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/web/test_ext_middleware_exempt.py -v`
Expected: FAIL on `test_stage_job_not_gated_by_cookie` (gate returns generic 401)

- [ ] **Step 3: Implement**

In `web/auth/middleware.py`:

```python
_EXEMPT_PATHS = (
    "/api/payments/webhook",
    "/api/scraper/stage-job",
    "/api/ext/me",
)
```

> `/auth/ext/login` and `/auth/ext/revoke` are under `/auth/` which is already not in `_GATED_PREFIXES`, so they pass without listing.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/web/test_ext_middleware_exempt.py -v`
Expected: PASS
Run: `python -m pytest tests/web/test_auth_middleware.py -v`
Expected: PASS (no regression)

- [ ] **Step 5: Commit**

```bash
git add web/auth/middleware.py tests/web/test_ext_middleware_exempt.py
git commit -m "[feat] Exempt bearer-authed extension paths from cookie gate"
```

---

## Task 6: `stage-job` bearer-or-session auth

**Files:**
- Modify: `web/routers/scraper.py:18` (import) and `:91` (dependency)
- Test: `tests/web/test_stage_job_bearer.py`

**Interfaces:**
- Consumes: `bearer_or_session_profile` (Task 2).
- Produces: `POST /api/scraper/stage-job` resolves tenant from a bearer token when present, else session/dev-stub.

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_stage_job_bearer.py
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import Base, Account, get_db
from web.main import app
from web.auth import ext_token

PAYLOAD = {"source": "indeed", "job_key": "indeed_x1", "title": "Eng",
           "company": "Acme", "url": "https://indeed.com/v/x1", "description": "Do."}


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    s.add(Account(id=2, email="u@x.com", profile_id=8, created_at="t"))
    s.commit()
    yield s
    s.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_stage_job_with_bearer_uses_token_profile(client, db_session):
    raw = ext_token.mint_token(db_session, account_id=2)
    captured = {}
    with patch("web.routers.scraper.Job") as MockJob, patch("web.routers.scraper._sse_send"), \
         patch("web.routers.scraper.run_pipeline"):
        job = MagicMock(); job.job_key = "indeed_x1"
        def _save(batch, db, profile_id):
            captured["profile_id"] = profile_id
            return [job]
        MockJob.save_batch_returning.side_effect = _save
        r = client.post("/api/scraper/stage-job", json=PAYLOAD, headers={"Authorization": f"Bearer {raw}"})
    assert r.status_code == 200
    assert captured["profile_id"] == 8


def test_stage_job_bad_bearer_rejected(client):
    r = client.post("/api/scraper/stage-job", json=PAYLOAD, headers={"Authorization": "Bearer bad"})
    assert r.status_code == 401
    assert r.json()["detail"]["error"] == "no_account"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/web/test_stage_job_bearer.py -v`
Expected: FAIL (`test_stage_job_bad_bearer_rejected` — current dep ignores the bearer)

- [ ] **Step 3: Implement**

In `web/routers/scraper.py`, change the import line 18:

```python
from web.tenancy import current_profile_id
from web.auth.ext_token import bearer_or_session_profile
```

Change the `stage_job` dependency (line ~91):

```python
@router.post("/stage-job")
def stage_job(
    body: StageJobRequest,
    db: Session = Depends(get_db),
    profile_id: int = Depends(bearer_or_session_profile),
) -> dict[str, str]:
```

> `/run` keeps `current_profile_id` (dormant, session-only).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/web/test_stage_job_bearer.py tests/web/test_scraper_api.py -v`
Expected: PASS (new tests + existing scraper tests; note `test_scraper_api.py` overrides `current_profile_id` and sends no bearer, so it falls through to the session path — still works)

- [ ] **Step 5: Commit**

```bash
git add web/routers/scraper.py tests/web/test_stage_job_bearer.py
git commit -m "[feat] stage-job accepts extension bearer token or session"
```

---

## Task 7: Config + docs (backend)

**Files:**
- Modify: `.env.example`
- Modify: `web/CONTEXT.md`

**Interfaces:** none (documentation only).

- [ ] **Step 1: Add env doc**

Append to `.env.example`:

```
# Comma-separated allowlist of browser-extension OAuth redirect URLs.
# Chrome: https://<extension-id>.chromiumapp.org/   Firefox: browser.identity.getRedirectURL() value
EXTENSION_REDIRECT_URLS=
```

- [ ] **Step 2: Document the API surface**

In `web/CONTEXT.md`, add to the API Surface table:

```
| `GET` | `/auth/ext/login/{provider}` | Start extension OAuth; `redirect_uri` must match `EXTENSION_REDIRECT_URLS` (400 otherwise); ext-mode flag stashed in session |
| `POST` | `/auth/ext/revoke` | Bearer-authed; revoke the presented extension token |
| `GET` | `/api/ext/me` | Bearer-authed; `{email}` of the token's account; 401 if invalid |
```

And add a "Key Design Notes" bullet:

```
- **Extension auth (sub-project A)** — the browser extension runs OAuth via
  `identity.launchWebAuthFlow` against `/auth/ext/login/{provider}`; the callback mints
  a long-lived revocable opaque token (`extension_token` table, sha256-hashed) for an
  EXISTING account only (`resolve_existing_account` — no provisioning, Option B) and
  302s it to the allowlisted `redirect_uri` in a `#token=` fragment. The token rides
  `Authorization: Bearer` on `/api/scraper/stage-job` (resolved by
  `bearer_or_session_profile`, falling back to the session/dev-stub locally).
  `/api/scraper/stage-job` and `/api/ext/me` are in the cookie-gate `_EXEMPT_PATHS`.
```

- [ ] **Step 3: Commit**

```bash
git add .env.example web/CONTEXT.md
git commit -m "[docs] Document extension auth env + endpoints"
```

---

## Task 8: Browser-API shim (extension)

**Files:**
- Create: `browser-extension/lib/browser_shim.js`

**Interfaces:**
- Produces a global `xb` (cross-browser) object with promise-based `xb.storage.local.get/set`, `xb.identity.launchWebAuthFlow`, `xb.identity.getRedirectURL`, `xb.runtime.sendMessage` / `onMessage`, available in popup, service worker, and content scripts.

> No JS test harness exists; verification is manual (loading the extension). Keep the shim tiny.

- [ ] **Step 1: Implement the shim**

```javascript
// browser-extension/lib/browser_shim.js
// Minimal cross-browser bridge. Firefox exposes promise-based `browser.*`;
// Chrome exposes callback-based `chrome.*`. We expose a promise API as `xb`.
(function (root) {
  const api = (typeof browser !== "undefined") ? browser : chrome;
  const isFirefox = (typeof browser !== "undefined");

  function promisify(fn, ctx) {
    return (...args) =>
      isFirefox
        ? fn.apply(ctx, args)
        : new Promise((resolve, reject) =>
            fn.call(ctx, ...args, (res) =>
              chrome.runtime.lastError ? reject(new Error(chrome.runtime.lastError.message)) : resolve(res)
            )
          );
  }

  root.xb = {
    storage: {
      local: {
        get: promisify(api.storage.local.get, api.storage.local),
        set: promisify(api.storage.local.set, api.storage.local),
        remove: promisify(api.storage.local.remove, api.storage.local),
      },
    },
    identity: {
      launchWebAuthFlow: promisify(api.identity.launchWebAuthFlow, api.identity),
      getRedirectURL: (...a) => api.identity.getRedirectURL(...a),
    },
    runtime: {
      sendMessage: promisify(api.runtime.sendMessage, api.runtime),
      onMessage: api.runtime.onMessage,
    },
  };
})(typeof self !== "undefined" ? self : window);
```

- [ ] **Step 2: Manual sanity check**

Load the extension unpacked (see Task 13 for steps) and in the service worker console run `typeof xb.identity.launchWebAuthFlow`.
Expected: `"function"` (once `browser_shim.js` is wired into manifest in Task 9).

- [ ] **Step 3: Commit**

```bash
git add browser-extension/lib/browser_shim.js
git commit -m "[feat] Add cross-browser WebExtensions shim"
```

---

## Task 9: Manifest — identity perm, pinned ids, host permissions

**Files:**
- Modify: `browser-extension/manifest.json`

**Interfaces:**
- Produces: `identity` permission; `browser_shim.js` loaded first in every context; `host_permissions` for the prod server; stable Firefox id (already present) + Chrome `key` placeholder note.

- [ ] **Step 1: Edit the manifest**

```json
{
  "manifest_version": 3,
  "name": "Job Scraper",
  "version": "1.1.0",
  "description": "Scrapes job listings from LinkedIn and Indeed into AutoApply.",
  "permissions": ["storage", "identity"],
  "host_permissions": [
    "https://*.linkedin.com/*",
    "https://*.indeed.com/*",
    "https://autoapply.matthewbarlow.me/*"
  ],
  "background": {
    "service_worker": "background/service_worker.js",
    "scripts": ["lib/browser_shim.js", "background/service_worker.js"]
  },
  "browser_specific_settings": {
    "gecko": { "id": "job-scraper@autoapply" }
  },
  "content_scripts": [
    {
      "matches": ["https://www.linkedin.com/jobs/*", "https://www.linkedin.com/my-items/*"],
      "js": ["lib/browser_shim.js", "content/injector.js", "content/linkedin.js"]
    },
    {
      "matches": ["https://www.indeed.com/jobs*", "https://myjobs.indeed.com/*"],
      "js": ["lib/browser_shim.js", "content/injector.js", "content/indeed.js"]
    }
  ],
  "icons": {
    "16": "icons/icon-16.png", "32": "icons/icon-32.png",
    "48": "icons/icon-48.png", "128": "icons/icon-128.png"
  },
  "action": {
    "default_popup": "popup/popup.html",
    "default_title": "Job Scraper",
    "default_icon": {
      "16": "icons/icon-16.png", "32": "icons/icon-32.png",
      "48": "icons/icon-48.png", "128": "icons/icon-128.png"
    }
  }
}
```

- [ ] **Step 2: Record the redirect URLs to allowlist**

After loading unpacked in each browser (Task 13), capture the redirect URL by running in each console:
`xb.identity.getRedirectURL()` (Chrome → `https://<id>.chromiumapp.org/`; Firefox → its value).
Set both, comma-separated, in `EXTENSION_REDIRECT_URLS` (local `.env` and Railway).

> The service worker `scripts` array (Firefox MV3) lists the shim first; Chrome ignores `scripts` and uses `service_worker`, so the worker must itself `importScripts("../lib/browser_shim.js")` — handled in Task 11.

- [ ] **Step 3: Commit**

```bash
git add browser-extension/manifest.json
git commit -m "[feat] Manifest: identity permission, prod host, shim wiring"
```

---

## Task 10: Popup sign-in / sign-out UI

**Files:**
- Modify: `browser-extension/popup/popup.html`
- Modify: `browser-extension/popup/popup.js`

**Interfaces:**
- Consumes: `xb` shim; backend `/auth/ext/login/{provider}`, `/api/ext/me`, `/auth/ext/revoke`.
- Produces: token persisted at `xb.storage.local` key `extToken`; signed-in email displayed; sign-out clears token + revokes.

- [ ] **Step 1: Replace popup.html body**

```html
<!-- browser-extension/popup/popup.html -->
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    body { font: 13px system-ui; width: 240px; padding: 12px; }
    button { display: block; width: 100%; margin: 6px 0; padding: 8px; cursor: pointer; }
    #email { font-weight: 600; }
    .hidden { display: none; }
  </style>
</head>
<body>
  <div id="signedOut">
    <p>Sign in to send jobs to AutoApply:</p>
    <button id="loginGoogle">Sign in with Google</button>
    <button id="loginGithub">Sign in with GitHub</button>
    <p id="err" style="color:#b00;"></p>
  </div>
  <div id="signedIn" class="hidden">
    <p>Signed in as <span id="email"></span></p>
    <button id="logout">Sign out</button>
  </div>
  <hr />
  <button id="clearDedup">Clear scrape history</button>
  <script src="../lib/browser_shim.js"></script>
  <script src="popup.js"></script>
</body>
</html>
```

- [ ] **Step 2: Implement popup.js**

```javascript
// browser-extension/popup/popup.js
const SERVER = "https://autoapply.matthewbarlow.me";
const TOKEN_KEY = "extToken";

async function getToken() {
  const { [TOKEN_KEY]: t } = await xb.storage.local.get(TOKEN_KEY);
  return t || "";
}

async function signIn(provider) {
  const redirectUri = xb.identity.getRedirectURL();
  const url = `${SERVER}/auth/ext/login/${provider}?redirect_uri=${encodeURIComponent(redirectUri)}`;
  let resultUrl;
  try {
    resultUrl = await xb.identity.launchWebAuthFlow({ url, interactive: true });
  } catch (e) {
    return showError("Sign-in cancelled or failed.");
  }
  const frag = new URL(resultUrl).hash.slice(1);
  const params = new URLSearchParams(frag);
  if (params.get("error") === "no_account") {
    return showError("No AutoApply account. Sign up at autoapply.matthewbarlow.me first.");
  }
  const token = params.get("token");
  if (!token) return showError("Sign-in failed, try again.");
  await xb.storage.local.set({ [TOKEN_KEY]: token });
  await render();
}

async function signOut() {
  const token = await getToken();
  if (token) {
    try {
      await fetch(`${SERVER}/auth/ext/revoke`, { method: "POST", headers: { Authorization: `Bearer ${token}` } });
    } catch (_) {}
  }
  await xb.storage.local.remove(TOKEN_KEY);
  await render();
}

function showError(msg) {
  document.getElementById("err").textContent = msg;
}

async function render() {
  const token = await getToken();
  const inEl = document.getElementById("signedIn");
  const outEl = document.getElementById("signedOut");
  showError("");
  if (!token) {
    inEl.classList.add("hidden");
    outEl.classList.remove("hidden");
    return;
  }
  try {
    const res = await fetch(`${SERVER}/api/ext/me`, { headers: { Authorization: `Bearer ${token}` } });
    if (!res.ok) throw new Error();
    const { email } = await res.json();
    document.getElementById("email").textContent = email;
    inEl.classList.remove("hidden");
    outEl.classList.add("hidden");
  } catch (_) {
    await xb.storage.local.remove(TOKEN_KEY);
    inEl.classList.add("hidden");
    outEl.classList.remove("hidden");
  }
}

document.getElementById("loginGoogle").addEventListener("click", () => signIn("google"));
document.getElementById("loginGithub").addEventListener("click", () => signIn("github"));
document.getElementById("logout").addEventListener("click", signOut);
document.getElementById("clearDedup").addEventListener("click", async () => {
  await xb.storage.local.remove("stagedJobKeys");
  showError("Scrape history cleared.");
});
render();
```

- [ ] **Step 3: Manual verification (deferred to Task 13 smoke test)**

- [ ] **Step 4: Commit**

```bash
git add browser-extension/popup/popup.html browser-extension/popup/popup.js
git commit -m "[feat] Popup: extension OAuth sign-in/out"
```

---

## Task 11: Service worker — bearer header + typed auth error

**Files:**
- Modify: `browser-extension/background/service_worker.js`

**Interfaces:**
- Consumes: token at `xb.storage.local` key `extToken`.
- Produces: `handleScrape` returns `{ok:false, error:"no_account"}` when token missing or server 401; success path unchanged. POSTs to the hardcoded prod server.

- [ ] **Step 1: Rewrite service_worker.js**

```javascript
// browser-extension/background/service_worker.js
importScripts("../lib/browser_shim.js");

const SERVER = "https://autoapply.matthewbarlow.me";
const DEDUP_KEY = "stagedJobKeys";
const TOKEN_KEY = "extToken";

xb.runtime.onMessage.addListener((message, sender, sendResponse) => {
  handleMessage(message, sender, sendResponse);
  return true;
});

async function handleMessage(message, sender, sendResponse) {
  if (message.type === "CHECK_DEDUP") {
    const { [DEDUP_KEY]: keys = [] } = await xb.storage.local.get(DEDUP_KEY);
    sendResponse({ isDuplicate: keys.includes(message.job_key) });
    return;
  }
  if (message.type === "SCRAPE_JOB") {
    try {
      sendResponse(await handleScrape(message.payload));
    } catch (err) {
      sendResponse({ ok: false, error: err.message });
    }
  }
}

async function handleScrape(payload) {
  const { [DEDUP_KEY]: keys = [] } = await xb.storage.local.get(DEDUP_KEY);
  const keySet = new Set(keys);
  if (keySet.has(payload.job_key)) return { ok: true, status: "duplicate" };

  const { [TOKEN_KEY]: token } = await xb.storage.local.get(TOKEN_KEY);
  if (!token) return { ok: false, error: "no_account" };

  const res = await fetch(`${SERVER}/api/scraper/stage-job`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(payload),
  });

  if (res.status === 401) return { ok: false, error: "no_account" };
  if (!res.ok) throw new Error(`HTTP ${res.status}`);

  const data = await res.json();
  keySet.add(payload.job_key);
  await xb.storage.local.set({ [DEDUP_KEY]: [...keySet] });
  return { ok: true, status: data.status };
}
```

- [ ] **Step 2: Manual verification (Task 13)**

- [ ] **Step 3: Commit**

```bash
git add browser-extension/background/service_worker.js
git commit -m "[feat] Service worker: bearer auth + no_account error to prod server"
```

---

## Task 12: Injector — "Sign in required" button state

**Files:**
- Modify: `browser-extension/content/injector.js`

**Interfaces:**
- Consumes: scrape result `{ok:false, error:"no_account"}` from the service worker.
- Produces: the injected button shows "✗ Sign in required" instead of a generic error when `error === "no_account"`.

> Implementer: locate where injector.js reads the service-worker response and sets the button label (the existing "✗ Server error" / "✓ Scraped" branch). Add the `no_account` branch there. Exact surrounding code must be read live; below is the required logic.

- [ ] **Step 1: Add the branch**

Find the response-handling block (where `result.ok` is checked) and add, before the generic error label:

```javascript
if (!result.ok && result.error === "no_account") {
  btn.textContent = "✗ Sign in required";
  btn.title = "Open the Job Scraper extension and sign in to AutoApply.";
  return;
}
```

- [ ] **Step 2: Manual verification (Task 13)** — signed-out scrape shows "✗ Sign in required".

- [ ] **Step 3: Commit**

```bash
git add browser-extension/content/injector.js
git commit -m "[feat] Injector: show 'Sign in required' on no_account"
```

---

## Task 13: Live smoke test + CONTEXT.md (LinkedIn + Indeed)

**Files:**
- Modify: `browser-extension/CONTEXT.md`
- Possibly modify: `browser-extension/content/indeed.js`, `browser-extension/content/linkedin.js` (selector repair if smoke test reveals breakage)

**Interfaces:** none (verification + docs; selector fixes as needed).

> This task requires a human-driven, logged-in browser session — it cannot be automated. The implementer hands the maintainer this checklist and acts on the reported results.

- [ ] **Step 1: Load unpacked in both browsers, capture redirect URLs**

- Chrome: `chrome://extensions` → Developer mode → Load unpacked → `browser-extension/`.
- Firefox: `about:debugging` → This Firefox → Load Temporary Add-on → `manifest.json`.
- In each background console run `xb.identity.getRedirectURL()`; set both values in `EXTENSION_REDIRECT_URLS` (local `.env`; restart server) and on Railway.

- [ ] **Step 2: Auth smoke (each browser)**

- Click extension icon → Sign in with Google → consent → popup shows your email.
- Repeat with a Google account that has **no** AutoApply account → popup shows "No AutoApply account…".
- Sign out → popup returns to signed-out state; confirm `extension_token.revoked=1` for that row (Railway DB or local).

- [ ] **Step 3: LinkedIn scrape smoke (signed in)**

On `https://www.linkedin.com/jobs/...` search and a `/jobs/view/` page, click Scrape. Confirm in the dashboard the job has correct **title, company, location, description**. Record any wrong field.

- [ ] **Step 4: Indeed scrape smoke (signed in)**

On `https://www.indeed.com/jobs?q=...` (search) and one `myjobs.indeed.com` saved job, click Scrape. Verify **title, company, location, url, description** land correctly. If a field is empty/wrong, inspect the card DOM and repair the selector in `indeed.js` (`getJobData`, `getDescription`, `detailReadySelector`).

- [ ] **Step 5: Signed-out scrape**

Sign out, click Scrape on any card → button shows "✗ Sign in required".

- [ ] **Step 6: Update CONTEXT.md**

Rewrite `browser-extension/CONTEXT.md` "How It Works", "Loading", and "Known Issues":
- Replace the localhost staging description with the OAuth + bearer-token + prod-server flow.
- Document the `extToken` storage key, the sign-in popup, and the `no_account` button state.
- Record the **verified-working** Indeed and LinkedIn selectors as of test date, plus any positional fragility found.
- Note the deferred sub-project B (store packaging) and the pinned-id → redirect-allowlist dependency.

- [ ] **Step 7: Commit**

```bash
git add browser-extension/CONTEXT.md browser-extension/content/indeed.js browser-extension/content/linkedin.js
git commit -m "[docs] Update extension CONTEXT for OAuth flow + verified selectors"
```

---

## Final verification

- [ ] **Run the full backend suite**

Run: `python -m pytest tests/ -q`
Expected: all pass (new ext tests + existing auth/scraper/middleware suites).

- [ ] **Confirm single Alembic head**

Run: `python -m alembic heads`
Expected: `aa06exttoken01 (head)`

- [ ] **Deploy gate (manual, requires user approval per guardrails)**

Set `EXTENSION_REDIRECT_URLS` on Railway, then redeploy. Do NOT deploy without explicit user approval.
