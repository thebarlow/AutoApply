# Admin Page — User Management & Impersonation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the admin page into a Docs-style console with a scrollable users table (email/tier/credits), per-user purchase-history modal, and read-only "view as" impersonation driven through the existing tenancy seam.

**Architecture:** Impersonation overrides `current_profile_id` from a session flag, honored only for a re-verified admin, so every tenant-scoped read re-points transparently. A read-only ASGI guard blocks unsafe methods while impersonating. Admin endpoints authorize against the *real* admin via `require_real_admin` (ignoring impersonation). Frontend mirrors `Docs.jsx` layout.

**Tech Stack:** FastAPI, Starlette middleware/sessions, SQLAlchemy, React + react-router, Tailwind.

Spec: `docs/superpowers/specs/2026-06-16-admin-page-users-impersonation-design.md`

**Conventions (read before editing):**
- Run backend tests with the venv: `.venv/Scripts/python.exe -m pytest ...` (the bare `python` in Git Bash is the global interpreter and is missing deps like `itsdangerous`).
- Spec/plan dirs are gitignored — stage docs with `git add -f`.
- ISO timestamps: `datetime.now(timezone.utc).isoformat()`.
- No JS test framework — verify frontend via `cd react-dashboard && npm run build`.
- Existing admin test fixture (`tests/web/test_admin_invite.py`) yields a `(TestClient, db)` already admin-authed by overriding `current_profile_id` → 1, with two seeded accounts (id 1 admin/profile 1; id 2 non-admin/profile 2). Reuse it.

---

## File Structure

- `web/tenancy.py` — impersonation-aware `current_profile_id` + `_impersonated_profile_id` helper.
- `web/routers/admin.py` — `require_real_admin`, `users`, `users/{pid}/purchases`, `impersonate/start`, `impersonate/stop`.
- `web/middleware_impersonation.py` (new) — read-only guard (pure ASGI) + testable `is_blocked()` helper.
- `web/main.py` — register the guard middleware.
- `web/auth/routes.py` — `/api/me` gains `impersonating`.
- `react-dashboard/src/api.js` — `getUsers`, `getUserPurchases`, `startImpersonation`, `stopImpersonation`.
- `react-dashboard/src/components/Navbar.jsx` — gold Admin pill.
- `react-dashboard/src/components/AdminPage.jsx` — Docs-style layout + left function nav.
- `react-dashboard/src/components/admin/ManageUsers.jsx` (new) — invite form + users table + purchases modal.
- `react-dashboard/src/App.jsx` — impersonation banner.

---

## Task 1: Impersonation-aware tenancy seam

**Files:**
- Modify: `web/tenancy.py`
- Test: `tests/web/test_impersonation_seam.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_impersonation_seam.py
import os

from starlette.requests import Request

from db.database import Account, Base, engine
from web.tenancy import current_profile_id


def _req(session: dict) -> Request:
    return Request({"type": "http", "headers": [], "session": session})


def _seed(db_session, *, account_id, profile_id, is_admin):
    db_session.add(Account(
        id=account_id, email=f"a{account_id}@x.com", is_admin=is_admin,
        profile_id=profile_id, created_at="2026-01-01T00:00:00+00:00",
        credit_balance=0, credit_rate=0.0, tier="standard"))
    db_session.commit()


def test_admin_impersonation_returns_target(db_session, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    _seed(db_session, account_id=1, profile_id=1, is_admin=True)
    _seed(db_session, account_id=2, profile_id=7, is_admin=False)
    req = _req({"account_id": 1, "impersonate_profile_id": 7})
    assert current_profile_id(req, db_session) == 7


def test_non_admin_flag_ignored(db_session, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    _seed(db_session, account_id=2, profile_id=5, is_admin=False)
    req = _req({"account_id": 2, "impersonate_profile_id": 7})
    assert current_profile_id(req, db_session) == 5


def test_no_flag_returns_own(db_session, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    _seed(db_session, account_id=1, profile_id=1, is_admin=True)
    req = _req({"account_id": 1})
    assert current_profile_id(req, db_session) == 1
```

Note: reuse the in-memory `db_session` fixture pattern from `tests/web/test_identity.py` (inline fixture named `db` there — check the exact name and adapt the parameter accordingly; if it's `db`, rename the params here from `db_session` to `db`). The fixture must create all tables and yield a Session.

- [ ] **Step 2: Run test, verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/web/test_impersonation_seam.py -v`
Expected: FAIL (impersonation not implemented — returns own pid for the admin case).

- [ ] **Step 3: Implement the seam**

In `web/tenancy.py`, add the helper and use it in `current_profile_id`:

```python
def _impersonated_profile_id(request: Request, db: Session, account: Account) -> int | None:
    """The impersonation target, honored only when the real account is an admin.

    Admin status is re-verified here every request, so a stale session flag left
    by a since-demoted account is ignored.
    """
    if not account.is_admin:
        return None
    target = request.session.get("impersonate_profile_id")
    return int(target) if target else None
```

Replace the production branch of `current_profile_id` so it resolves the account
once and consults impersonation:

```python
    if os.getenv("APP_ENV") == "production":
        account_id = request.session.get("account_id")
        if not account_id:
            raise HTTPException(status_code=401, detail="Not authenticated")
        acct = db.query(Account).filter_by(id=account_id).first()
        if acct is None:
            raise HTTPException(status_code=401, detail="Not authenticated")
        impersonated = _impersonated_profile_id(request, db, acct)
        return impersonated if impersonated is not None else acct.profile_id
    return get_dev_tenant_id(db)
```

(`Request`, `Session`, `Account`, `HTTPException` are already imported in tenancy.py.)

- [ ] **Step 4: Run test, verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/web/test_impersonation_seam.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add web/tenancy.py tests/web/test_impersonation_seam.py
git commit -m "[feat] Impersonation-aware tenancy seam (admin-gated)"
```

---

## Task 2: require_real_admin + users + purchases endpoints

**Files:**
- Modify: `web/routers/admin.py`
- Test: `tests/web/test_admin_users.py`

- [ ] **Step 1: Write the failing test**

Open `tests/web/test_admin_invite.py` first and copy its fixture (the `(TestClient, db)`
fixture with two seeded accounts and the `current_profile_id` override). Reuse the
SAME fixture name and seeding helper here.

```python
# tests/web/test_admin_users.py
# Reuse the client fixture from test_admin_invite.py (copy it / its conftest pattern).
from db.database import Account, Purchase


def _seed_extra_user(db):
    db.add(Account(id=3, email="user3@x.com", is_admin=False, profile_id=3,
                   created_at="2026-01-01T00:00:00+00:00", credit_balance=4200,
                   credit_rate=1.0, tier="standard"))
    db.add(Purchase(profile_id=3, stripe_session_id="cs_3", price_id="price_x",
                    credits=1000, amount_usd=10.0, status="completed",
                    created_at="2026-02-01T00:00:00+00:00"))
    db.commit()


def test_users_requires_admin(client):
    app, _db = client
    from web.tenancy import current_profile_id
    app.dependency_overrides[current_profile_id] = lambda: 2  # non-admin
    from fastapi.testclient import TestClient
    r = TestClient(app).get("/api/admin/users")
    assert r.status_code == 403


def test_users_lists_accounts(client):
    app, db = client  # admin-authed (profile 1)
    _seed_extra_user(db)
    from fastapi.testclient import TestClient
    r = TestClient(app).get("/api/admin/users")
    assert r.status_code == 200
    rows = {row["email"]: row for row in r.json()}
    assert rows["user3@x.com"]["tier"] == "standard"
    assert rows["user3@x.com"]["credits"] == 4200
    assert rows["user3@x.com"]["profile_id"] == 3
    assert rows["user3@x.com"]["is_admin"] is False


def test_user_purchases(client):
    app, db = client
    _seed_extra_user(db)
    from fastapi.testclient import TestClient
    r = TestClient(app).get("/api/admin/users/3/purchases")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["stripe_session_id"] == "cs_3"
    assert body[0]["credits"] == 1000
```

IMPORTANT: the admin endpoints in this task use `require_real_admin`, which reads
`request.session["account_id"]` — NOT `current_profile_id`. The existing fixture
authorizes admin by overriding `current_profile_id`, which will NOT satisfy
`require_real_admin`. So in this test, ALSO override `require_real_admin` to return
the seeded admin account. Add, in each admin-authed test:

```python
    from web.routers.admin import require_real_admin
    admin = db.query(Account).filter_by(id=1).first()
    app.dependency_overrides[require_real_admin] = lambda: admin
```

and for the 403 test, override `require_real_admin` to raise:

```python
    from fastapi import HTTPException
    from web.routers.admin import require_real_admin
    def _deny():
        raise HTTPException(status_code=403, detail="admin only")
    app.dependency_overrides[require_real_admin] = _deny
```

(Adapt the exact fixture unpacking to match `test_admin_invite.py`.)

- [ ] **Step 2: Run test, verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/web/test_admin_users.py -v`
Expected: FAIL (routes 404 / `require_real_admin` import error).

- [ ] **Step 3: Implement in `web/routers/admin.py`**

Add imports at top (merge with existing): `from fastapi import Request` and
`from db.database import Purchase` and `from web.tenancy import current_profile_id`
is NOT needed. Add:

```python
def require_real_admin(request: Request, db: Session = Depends(get_db)) -> Account:
    """Resolve the REAL logged-in account from the session and require admin.

    Unlike require_admin (which depends on current_profile_id and would resolve
    the *impersonated* tenant), this always authorizes the actual admin, so admin
    endpoints keep working — and stay admin-gated — while impersonating.
    Outside production there is no session login; fall back to current_profile_id's
    account so local/dev and tests behave.
    """
    account_id = request.session.get("account_id")
    if account_id:
        acct = db.query(Account).filter_by(id=account_id).first()
    else:
        acct = None
    if acct is None:
        # dev/local: no session login — resolve the dev tenant's account.
        from web.tenancy import get_dev_tenant_id
        acct = db.query(Account).filter_by(profile_id=get_dev_tenant_id(db)).first()
    if acct is None or not acct.is_admin:
        raise HTTPException(status_code=403, detail="admin only")
    return acct


@router.get("/users")
def list_users(db: Session = Depends(get_db),
               admin: Account = Depends(require_real_admin)):
    rows = db.query(Account).order_by(Account.profile_id.asc()).all()
    return [{"profile_id": a.profile_id, "email": a.email, "tier": a.tier,
             "credits": a.credit_balance or 0, "is_admin": a.is_admin}
            for a in rows]


@router.get("/users/{profile_id}/purchases")
def user_purchases(profile_id: int, db: Session = Depends(get_db),
                   admin: Account = Depends(require_real_admin)):
    rows = (db.query(Purchase).filter_by(profile_id=profile_id)
            .order_by(Purchase.id.desc()).limit(50).all())
    return [{"stripe_session_id": r.stripe_session_id, "credits": r.credits,
             "amount_usd": r.amount_usd, "status": r.status,
             "created_at": r.created_at} for r in rows]
```

- [ ] **Step 4: Run test, verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/web/test_admin_users.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add web/routers/admin.py tests/web/test_admin_users.py
git commit -m "[feat] Admin users list + per-user purchases endpoints"
```

---

## Task 3: Impersonation start/stop endpoints

**Files:**
- Modify: `web/routers/admin.py`
- Test: `tests/web/test_admin_impersonate.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_admin_impersonate.py
# Reuse the client fixture + require_real_admin override pattern from
# tests/web/test_admin_users.py.
from db.database import Account


def _admin_override(app, db):
    from web.routers.admin import require_real_admin
    admin = db.query(Account).filter_by(id=1).first()
    app.dependency_overrides[require_real_admin] = lambda: admin


def _seed_target(db):
    db.add(Account(id=3, email="t@x.com", is_admin=False, profile_id=9,
                   created_at="2026-01-01T00:00:00+00:00", credit_balance=0,
                   credit_rate=1.0, tier="standard"))
    db.commit()


def test_start_unknown_profile_404(client):
    app, db = client
    _admin_override(app, db)
    from fastapi.testclient import TestClient
    r = TestClient(app).post("/api/admin/impersonate/start", json={"profile_id": 999})
    assert r.status_code == 404


def test_start_and_stop_sets_session(client):
    app, db = client
    _admin_override(app, db)
    _seed_target(db)
    from fastapi.testclient import TestClient
    c = TestClient(app)
    r = c.post("/api/admin/impersonate/start", json={"profile_id": 9})
    assert r.status_code == 200 and r.json()["ok"] is True
    # The session cookie now carries the flag; stop clears it.
    r2 = c.post("/api/admin/impersonate/stop")
    assert r2.status_code == 200 and r2.json()["ok"] is True
```

- [ ] **Step 2: Run test, verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/web/test_admin_impersonate.py -v`
Expected: FAIL (routes 404).

- [ ] **Step 3: Implement in `web/routers/admin.py`**

```python
class ImpersonateRequest(BaseModel):
    profile_id: int


@router.post("/impersonate/start")
def impersonate_start(body: ImpersonateRequest, request: Request,
                      db: Session = Depends(get_db),
                      admin: Account = Depends(require_real_admin)):
    target = db.query(Account).filter_by(profile_id=body.profile_id).first()
    if target is None:
        raise HTTPException(status_code=404, detail="profile not found")
    request.session["impersonate_profile_id"] = body.profile_id
    return {"ok": True}


@router.post("/impersonate/stop")
def impersonate_stop(request: Request,
                     admin: Account = Depends(require_real_admin)):
    request.session.pop("impersonate_profile_id", None)
    return {"ok": True}
```

(`BaseModel` and `Request` are imported already after Task 2.)

- [ ] **Step 4: Run test, verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/web/test_admin_impersonate.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add web/routers/admin.py tests/web/test_admin_impersonate.py
git commit -m "[feat] Impersonation start/stop endpoints"
```

---

## Task 4: Read-only guard middleware

**Files:**
- Create: `web/middleware_impersonation.py`
- Modify: `web/main.py`
- Test: `tests/web/test_impersonation_guard.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_impersonation_guard.py
from web.middleware_impersonation import is_blocked


def test_get_never_blocked():
    assert is_blocked("GET", "/api/jobs", {"impersonate_profile_id": 9}) is False


def test_post_blocked_while_impersonating():
    assert is_blocked("POST", "/api/jobs/x/generate", {"impersonate_profile_id": 9}) is True


def test_post_allowed_without_flag():
    assert is_blocked("POST", "/api/jobs/x/generate", {}) is False


def test_stop_allowlisted():
    assert is_blocked("POST", "/api/admin/impersonate/stop", {"impersonate_profile_id": 9}) is False


def test_logout_allowlisted():
    assert is_blocked("POST", "/auth/logout", {"impersonate_profile_id": 9}) is False
```

- [ ] **Step 2: Run test, verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/web/test_impersonation_guard.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement `web/middleware_impersonation.py`**

```python
"""Read-only guard for impersonation sessions (pure ASGI).

While an admin is impersonating a user (session carries impersonate_profile_id),
all unsafe HTTP methods are rejected so the admin can only VIEW the user's data,
never mutate it or spend their credits. A small allowlist lets the admin exit
impersonation and log out.

Pure ASGI (not BaseHTTPMiddleware) so the /api/events SSE stream is not buffered.
Requires SessionMiddleware to be registered OUTSIDE this one so scope["session"]
is populated before dispatch.
"""
from __future__ import annotations

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_ALLOWLIST = {"/api/admin/impersonate/stop", "/auth/logout"}


def is_blocked(method: str, path: str, session: dict) -> bool:
    """True if this request must be rejected because an impersonation is active."""
    if not session.get("impersonate_profile_id"):
        return False
    if method.upper() not in _UNSAFE_METHODS:
        return False
    return path not in _ALLOWLIST


class ImpersonationReadOnlyMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        session = scope.get("session") or {}
        if is_blocked(scope.get("method", "GET"), scope.get("path", ""), session):
            await JSONResponse(
                {"error": "impersonation_read_only"}, status_code=403,
            )(scope, receive, send)
            return
        await self.app(scope, receive, send)
```

- [ ] **Step 4: Run test, verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/web/test_impersonation_guard.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Register the middleware in `web/main.py`**

Add the import near the other middleware import (after line 34
`from web.auth.middleware import AuthGateMiddleware`):

```python
from web.middleware_impersonation import ImpersonationReadOnlyMiddleware
```

Register it so the session is available to it — add it BETWEEN the AuthGate and
Session registrations (Starlette runs most-recently-added outermost, so Session
must remain last/outermost; the guard added after AuthGate sits inside Session and
reads the populated session). Change the middleware block to:

```python
app.add_middleware(AuthGateMiddleware)
app.add_middleware(ImpersonationReadOnlyMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=_session_secret(),
    https_only=os.getenv("APP_ENV") == "production",
    same_site="lax",
)
```

- [ ] **Step 6: Verify app imports and the guard is wired**

Run: `.venv/Scripts/python.exe -c "from web.main import app; print('ok')"`
Expected: prints `ok` (no import/registration error).

- [ ] **Step 7: Commit**

```bash
git add web/middleware_impersonation.py web/main.py tests/web/test_impersonation_guard.py
git commit -m "[feat] Read-only guard middleware for impersonation sessions"
```

---

## Task 5: /api/me reports impersonation

**Files:**
- Modify: `web/auth/routes.py` (the `api_me` function, ~line 104-118)
- Test: `tests/web/test_me_impersonation.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_me_impersonation.py
# Build a TestClient over web.main.app is heavy; instead test api_me directly by
# constructing a Request with a session and a db, mirroring tests/web/test_auth_routes.py
# style. Reuse the in-memory db fixture (name `db`) from test_identity.py.
from starlette.requests import Request

from db.database import Account
from web.auth.routes import api_me


def _req(session):
    return Request({"type": "http", "headers": [], "session": session})


def _seed(db, **kw):
    db.add(Account(created_at="2026-01-01T00:00:00+00:00", credit_balance=0,
                   credit_rate=0.0, tier="standard", **kw))
    db.commit()


def test_me_impersonating_null_normally(db):
    _seed(db, id=1, email="admin@x.com", is_admin=True, profile_id=1)
    out = api_me(_req({"account_id": 1}), db)
    assert out["impersonating"] is None
    assert out["is_admin"] is True


def test_me_reports_impersonation_target(db):
    _seed(db, id=1, email="admin@x.com", is_admin=True, profile_id=1)
    _seed(db, id=2, email="victim@x.com", is_admin=False, profile_id=9)
    out = api_me(_req({"account_id": 1, "impersonate_profile_id": 9}), db)
    assert out["impersonating"] == {"profile_id": 9, "email": "victim@x.com"}


def test_me_non_admin_impersonation_ignored(db):
    _seed(db, id=2, email="user@x.com", is_admin=False, profile_id=5)
    out = api_me(_req({"account_id": 2, "impersonate_profile_id": 9}), db)
    assert out["impersonating"] is None
```

Note: confirm `api_me`'s signature is `api_me(request, db)`; the existing code
raises `HTTPException(401)` when no `account_id`. Match the fixture name (`db`).

- [ ] **Step 2: Run test, verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/web/test_me_impersonation.py -v`
Expected: FAIL (KeyError `impersonating` / return dict lacks the field).

- [ ] **Step 3: Implement — extend `api_me` in `web/auth/routes.py`**

Replace the return block of `api_me` with one that adds `impersonating`:

```python
    user = db.query(User).filter_by(id=acct.profile_id).first()
    impersonating = None
    if acct.is_admin:
        target_pid = request.session.get("impersonate_profile_id")
        if target_pid:
            target = db.query(Account).filter_by(profile_id=int(target_pid)).first()
            if target is not None:
                impersonating = {"profile_id": target.profile_id, "email": target.email}
    return {
        "email": acct.email,
        "is_admin": acct.is_admin,
        "profile_name": user.name if user else "",
        "impersonating": impersonating,
    }
```

- [ ] **Step 4: Run test, verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/web/test_me_impersonation.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add web/auth/routes.py tests/web/test_me_impersonation.py
git commit -m "[feat] /api/me reports active impersonation target"
```

---

## Task 6: API client functions

**Files:**
- Modify: `react-dashboard/src/api.js` (near `inviteUser`/`getInvites`, ~line 288)

- [ ] **Step 1: Add the functions**

After `getInvites`:

```javascript
export const getUsers = () => _fetch('/api/admin/users')

export const getUserPurchases = (profileId) =>
  _fetch(`/api/admin/users/${profileId}/purchases`)

export const startImpersonation = (profileId) =>
  _fetch('/api/admin/impersonate/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ profile_id: profileId }),
  })

export const stopImpersonation = () =>
  _fetch('/api/admin/impersonate/stop', { method: 'POST' })
```

- [ ] **Step 2: Verify build**

Run: `cd react-dashboard && npm run build`
Expected: succeeds.

- [ ] **Step 3: Commit**

```bash
git add react-dashboard/src/api.js
git commit -m "[feat] Add admin users/impersonation API client functions"
```

---

## Task 7: Gold Admin tab

**Files:**
- Modify: `react-dashboard/src/components/Navbar.jsx`

- [ ] **Step 1: Restyle the admin link**

Replace the existing admin `<Link>` block (rendered when `me?.is_admin`) with a
gold pill:

```javascript
        {me?.is_admin && (
          <Link
            to="/admin"
            className="text-sm font-semibold text-black bg-amber-400 hover:bg-amber-300 rounded-md px-2.5 py-1 transition-colors"
          >
            Admin
          </Link>
        )}
```

- [ ] **Step 2: Verify build**

Run: `cd react-dashboard && npm run build`
Expected: succeeds.

- [ ] **Step 3: Commit**

```bash
git add react-dashboard/src/components/Navbar.jsx
git commit -m "[feat] Gold background for the Admin navbar tab"
```

---

## Task 8: Admin page Docs-style layout + ManageUsers extraction

**Files:**
- Modify: `react-dashboard/src/components/AdminPage.jsx`
- Create: `react-dashboard/src/components/admin/ManageUsers.jsx`

This task MOVES the existing invite UI into `ManageUsers.jsx` and rebuilds
`AdminPage.jsx` as a Docs-style shell. The users table is added in Task 9 — here
`ManageUsers` contains only the migrated invite form so each task stays focused.

- [ ] **Step 1: Create `react-dashboard/src/components/admin/ManageUsers.jsx`**

Move the invite form + status + invited-list logic out of the current
`AdminPage.jsx` into this component (behavior unchanged). It owns its own state and
calls `inviteUser`/`getInvites`.

```javascript
import { useState, useEffect, useCallback } from 'react'
import { inviteUser, getInvites } from '../../api'

export default function ManageUsers() {
  const [email, setEmail] = useState('')
  const [status, setStatus] = useState(null) // { kind: 'ok'|'err', text }
  const [submitting, setSubmitting] = useState(false)
  const [invites, setInvites] = useState([])

  const refreshInvites = useCallback(() => {
    getInvites().then(setInvites).catch(() => {})
  }, [])

  useEffect(() => { refreshInvites() }, [refreshInvites])

  const submit = async (e) => {
    e.preventDefault()
    if (!email.trim()) return
    setSubmitting(true)
    setStatus(null)
    try {
      const r = await inviteUser(email.trim())
      const text = r.already_invited
        ? 'Already invited.'
        : r.emailed
        ? 'Invited — email sent.'
        : 'Added to allowlist (email not configured).'
      setStatus({ kind: 'ok', text })
      setEmail('')
      refreshInvites()
    } catch {
      setStatus({ kind: 'err', text: 'Failed to send invite.' })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <section>
        <h2 className="text-lg font-semibold mb-3">Invite a user</h2>
        <form onSubmit={submit} className="flex gap-2">
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="person@example.com"
            className="flex-1 px-3 py-2 rounded-lg bg-white/5 border border-space-border text-sm focus:outline-none focus:border-purple-500"
          />
          <button
            type="submit"
            disabled={submitting}
            className="px-4 py-2 rounded-lg bg-purple-600 text-white text-sm font-semibold hover:bg-purple-500 disabled:opacity-50"
          >
            {submitting ? 'Sending…' : 'Send Invite'}
          </button>
        </form>
        {status && (
          <p className={`text-sm mt-2 ${status.kind === 'ok' ? 'text-green-400' : 'text-red-400'}`}>
            {status.text}
          </p>
        )}
        {invites.length > 0 && (
          <ul className="flex flex-col gap-1 mt-4">
            <li className="text-xs uppercase tracking-widest text-space-dim mb-1">Invited</li>
            {invites.map((inv) => (
              <li key={inv.email} className="flex justify-between text-sm border-b border-space-border/50 py-1">
                <span>{inv.email}</span>
                <span className="text-space-dim text-xs">{new Date(inv.created_at).toLocaleDateString()}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
```

- [ ] **Step 2: Rebuild `react-dashboard/src/components/AdminPage.jsx` as a Docs-style shell**

```javascript
import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import Navbar from './Navbar'
import { getMe } from '../api'
import ManageUsers from './admin/ManageUsers'

const FUNCTIONS = [
  { key: 'users', label: 'Manage Users' },
]

export default function AdminPage() {
  const [allowed, setAllowed] = useState(undefined) // undefined=loading
  const [active, setActive] = useState('users')

  useEffect(() => {
    getMe().then((me) => setAllowed(!!me?.is_admin)).catch(() => setAllowed(false))
  }, [])

  if (allowed === undefined) return null
  if (!allowed) {
    return (
      <div className="min-h-screen flex items-center justify-center text-space-dim">
        <p>Not authorized. <Link to="/" className="text-purple-400 hover:underline">Go home</Link></p>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[#0f0f1a] text-space-text">
      <Navbar />
      <div className="max-w-5xl mx-auto p-6">
        <div className="flex gap-8 h-[calc(100vh-4rem)]">
          <nav className="w-56 shrink-0 sticky top-6 self-start">
            <p className="text-xs uppercase tracking-widest text-space-dim mb-3">Admin</p>
            <ul className="space-y-2">
              {FUNCTIONS.map((f) => (
                <li key={f.key}>
                  <button
                    onClick={() => setActive(f.key)}
                    className={`w-full text-left text-base font-semibold transition-colors ${
                      active === f.key ? 'text-space-text' : 'text-space-dim hover:text-space-text'
                    }`}
                  >
                    {f.label}
                  </button>
                </li>
              ))}
            </ul>
          </nav>

          <section className="flex-1 min-w-0 overflow-y-auto">
            {active === 'users' && <ManageUsers />}
          </section>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Verify build**

Run: `cd react-dashboard && npm run build`
Expected: succeeds (no unused imports — `inviteUser`/`getInvites` now live only in ManageUsers).

- [ ] **Step 4: Commit**

```bash
git add react-dashboard/src/components/AdminPage.jsx react-dashboard/src/components/admin/ManageUsers.jsx
git commit -m "[refactor] Docs-style admin page shell with ManageUsers function"
```

---

## Task 9: Users table + purchases modal + view-as

**Files:**
- Modify: `react-dashboard/src/components/admin/ManageUsers.jsx`

- [ ] **Step 1: Add users table, purchases modal, and view-as to `ManageUsers.jsx`**

Extend the component. Add imports: `getUsers, getUserPurchases, startImpersonation`
from `../../api`. Add state for `users`, `purchasesFor` (the profile_id whose modal
is open), and `purchases`. Fetch users on mount. Render the table below the invite
section, and a modal when `purchasesFor` is set.

Add to the imports line:
```javascript
import { inviteUser, getInvites, getUsers, getUserPurchases, startImpersonation } from '../../api'
```

Add state + effects inside the component (after the invites state):
```javascript
  const [users, setUsers] = useState([])
  const [purchasesFor, setPurchasesFor] = useState(null) // profile_id | null
  const [purchases, setPurchases] = useState(null)        // null=loading

  useEffect(() => { getUsers().then(setUsers).catch(() => {}) }, [])

  const openPurchases = (profileId) => {
    setPurchasesFor(profileId)
    setPurchases(null)
    getUserPurchases(profileId).then(setPurchases).catch(() => setPurchases([]))
  }

  const viewAs = async (profileId) => {
    try {
      await startImpersonation(profileId)
      window.location.href = '/'
    } catch {
      setStatus({ kind: 'err', text: 'Could not start impersonation.' })
    }
  }
```

Add this JSX after the invite `</section>` (still inside the outer flex `div`):
```javascript
      <section>
        <h2 className="text-lg font-semibold mb-3">Users</h2>
        <div className="border border-space-border rounded-lg overflow-hidden">
          <div className="grid grid-cols-[2fr_1fr_1fr_auto] gap-2 px-3 py-2 text-xs uppercase tracking-widest text-space-dim bg-white/5">
            <span>Email</span><span>Tier</span><span>Credits</span><span>Actions</span>
          </div>
          <div className="max-h-60 overflow-y-auto">
            {users.map((u) => (
              <div key={u.profile_id} className="grid grid-cols-[2fr_1fr_1fr_auto] gap-2 px-3 py-2 text-sm items-center border-t border-space-border/50">
                <span className="truncate" title={u.email}>{u.email}</span>
                <span className="text-space-dim">{u.tier}</span>
                <span className="font-mono text-purple-400">{(u.credits ?? 0).toLocaleString()}</span>
                <span className="flex items-center gap-2">
                  <button
                    type="button"
                    title="View app as this user"
                    onClick={() => viewAs(u.profile_id)}
                    className="text-space-dim hover:text-amber-400 transition-colors"
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" />
                    </svg>
                  </button>
                  <button
                    type="button"
                    title="View purchase history"
                    onClick={() => openPurchases(u.profile_id)}
                    className="text-space-dim hover:text-purple-400 transition-colors text-xs underline"
                  >
                    Purchases
                  </button>
                </span>
              </div>
            ))}
            {users.length === 0 && <p className="px-3 py-3 text-xs text-space-dim">No users.</p>}
          </div>
        </div>
      </section>

      {purchasesFor !== null && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/70" onClick={() => setPurchasesFor(null)}>
          <div className="bg-[#12121f] border border-space-border rounded-xl p-5 w-full max-w-md mx-4" onClick={(e) => e.stopPropagation()}>
            <div className="flex justify-between items-center mb-3">
              <h3 className="text-sm font-semibold">Purchase history</h3>
              <button onClick={() => setPurchasesFor(null)} className="text-space-dim hover:text-space-text" aria-label="Close">×</button>
            </div>
            {purchases === null ? (
              <p className="text-xs text-space-dim">Loading…</p>
            ) : purchases.length === 0 ? (
              <p className="text-xs text-space-dim">No purchases.</p>
            ) : (
              <ul className="flex flex-col gap-1">
                {purchases.map((p) => (
                  <li key={p.stripe_session_id} className="flex justify-between text-xs border-b border-space-border/50 py-1">
                    <span>{new Date(p.created_at).toLocaleDateString()}</span>
                    <span>{p.credits.toLocaleString()} cr</span>
                    <span className="text-space-dim">${p.amount_usd.toFixed(2)} · {p.status}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
```

- [ ] **Step 2: Verify build**

Run: `cd react-dashboard && npm run build`
Expected: succeeds.

- [ ] **Step 3: Commit**

```bash
git add react-dashboard/src/components/admin/ManageUsers.jsx
git commit -m "[feat] Admin users table with view-as and purchase-history modal"
```

---

## Task 10: Impersonation banner in App

**Files:**
- Modify: `react-dashboard/src/App.jsx`

- [ ] **Step 1: Add the banner**

`App.jsx` already has `me` (from `getMe()`). Add an import for `stopImpersonation`
from `./api`. Render a persistent gold banner at the very top of the main app route
(inside the `path="*"` element, just before `<Navbar />`) when `me?.impersonating`:

```javascript
          {me?.impersonating && (
            <div className="sticky top-0 z-[120] flex items-center justify-center gap-3 bg-amber-400 text-black text-sm font-semibold px-4 py-2">
              <span>Viewing as {me.impersonating.email}</span>
              <button
                onClick={() => { stopImpersonation().finally(() => { window.location.href = '/' }) }}
                className="underline hover:no-underline"
              >
                Exit
              </button>
            </div>
          )}
```

Add to the existing import from `./api` (currently
`import { getJobs, getActivePromptStatus, getLlmStatus, markJobSeen, getMe } from './api'`):
append `, stopImpersonation`.

- [ ] **Step 2: Verify build**

Run: `cd react-dashboard && npm run build`
Expected: succeeds.

- [ ] **Step 3: Commit**

```bash
git add react-dashboard/src/App.jsx
git commit -m "[feat] Impersonation banner with exit control"
```

---

## Task 11: Full verification + docs

- [ ] **Step 1: Full backend suite**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 2: Frontend build**

Run: `cd react-dashboard && npm run build`
Expected: succeeds.

- [ ] **Step 3: Manual smoke (note results)**

As an admin (production-like session): Admin tab is gold; `/admin` shows left nav
("Manage Users") + invite form + users table (≤5 rows, scrolls) with Email/Tier/
Credits; eyeball enters a read-only view (gold "Viewing as …" banner, Exit
restores); Purchases button opens a modal of that user's purchases. Confirm a POST
action (e.g. generate) is rejected while impersonating.

- [ ] **Step 4: Update CONTEXT docs**

- `web/CONTEXT.md`: note impersonation seam in `tenancy.py`; new admin endpoints
  (`users`, `users/{pid}/purchases`, `impersonate/start|stop`) and
  `require_real_admin`; the `ImpersonationReadOnlyMiddleware` (read-only guard,
  allowlist) and its registration order; `/api/me` `impersonating` field.
- `react-dashboard/CONTEXT.md`: `AdminPage.jsx` is now a Docs-style shell;
  `components/admin/ManageUsers.jsx` (invite + users table + purchases modal +
  view-as); App-level impersonation banner; gold Admin tab.

- [ ] **Step 5: Commit**

```bash
git add web/CONTEXT.md react-dashboard/CONTEXT.md
git commit -m "[docs] Document admin user management and impersonation"
```

---

## Self-Review Notes (addressed)

- **Auth-during-impersonation trap:** admin endpoints use `require_real_admin`
  (session-based), not `require_admin` (which would resolve the impersonated
  tenant). Covered in Tasks 2-3.
- **Middleware order:** guard registered inside `SessionMiddleware` so
  `scope["session"]` is populated. Covered in Task 4 Step 5.
- **Read-only completeness:** guard blocks all unsafe methods app-wide with a
  minimal exit allowlist, rather than annotating each write route.
- **Dev fallback:** `require_real_admin` resolves the dev-tenant account when no
  session login exists, so the admin page/table work in local dev.
