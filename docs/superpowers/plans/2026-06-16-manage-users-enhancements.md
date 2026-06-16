# Manage Users Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an admin badge, admin-credits fix, search, sortable/left-aligned columns, user ban/restore, and capped credit grants to the admin Manage Users table.

**Architecture:** A new `account.banned` flag enforced at login and in the request seam. New admin endpoints for access (ban/restore), grant budget, and capped grant — grant cap = system credits (OpenRouter balance × 1000) − allocated (sum of non-admin balances), fail-closed when the balance is unreadable. Frontend table gains client-side search/sort and grant/revoke modals.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, React + Tailwind.

**Conventions (read before editing):**
- Tests: `.venv/Scripts/python.exe -m pytest ...` (bare `python` lacks deps).
- Spec/plan dirs are gitignored — stage docs with `git add -f`.
- No JS test framework — verify frontend with `cd react-dashboard && npm run build`.
- Alembic head is currently `aa03invites01`.
- Admin test fixture (`tests/web/test_admin_users.py`) yields `(TestClient, db)` admin-authed; override `require_real_admin` with the seeded admin account (id 1). Reuse it.
- The in-memory `db` fixture pattern lives inline in `tests/web/test_identity.py` / `test_impersonation_seam.py`.

Spec: `docs/superpowers/specs/2026-06-16-manage-users-enhancements-design.md`

---

## File Structure

- `db/database.py` — `Account.banned` column.
- `alembic/versions/aa04bans01_add_account_banned.py` — migration.
- `web/auth/identity.py` — ban check on login.
- `web/tenancy.py` — ban check in the production seam.
- `web/routers/credits.py` — `openrouter_remaining()` helper; refactor `system_balance`.
- `web/routers/admin.py` — `access`, `grant-budget`, `users/{id}/grant`; `banned` in `list_users`.
- `react-dashboard/src/api.js` — `setUserAccess`, `getGrantBudget`, `grantCredits`.
- `react-dashboard/src/components/admin/ManageUsers.jsx` — full UI rebuild.

---

## Task 1: `Account.banned` column + migration

**Files:**
- Modify: `db/database.py` (the `Account` model, ~line 126-139)
- Create: `alembic/versions/aa04bans01_add_account_banned.py`
- Test: `tests/db/test_account_banned.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/db/test_account_banned.py
from db.database import Account


def test_account_has_banned_column():
    col = Account.__table__.c.banned
    assert col is not None
    assert col.nullable is False
```

- [ ] **Step 2: Run, verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/db/test_account_banned.py -v`
Expected: FAIL (AttributeError on `banned`).

- [ ] **Step 3: Add the column**

In `db/database.py`, in the `Account` class after `stripe_customer_id`:

```python
    banned = Column(Boolean, nullable=False, default=False)
```

(`Boolean` is already imported.)

- [ ] **Step 4: Create the migration**

```python
# alembic/versions/aa04bans01_add_account_banned.py
"""add account.banned

Revision ID: aa04bans01
Revises: aa03invites01
Create Date: 2026-06-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "aa04bans01"
down_revision: Union[str, Sequence[str], None] = "aa03invites01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("account",
                  sa.Column("banned", sa.Boolean(), nullable=False,
                            server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("account", "banned")
```

- [ ] **Step 5: Apply + verify**

Run: `.venv/Scripts/python.exe -c "from db.database import init_db; init_db()"`
Expected: no error.
Run: `.venv/Scripts/python.exe -m pytest tests/db/test_account_banned.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add db/database.py alembic/versions/aa04bans01_add_account_banned.py tests/db/test_account_banned.py
git commit -m "[feat] Add account.banned column"
```

---

## Task 2: Ban enforcement (login + seam)

**Files:**
- Modify: `web/auth/identity.py` (`_resolve_or_provision`, the `if ident is not None` branch)
- Modify: `web/tenancy.py` (`current_profile_id` production branch)
- Test: `tests/web/test_ban_enforcement.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_ban_enforcement.py
import pytest
from starlette.requests import Request

from db.database import Account, Identity
from web.tenancy import current_profile_id
from web.auth.identity import _resolve_or_provision, Claims, BetaAccessDenied


def _req(session):
    return Request({"type": "http", "headers": [], "session": session})


def _seed_acct(db, *, account_id, profile_id, banned, is_admin=False):
    db.add(Account(id=account_id, email=f"a{account_id}@x.com", is_admin=is_admin,
                   profile_id=profile_id, created_at="2026-01-01T00:00:00+00:00",
                   credit_balance=0, credit_rate=1.0, tier="standard", banned=banned))
    db.commit()


def test_seam_blocks_banned(db, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    _seed_acct(db, account_id=1, profile_id=1, banned=True)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as ei:
        current_profile_id(_req({"account_id": 1}), db)
    assert ei.value.status_code == 401


def test_seam_allows_unbanned(db, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    _seed_acct(db, account_id=1, profile_id=1, banned=False)
    assert current_profile_id(_req({"account_id": 1}), db) == 1


def test_login_blocks_banned_existing_identity(db):
    _seed_acct(db, account_id=1, profile_id=1, banned=True)
    db.add(Identity(account_id=1, provider="google", provider_subject="sub1",
                    created_at="2026-01-01T00:00:00+00:00"))
    db.commit()
    claims = Claims(provider="google", subject="sub1", email="a1@x.com",
                    email_verified=True)
    with pytest.raises(BetaAccessDenied):
        _resolve_or_provision(db, claims)
```

(Use the inline `db` fixture from `test_impersonation_seam.py`; replicate it here.)

- [ ] **Step 2: Run, verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/web/test_ban_enforcement.py -v`
Expected: FAIL (banned users currently allowed through).

- [ ] **Step 3: Implement login check**

In `web/auth/identity.py`, inside `_resolve_or_provision`, replace the
`if ident is not None:` block:

```python
    if ident is not None:
        acct = db.query(Account).filter_by(id=ident.account_id).first()
        if acct is not None and acct.banned:
            raise BetaAccessDenied(email)
        return acct
```

- [ ] **Step 4: Implement seam check**

In `web/tenancy.py` `current_profile_id`, in the production branch, right after
resolving `acct` (the `if acct is None: ... 401` guard), add:

```python
        if acct.banned:
            raise HTTPException(status_code=401, detail="account suspended")
```

Place it before the impersonation resolution so a banned admin (shouldn't happen)
is also blocked.

- [ ] **Step 5: Run tests, verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/web/test_ban_enforcement.py tests/web/test_impersonation_seam.py tests/web/test_identity.py -v`
Expected: PASS (no regressions).

- [ ] **Step 6: Commit**

```bash
git add web/auth/identity.py web/tenancy.py tests/web/test_ban_enforcement.py
git commit -m "[feat] Enforce account.banned at login and in the request seam"
```

---

## Task 3: Access (ban/restore) endpoint + `banned` in users list

**Files:**
- Modify: `web/routers/admin.py`
- Test: `tests/web/test_admin_access.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_admin_access.py
# Reuse the (TestClient, db) `client` fixture + _admin_ok helper from
# tests/web/test_admin_users.py (copy them in).
from db.database import Account, AllowedEmail
from fastapi.testclient import TestClient


def _seed_user(db, *, banned=False, is_admin=False, pid=3, email="u3@x.com"):
    db.add(Account(id=pid, email=email, is_admin=is_admin, profile_id=pid,
                   created_at="2026-01-01T00:00:00+00:00", credit_balance=0,
                   credit_rate=1.0, tier="standard", banned=banned))
    db.add(AllowedEmail(email=email, created_at="2026-01-01T00:00:00+00:00"))
    db.commit()


def test_ban_sets_flag_and_removes_allowlist(client):
    app, db = client
    _admin_ok(app, db)
    _seed_user(db)
    r = TestClient(app).post("/api/admin/users/3/access", json={"banned": True})
    assert r.status_code == 200 and r.json()["banned"] is True
    assert db.query(Account).filter_by(profile_id=3).first().banned is True
    assert db.query(AllowedEmail).filter_by(email="u3@x.com").first() is None


def test_restore_clears_flag(client):
    app, db = client
    _admin_ok(app, db)
    _seed_user(db, banned=True)
    r = TestClient(app).post("/api/admin/users/3/access", json={"banned": False})
    assert r.status_code == 200 and r.json()["banned"] is False
    assert db.query(Account).filter_by(profile_id=3).first().banned is False


def test_cannot_ban_admin(client):
    app, db = client
    _admin_ok(app, db)
    _seed_user(db, is_admin=True, pid=4, email="admin2@x.com")
    r = TestClient(app).post("/api/admin/users/4/access", json={"banned": True})
    assert r.status_code == 400


def test_access_unknown_404(client):
    app, db = client
    _admin_ok(app, db)
    r = TestClient(app).post("/api/admin/users/999/access", json={"banned": True})
    assert r.status_code == 404


def test_users_includes_banned(client):
    app, db = client
    _admin_ok(app, db)
    _seed_user(db, banned=True)
    rows = {r["email"]: r for r in TestClient(app).get("/api/admin/users").json()}
    assert rows["u3@x.com"]["banned"] is True
```

- [ ] **Step 2: Run, verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/web/test_admin_access.py -v`
Expected: FAIL (route 404 / `banned` missing in users).

- [ ] **Step 3: Implement in `web/routers/admin.py`**

Add the `banned` field to `list_users` — change its return dict to include
`"banned": a.banned`. Then add:

```python
class AccessRequest(BaseModel):
    banned: bool


@router.post("/users/{profile_id}/access")
def set_user_access(profile_id: int, body: AccessRequest,
                    db: Session = Depends(get_db),
                    admin: Account = Depends(require_real_admin)):
    target = db.query(Account).filter_by(profile_id=profile_id).first()
    if target is None:
        raise HTTPException(status_code=404, detail="profile not found")
    if target.is_admin:
        raise HTTPException(status_code=400, detail="cannot ban an admin")
    target.banned = body.banned
    if body.banned:
        row = db.query(AllowedEmail).filter_by(email=target.email.lower()).first()
        if row is not None:
            db.delete(row)
    db.commit()
    return {"profile_id": profile_id, "banned": target.banned}
```

- [ ] **Step 4: Run tests, verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/web/test_admin_access.py tests/web/test_admin_users.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/routers/admin.py tests/web/test_admin_access.py
git commit -m "[feat] Admin ban/restore endpoint; banned in users list"
```

---

## Task 4: `openrouter_remaining` helper + refactor `system_balance`

**Files:**
- Modify: `web/routers/credits.py`
- Test: `tests/web/test_openrouter_remaining.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_openrouter_remaining.py
from unittest.mock import MagicMock, patch

from web.routers import credits as credits_mod


def test_remaining_none_without_key(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    assert credits_mod.openrouter_remaining() is None


def test_remaining_computes_from_api(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "k")
    resp = MagicMock()
    resp.json.return_value = {"data": {"total_credits": 30.0, "total_usage": 12.0}}
    resp.raise_for_status.return_value = None
    with patch("web.routers.credits.httpx.get", return_value=resp):
        assert credits_mod.openrouter_remaining() == 18.0


def test_remaining_none_on_http_error(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "k")
    import httpx
    with patch("web.routers.credits.httpx.get", side_effect=httpx.HTTPError("x")):
        assert credits_mod.openrouter_remaining() is None
```

- [ ] **Step 2: Run, verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/web/test_openrouter_remaining.py -v`
Expected: FAIL (no `openrouter_remaining`).

- [ ] **Step 3: Implement the helper + refactor**

In `web/routers/credits.py`, add:

```python
def openrouter_remaining() -> float | None:
    """Remaining USD on the platform OpenRouter key, or None if unset/unreachable."""
    key = os.getenv("LLM_API_KEY", "")
    if not key:
        return None
    try:
        resp = httpx.get("https://openrouter.ai/api/v1/credits",
                         headers={"Authorization": f"Bearer {key}"}, timeout=10)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        return float(data.get("total_credits", 0)) - float(data.get("total_usage", 0))
    except httpx.HTTPError:
        logger.exception("openrouter_remaining: request failed")
        return None
```

Refactor `system_balance` to preserve its current HTTP contract using the helper:

```python
@router.get("/admin/system-balance")
def system_balance(admin: Account = Depends(require_admin)):
    """Remaining balance on the platform OpenRouter key (money in the system)."""
    if not os.getenv("LLM_API_KEY", ""):
        raise HTTPException(status_code=503, detail="no platform key")
    remaining = openrouter_remaining()
    if remaining is None:
        raise HTTPException(status_code=502, detail="failed to reach OpenRouter")
    return {"remaining": remaining}
```

Note: the response previously also returned `total`/`used`; the only consumer
(`getSystemBalance` → `d.remaining`) uses `remaining`, so returning just
`remaining` is safe. If you prefer to preserve `total`/`used`, that's optional and
not required.

- [ ] **Step 4: Run tests, verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/web/test_openrouter_remaining.py tests/web/test_credits_api.py -v`
Expected: PASS (if `test_credits_api.py` asserts `total`/`used`, update those
assertions to `remaining` or restore those keys in the response).

- [ ] **Step 5: Commit**

```bash
git add web/routers/credits.py tests/web/test_openrouter_remaining.py
git commit -m "[refactor] Extract openrouter_remaining helper; reuse in system-balance"
```

---

## Task 5: `grant-budget` endpoint

**Files:**
- Modify: `web/routers/admin.py`
- Test: `tests/web/test_grant_budget.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_grant_budget.py
# Reuse the `client` fixture + _admin_ok helper from test_admin_users.py.
from db.database import Account
from fastapi.testclient import TestClient


def _seed_users(db):
    # non-admin balances: 1000 + 500 = 1500 allocated; admin balance ignored.
    db.add(Account(id=3, email="u3@x.com", is_admin=False, profile_id=3,
                   created_at="t", credit_balance=1000, credit_rate=1.0,
                   tier="standard", banned=False))
    db.add(Account(id=4, email="u4@x.com", is_admin=False, profile_id=4,
                   created_at="t", credit_balance=500, credit_rate=1.0,
                   tier="standard", banned=False))
    db.commit()


def test_budget_available(client, monkeypatch):
    app, db = client
    _admin_ok(app, db)
    _seed_users(db)
    # system_credits = 20.0 * 1000 = 20000; allocated = 1500; available = 18500
    monkeypatch.setattr("web.routers.admin.openrouter_remaining", lambda: 20.0)
    r = TestClient(app).get("/api/admin/grant-budget")
    assert r.status_code == 200
    b = r.json()
    assert b["system_credits"] == 20000
    assert b["allocated"] == 1500
    assert b["available"] == 18500


def test_budget_unavailable(client, monkeypatch):
    app, db = client
    _admin_ok(app, db)
    _seed_users(db)
    monkeypatch.setattr("web.routers.admin.openrouter_remaining", lambda: None)
    r = TestClient(app).get("/api/admin/grant-budget")
    b = r.json()
    assert b["system_credits"] is None
    assert b["available"] is None
    assert b["allocated"] == 1500
```

Note: admin.py must import the function by name
(`from web.routers.credits import openrouter_remaining`) and call the module-level
name so it can be patched. IMPORTANT: in the tests use
`monkeypatch.setattr("web.routers.admin.openrouter_remaining", lambda: <value>)`
rather than assigning the attribute directly — `monkeypatch` auto-restores it after
each test, preventing the stub from leaking into other test files. Replace the
`_set_remaining`/direct-assignment shown below accordingly (pass `monkeypatch` into
each test).

- [ ] **Step 2: Run, verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/web/test_grant_budget.py -v`
Expected: FAIL (route 404).

- [ ] **Step 3: Implement in `web/routers/admin.py`**

Add imports: `from sqlalchemy import func` and
`from web.routers.credits import openrouter_remaining`. Add:

```python
CREDITS_PER_DOLLAR = 1000


def _grant_budget(db: Session) -> dict:
    remaining = openrouter_remaining()
    allocated = int(db.query(func.coalesce(func.sum(Account.credit_balance), 0))
                    .filter(Account.is_admin.is_(False)).scalar() or 0)
    if remaining is None:
        return {"system_credits": None, "allocated": allocated, "available": None}
    system_credits = round(remaining * CREDITS_PER_DOLLAR)
    return {"system_credits": system_credits, "allocated": allocated,
            "available": max(system_credits - allocated, 0)}


@router.get("/grant-budget")
def grant_budget(db: Session = Depends(get_db),
                 admin: Account = Depends(require_real_admin)):
    return _grant_budget(db)
```

- [ ] **Step 4: Run tests, verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/web/test_grant_budget.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/routers/admin.py tests/web/test_grant_budget.py
git commit -m "[feat] Admin grant-budget endpoint (system minus allocated credits)"
```

---

## Task 6: Capped grant endpoint

**Files:**
- Modify: `web/routers/admin.py`
- Test: `tests/web/test_admin_grant_capped.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_admin_grant_capped.py
# Reuse the `client` fixture + _admin_ok helper from test_admin_users.py.
from db.database import Account
from fastapi.testclient import TestClient


def _seed_target(db, *, is_admin=False, balance=0, pid=3):
    db.add(Account(id=pid, email=f"u{pid}@x.com", is_admin=is_admin, profile_id=pid,
                   created_at="t", credit_balance=balance, credit_rate=1.0,
                   tier="standard", banned=False))
    db.commit()


def _set_remaining(monkeypatch, value):
    monkeypatch.setattr("web.routers.admin.openrouter_remaining", lambda: value)


def test_grant_success_within_cap(client, monkeypatch):
    app, db = client
    _admin_ok(app, db)
    _seed_target(db, balance=100)
    _set_remaining(monkeypatch, 20.0)  # 20000 system, allocated 100, available 19900
    r = TestClient(app).post("/api/admin/users/3/grant", json={"amount": 500})
    assert r.status_code == 200
    assert r.json()["granted"] == 500
    assert db.query(Account).filter_by(profile_id=3).first().credit_balance == 600


def test_grant_exceeds_cap_400(client, monkeypatch):
    app, db = client
    _admin_ok(app, db)
    _seed_target(db, balance=0)
    _set_remaining(monkeypatch, 0.5)  # 500 system, allocated 0, available 500
    r = TestClient(app).post("/api/admin/users/3/grant", json={"amount": 501})
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "exceeds_grant_budget"


def test_grant_unavailable_balance_409(client, monkeypatch):
    app, db = client
    _admin_ok(app, db)
    _seed_target(db)
    _set_remaining(monkeypatch, None)
    r = TestClient(app).post("/api/admin/users/3/grant", json={"amount": 10})
    assert r.status_code == 409


def test_grant_admin_target_400(client, monkeypatch):
    app, db = client
    _admin_ok(app, db)
    _seed_target(db, is_admin=True, pid=4)
    _set_remaining(monkeypatch, 20.0)
    r = TestClient(app).post("/api/admin/users/4/grant", json={"amount": 10})
    assert r.status_code == 400


def test_grant_nonpositive_400(client, monkeypatch):
    app, db = client
    _admin_ok(app, db)
    _seed_target(db)
    _set_remaining(monkeypatch, 20.0)
    r = TestClient(app).post("/api/admin/users/3/grant", json={"amount": 0})
    assert r.status_code == 400
```

Note: `HTTPException(detail={...})` surfaces as `r.json()["detail"]` being that
dict — hence `r.json()["detail"]["error"]`.

- [ ] **Step 2: Run, verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/web/test_admin_grant_capped.py -v`
Expected: FAIL (route 404).

- [ ] **Step 3: Implement in `web/routers/admin.py`**

Add `from core.credits import grant_credits`. Add:

```python
class GrantRequest(BaseModel):
    amount: int


@router.post("/users/{profile_id}/grant")
def grant_to_user(profile_id: int, body: GrantRequest,
                  db: Session = Depends(get_db),
                  admin: Account = Depends(require_real_admin)):
    target = db.query(Account).filter_by(profile_id=profile_id).first()
    if target is None:
        raise HTTPException(status_code=404, detail="profile not found")
    if target.is_admin:
        raise HTTPException(status_code=400, detail="cannot grant to an admin")
    if body.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")
    budget = _grant_budget(db)
    if budget["available"] is None:
        raise HTTPException(status_code=409,
                            detail={"error": "system_balance_unavailable"})
    if body.amount > budget["available"]:
        raise HTTPException(status_code=400,
                            detail={"error": "exceeds_grant_budget",
                                    "available": budget["available"]})
    grant_credits(db, profile_id, body.amount, reason="admin_grant",
                  created_by=admin.id)
    bal = db.query(Account).filter_by(profile_id=profile_id).first().credit_balance
    return {"granted": body.amount, "balance": bal}
```

- [ ] **Step 4: Run tests, verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/web/test_admin_grant_capped.py -v`
Expected: PASS (5)

- [ ] **Step 5: Commit**

```bash
git add web/routers/admin.py tests/web/test_admin_grant_capped.py
git commit -m "[feat] Capped admin grant endpoint (funded from system budget)"
```

---

## Task 7: API client functions

**Files:**
- Modify: `react-dashboard/src/api.js` (near the other admin fns, ~line 290-310)

- [ ] **Step 1: Add the functions**

After `stopImpersonation`:

```javascript
export const setUserAccess = (profileId, banned) =>
  _fetch(`/api/admin/users/${profileId}/access`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ banned }),
  })

export const getGrantBudget = () => _fetch('/api/admin/grant-budget')

export const grantCredits = (profileId, amount) =>
  _fetch(`/api/admin/users/${profileId}/grant`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ amount }),
  })
```

- [ ] **Step 2: Verify build**

Run: `cd react-dashboard && npm run build`
Expected: succeeds.

- [ ] **Step 3: Commit**

```bash
git add react-dashboard/src/api.js
git commit -m "[feat] Add user access / grant-budget / grant API client functions"
```

---

## Task 8: ManageUsers UI rebuild (badge, search, sort, left-align, grant + revoke)

**Files:**
- Modify (full rewrite): `react-dashboard/src/components/admin/ManageUsers.jsx`

This replaces the whole component. Invite section + purchases modal + view-as are
preserved; the Users table gains a search box, sortable left-aligned columns, an
admin badge, `—` for admin credits, a clickable credits cell (grant modal), and a
revoke ✕ / restore control with a confirm modal.

- [ ] **Step 1: Replace the file contents**

```javascript
import { useState, useEffect, useCallback } from 'react'
import {
  inviteUser, getInvites, getUsers, getUserPurchases, startImpersonation,
  setUserAccess, getGrantBudget, grantCredits,
} from '../../api'

const SORTS = [
  { key: 'email', label: 'Email' },
  { key: 'tier', label: 'Tier' },
  { key: 'credits', label: 'Credits' },
]

// Admins display '—' for credits; sort them to the bottom of a credits sort.
const creditSortVal = (u) => (u.is_admin ? -1 : (u.credits ?? 0))

export default function ManageUsers() {
  const [email, setEmail] = useState('')
  const [status, setStatus] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [invites, setInvites] = useState([])

  const [users, setUsers] = useState([])
  const [search, setSearch] = useState('')
  const [sortKey, setSortKey] = useState('email')
  const [sortDir, setSortDir] = useState('asc')

  const [purchasesFor, setPurchasesFor] = useState(null)
  const [purchases, setPurchases] = useState(null)

  const [budget, setBudget] = useState(null)
  const [grantFor, setGrantFor] = useState(null)   // user | null
  const [grantAmount, setGrantAmount] = useState(100)
  const [grantError, setGrantError] = useState(null)
  const [granting, setGranting] = useState(false)

  const [revokeFor, setRevokeFor] = useState(null) // user | null

  const refreshUsers = useCallback(() => { getUsers().then(setUsers).catch(() => {}) }, [])
  const refreshBudget = useCallback(() => { getGrantBudget().then(setBudget).catch(() => setBudget(null)) }, [])
  const refreshInvites = useCallback(() => { getInvites().then(setInvites).catch(() => {}) }, [])

  useEffect(() => { refreshUsers() }, [refreshUsers])
  useEffect(() => { refreshBudget() }, [refreshBudget])
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

  const toggleSort = (key) => {
    if (key === sortKey) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else { setSortKey(key); setSortDir('asc') }
  }

  const openGrant = (u) => {
    setGrantFor(u)
    setGrantError(null)
    const avail = budget?.available
    setGrantAmount(avail != null ? Math.min(100, avail) : 100)
  }

  const submitGrant = async () => {
    if (!grantFor) return
    setGranting(true)
    setGrantError(null)
    try {
      await grantCredits(grantFor.profile_id, Number(grantAmount))
      setGrantFor(null)
      refreshUsers()
      refreshBudget()
    } catch {
      setGrantError('Grant failed (over budget or balance unavailable).')
    } finally {
      setGranting(false)
    }
  }

  const confirmRevoke = async () => {
    if (!revokeFor) return
    try {
      await setUserAccess(revokeFor.profile_id, true)
      setRevokeFor(null)
      refreshUsers()
    } catch {
      setStatus({ kind: 'err', text: 'Could not revoke access.' })
    }
  }

  const restore = async (u) => {
    try { await setUserAccess(u.profile_id, false); refreshUsers() }
    catch { setStatus({ kind: 'err', text: 'Could not restore access.' }) }
  }

  const shown = users
    .filter((u) => u.email.toLowerCase().includes(search.trim().toLowerCase()))
    .sort((a, b) => {
      let av, bv
      if (sortKey === 'credits') { av = creditSortVal(a); bv = creditSortVal(b) }
      else { av = (a[sortKey] ?? '').toString().toLowerCase(); bv = (b[sortKey] ?? '').toString().toLowerCase() }
      if (av < bv) return sortDir === 'asc' ? -1 : 1
      if (av > bv) return sortDir === 'asc' ? 1 : -1
      return 0
    })

  const arrow = (key) => (key === sortKey ? (sortDir === 'asc' ? ' ▲' : ' ▼') : '')

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

      <section>
        <h2 className="text-lg font-semibold mb-3">Users</h2>
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by email…"
          className="w-full mb-3 px-3 py-2 rounded-lg bg-white/5 border border-space-border text-sm focus:outline-none focus:border-purple-500"
        />
        <div className="border border-space-border rounded-lg overflow-hidden">
          <div className="grid grid-cols-[2fr_1fr_1fr_auto] gap-2 px-3 py-2 text-xs uppercase tracking-widest text-space-dim bg-white/5">
            {SORTS.map((s) => (
              <button
                key={s.key}
                onClick={() => toggleSort(s.key)}
                className="text-left hover:text-space-text transition-colors"
              >
                {s.label}{arrow(s.key)}
              </button>
            ))}
            <span className="text-left">Actions</span>
          </div>
          <div className="max-h-60 overflow-y-auto">
            {shown.map((u) => (
              <div
                key={u.profile_id}
                className={`grid grid-cols-[2fr_1fr_1fr_auto] gap-2 px-3 py-2 text-sm items-center border-t border-space-border/50 ${u.banned ? 'opacity-60' : ''}`}
              >
                <span className="truncate flex items-center gap-2" title={u.email}>
                  {u.email}
                  {u.is_admin && (
                    <span className="text-[10px] font-bold text-black bg-amber-400 rounded px-1 py-0.5">ADMIN</span>
                  )}
                  {u.banned && (
                    <span className="text-[10px] font-bold text-white bg-red-600 rounded px-1 py-0.5">BANNED</span>
                  )}
                </span>
                <span className="text-space-dim text-left">{u.tier}</span>
                {u.is_admin ? (
                  <span className="font-mono text-space-dim text-left">—</span>
                ) : (
                  <button
                    type="button"
                    title="Grant credits"
                    onClick={() => openGrant(u)}
                    className="font-mono text-purple-400 hover:text-purple-300 text-left"
                  >
                    {(u.credits ?? 0).toLocaleString()}
                  </button>
                )}
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
                  {!u.is_admin && (u.banned ? (
                    <button
                      type="button"
                      title="Restore access"
                      onClick={() => restore(u)}
                      className="text-space-dim hover:text-green-400 transition-colors"
                    >↺</button>
                  ) : (
                    <button
                      type="button"
                      title="Revoke access"
                      onClick={() => setRevokeFor(u)}
                      className="text-red-500 hover:text-red-400 transition-colors font-bold"
                    >✕</button>
                  ))}
                </span>
              </div>
            ))}
            {shown.length === 0 && <p className="px-3 py-3 text-xs text-space-dim">No users.</p>}
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

      {grantFor && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/70" onClick={() => setGrantFor(null)}>
          <div className="bg-[#12121f] border border-space-border rounded-xl p-5 w-full max-w-sm mx-4" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-sm font-semibold mb-1">Grant credits</h3>
            <p className="text-xs text-space-dim mb-3">{grantFor.email}</p>
            {budget?.available == null ? (
              <p className="text-xs text-red-400 mb-3">System balance unavailable — grants are disabled.</p>
            ) : (
              <p className="text-xs text-space-dim mb-3">Up to {budget.available.toLocaleString()} credits available (free to the user, funded from the system balance).</p>
            )}
            <input
              type="number"
              min="1"
              max={budget?.available ?? undefined}
              value={grantAmount}
              onChange={(e) => setGrantAmount(e.target.value)}
              disabled={budget?.available == null}
              className="w-full mb-3 px-3 py-2 rounded-lg bg-white/5 border border-space-border text-sm focus:outline-none focus:border-purple-500 disabled:opacity-50"
            />
            {grantError && <p className="text-xs text-red-400 mb-2">{grantError}</p>}
            <div className="flex justify-end gap-2">
              <button onClick={() => setGrantFor(null)} className="px-3 py-1.5 text-sm text-space-dim hover:text-space-text">Cancel</button>
              <button
                onClick={submitGrant}
                disabled={granting || budget?.available == null || Number(grantAmount) <= 0}
                className="px-3 py-1.5 rounded-lg bg-purple-600 text-white text-sm font-semibold hover:bg-purple-500 disabled:opacity-50"
              >
                {granting ? 'Granting…' : 'Grant'}
              </button>
            </div>
          </div>
        </div>
      )}

      {revokeFor && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/70" onClick={() => setRevokeFor(null)}>
          <div className="bg-[#12121f] border border-space-border rounded-xl p-5 w-full max-w-sm mx-4" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-sm font-semibold mb-1">Revoke access</h3>
            <p className="text-xs text-space-dim mb-4">
              Ban <span className="text-space-text">{revokeFor.email}</span> and remove them from the allowlist? They'll be signed out and need a fresh invite to return.
            </p>
            <div className="flex justify-end gap-2">
              <button onClick={() => setRevokeFor(null)} className="px-3 py-1.5 text-sm text-space-dim hover:text-space-text">Cancel</button>
              <button onClick={confirmRevoke} className="px-3 py-1.5 rounded-lg bg-red-600 text-white text-sm font-semibold hover:bg-red-500">Revoke</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Verify build**

Run: `cd react-dashboard && npm run build`
Expected: succeeds.

- [ ] **Step 3: Commit**

```bash
git add react-dashboard/src/components/admin/ManageUsers.jsx
git commit -m "[feat] Manage Users: badge, search, sort, grant + revoke, admin-credits fix"
```

---

## Task 9: Full verification + docs

- [ ] **Step 1: Full backend suite**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 2: Frontend build**

Run: `cd react-dashboard && npm run build`
Expected: succeeds.

- [ ] **Step 3: Manual smoke (note results)**

As admin: admin rows show an `ADMIN` badge and `—` credits (no grant click);
search filters by email; clicking Email/Tier/Credits headers sorts with ▲/▼;
columns are left-aligned; clicking a non-admin's credits opens the grant modal
(amount defaults to min(100, available); over-budget rejected; disabled when system
balance unavailable); the red ✕ opens the revoke modal, banning dims the row and
shows a `BANNED` tag, and ↺ restores. Confirm a banned user is blocked from the API.

- [ ] **Step 4: Update CONTEXT docs**

- `web/CONTEXT.md`: `account.banned` (enforced at login + seam); admin endpoints
  `POST /users/{id}/access`, `GET /grant-budget`, `POST /users/{id}/grant`
  (cap = system credits − non-admin allocated, fail-closed); `banned` in
  `/users`; `openrouter_remaining` helper in `credits.py`.
- `react-dashboard/CONTEXT.md`: ManageUsers gains search/sort/admin badge/admin
  `—` credits/grant modal/revoke modal.
- `db/CONTEXT.md`: `account.banned` column.

- [ ] **Step 5: Commit**

```bash
git add web/CONTEXT.md react-dashboard/CONTEXT.md db/CONTEXT.md
git commit -m "[docs] Document ban/grant Manage Users enhancements"
```

---

## Self-Review Notes (addressed)

- **Ban actually locks out existing users:** enforced both at login (identity.py)
  and per-request (tenancy.py seam), not just by removing the allowlist row.
- **Grant cap can't be bypassed:** recomputed server-side in `users/{id}/grant`;
  client `budget` is display-only.
- **Fail-closed:** grant 409s when the system balance is unreadable (local dev
  without `LLM_API_KEY`).
- **Admins protected:** can't be banned (400) or granted (400); ✕ hidden on admin
  rows in the UI.
- **`openrouter_remaining` import style:** admin.py imports the name so tests can
  monkeypatch `web.routers.admin.openrouter_remaining`.
