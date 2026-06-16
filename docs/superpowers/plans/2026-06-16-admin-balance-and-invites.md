# Admin System-Balance Display & Invite Flow — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Admins see the platform system balance (toggleable $/credits) where users see personal credits, plus an admin-only navbar tab with an email-invite flow that allowlists new users.

**Architecture:** Display-only on the credit side (admins already have `credit_rate=0`, no ledger change). The allowlist moves from env-only to env-OR-DB so invites persist at runtime. A new admin router handles invite + list behind `require_admin`; a stdlib `smtplib` module sends Zoho SMTP mail, no-op when unconfigured.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, `smtplib` (stdlib), React + react-router, Tailwind.

Spec: `docs/superpowers/specs/2026-06-16-admin-balance-and-invites-design.md`

---

## File Structure

- `db/database.py` — add `AllowedEmail` model.
- `alembic/versions/aa03invites01_add_allowed_email.py` — new migration (head = `aa02tiers01`).
- `web/auth/identity.py` — `is_allowed_email(db, email)` checks env OR table; update caller.
- `core/email.py` — new: `send_invite(to_email)` via Zoho SMTP, no-op when unconfigured.
- `web/routers/admin.py` — new: `POST /api/admin/invite`, `GET /api/admin/invites`.
- `web/main.py` — mount admin router.
- `react-dashboard/src/api.js` — `inviteUser`, `getInvites`.
- `react-dashboard/src/components/widgets/CreditBalance.jsx` — admin balance + $/credits toggle.
- `react-dashboard/src/components/widgets/UserHome.jsx` — pass `isAdmin`, drop `SystemBalancePanel`.
- `react-dashboard/src/components/Navbar.jsx` — admin link.
- `react-dashboard/src/App.jsx` — pass `me` to Navbar, add `/admin` route.
- `react-dashboard/src/components/AdminPage.jsx` — new invite page.

**Convention notes (read before editing):**
- Spec/plan dirs are gitignored — stage docs with `git add -f`.
- ISO timestamps use the existing helper pattern: `datetime.now(timezone.utc).isoformat()`.
- Run backend tests with `python -m pytest` from the project root (Windows; the Bash tool runs Git Bash but `python` resolves to the venv).
- There is **no JS test framework**; verify frontend via `npm run build` (from `react-dashboard/`) and manual notes.

---

## Task 1: `AllowedEmail` model + migration

**Files:**
- Modify: `db/database.py` (after the `Identity` class, ~line 155)
- Create: `alembic/versions/aa03invites01_add_allowed_email.py`
- Test: `tests/db/test_allowed_email_model.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/db/test_allowed_email_model.py
from db.database import AllowedEmail


def test_allowed_email_columns():
    cols = {c.name for c in AllowedEmail.__table__.columns}
    assert cols == {"id", "email", "invited_by", "created_at"}
    assert AllowedEmail.__table__.c.email.unique is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/db/test_allowed_email_model.py -v`
Expected: FAIL with `ImportError: cannot import name 'AllowedEmail'`

- [ ] **Step 3: Add the model**

In `db/database.py`, after the `Identity` class:

```python
class AllowedEmail(Base):
    """Runtime allowlist entry (an admin invite). Supplements the ALLOWED_EMAILS
    env var, which remains the bootstrap allowlist."""

    __tablename__ = "allowed_email"

    id = Column(Integer, primary_key=True)
    email = Column(String, nullable=False, unique=True)
    invited_by = Column(Integer, ForeignKey("account.id"), nullable=True)
    created_at = Column(String, nullable=False)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/db/test_allowed_email_model.py -v`
Expected: PASS

- [ ] **Step 5: Create the Alembic migration**

```python
# alembic/versions/aa03invites01_add_allowed_email.py
"""add allowed_email table (runtime invite allowlist)

Revision ID: aa03invites01
Revises: aa02tiers01
Create Date: 2026-06-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "aa03invites01"
down_revision: Union[str, Sequence[str], None] = "aa02tiers01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "allowed_email",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(), nullable=False, unique=True),
        sa.Column("invited_by", sa.Integer(), sa.ForeignKey("account.id"), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("allowed_email")
```

- [ ] **Step 6: Apply migration to local SQLite and verify**

Run: `python -c "from db.database import init_db; init_db()"`
Expected: no error; exits cleanly (runs `alembic upgrade head`).

- [ ] **Step 7: Commit**

```bash
git add db/database.py alembic/versions/aa03invites01_add_allowed_email.py tests/db/test_allowed_email_model.py
git commit -m "[feat] Add allowed_email table for runtime invite allowlist"
```

---

## Task 2: `is_allowed_email` checks the DB

**Files:**
- Modify: `web/auth/identity.py:46-47` (`is_allowed_email`) and `:96` (its caller)
- Test: `tests/web/test_allowlist_db.py`

Note: `is_allowed_email` gains a `db: Session` parameter. Its only caller is
`_resolve_or_provision` (line 96), which already has `db`.

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_allowlist_db.py
import os

from db.database import AllowedEmail
from web.auth.identity import is_allowed_email


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def test_env_allowlist_still_works(db_session, monkeypatch):
    monkeypatch.setenv("ALLOWED_EMAILS", "envuser@example.com")
    assert is_allowed_email(db_session, "envuser@example.com") is True


def test_db_allowlist_row_matches(db_session, monkeypatch):
    monkeypatch.setenv("ALLOWED_EMAILS", "")
    db_session.add(AllowedEmail(email="invited@example.com", created_at=_now()))
    db_session.commit()
    assert is_allowed_email(db_session, "invited@example.com") is True


def test_unknown_email_rejected(db_session, monkeypatch):
    monkeypatch.setenv("ALLOWED_EMAILS", "")
    assert is_allowed_email(db_session, "stranger@example.com") is False
```

Note: reuse the existing `db_session` fixture. If `tests/web/` lacks one, copy
the pattern from `tests/web/test_identity.py` (check its top for the fixture name;
adjust the parameter name to match — do not invent a new fixture).

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/web/test_allowlist_db.py -v`
Expected: FAIL (TypeError: `is_allowed_email()` takes 1 positional arg, or assertion error for the DB-row case).

- [ ] **Step 3: Update `is_allowed_email`**

In `web/auth/identity.py`, replace:

```python
def is_allowed_email(email: str) -> bool:
    return email.lower() in _email_set("ALLOWED_EMAILS")
```

with:

```python
def is_allowed_email(db: Session, email: str) -> bool:
    e = email.lower()
    if e in _email_set("ALLOWED_EMAILS"):
        return True
    from db.database import AllowedEmail
    return db.query(AllowedEmail).filter_by(email=e).first() is not None
```

Then update the caller at line ~96:

```python
    admin = is_admin_email(email)
    if not admin and not is_allowed_email(db, email):
        raise BetaAccessDenied(email)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/web/test_allowlist_db.py -v`
Expected: PASS

- [ ] **Step 5: Run identity tests to confirm no regression**

Run: `python -m pytest tests/web/test_identity.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add web/auth/identity.py tests/web/test_allowlist_db.py
git commit -m "[feat] Allow login for DB-allowlisted (invited) emails"
```

---

## Task 3: `core/email.py` — Zoho SMTP send

**Files:**
- Create: `core/email.py`
- Test: `tests/core/test_email.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_email.py
from unittest.mock import MagicMock, patch

from core import email as email_mod


def test_send_invite_noop_when_unconfigured(monkeypatch):
    monkeypatch.delenv("ZOHO_SMTP_USER", raising=False)
    monkeypatch.delenv("ZOHO_SMTP_PASSWORD", raising=False)
    assert email_mod.send_invite("new@example.com") is False


def test_send_invite_sends_when_configured(monkeypatch):
    monkeypatch.setenv("ZOHO_SMTP_USER", "noreply@example.com")
    monkeypatch.setenv("ZOHO_SMTP_PASSWORD", "secret")
    smtp = MagicMock()
    ctx = MagicMock()
    ctx.__enter__.return_value = smtp
    with patch("core.email.smtplib.SMTP_SSL", return_value=ctx) as ctor:
        assert email_mod.send_invite("new@example.com") is True
    ctor.assert_called_once_with("smtp.zoho.com", 465)
    smtp.login.assert_called_once_with("noreply@example.com", "secret")
    smtp.send_message.assert_called_once()
    sent = smtp.send_message.call_args[0][0]
    assert sent["To"] == "new@example.com"
    assert sent["From"] == "noreply@example.com"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_email.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.email'`

- [ ] **Step 3: Implement `core/email.py`**

```python
"""Outbound email via Zoho SMTP. No-op (returns False) when SMTP env vars are
unset, so invite flows still work in local/dev without mail configured."""
from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)

SMTP_HOST = "smtp.zoho.com"
SMTP_PORT = 465


def _app_base_url() -> str:
    return os.getenv("APP_BASE_URL", "https://autoapply.matthewbarlow.me")


def send_invite(to_email: str) -> bool:
    """Send an invitation email. Returns True if sent, False if SMTP is unconfigured.

    Access is gated by the allowlist + OAuth login, so the message carries no
    token -- it just points the recipient at the app to sign in.
    """
    user = os.getenv("ZOHO_SMTP_USER")
    password = os.getenv("ZOHO_SMTP_PASSWORD")
    if not user or not password:
        logger.info("send_invite: SMTP not configured; skipping email to %s", to_email)
        return False

    url = _app_base_url()
    msg = EmailMessage()
    msg["Subject"] = "You're invited to Auto Apply"
    msg["From"] = user
    msg["To"] = to_email
    msg.set_content(
        "You've been invited to Auto Apply.\n\n"
        f"Sign in at {url} using this email address ({to_email}) "
        "with Google or GitHub to get started.\n"
    )

    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.login(user, password)
        smtp.send_message(msg)
    logger.info("send_invite: sent invite to %s", to_email)
    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/core/test_email.py -v`
Expected: PASS

- [ ] **Step 5: Document env vars in `.env.example` (if it exists)**

Check for `.env.example` at project root. If present, append:

```
# Zoho SMTP for admin invite emails (app-specific password if 2FA enabled)
ZOHO_SMTP_USER=
ZOHO_SMTP_PASSWORD=
APP_BASE_URL=https://autoapply.matthewbarlow.me
```

If `.env.example` does not exist, skip this step (do NOT create/modify `.env`).

- [ ] **Step 6: Commit**

```bash
git add core/email.py tests/core/test_email.py
git commit -m "[feat] Add Zoho SMTP invite email sender"
```

---

## Task 4: Admin router — invite + list

**Files:**
- Create: `web/routers/admin.py`
- Modify: `web/main.py` (import ~line 29, include ~line 130)
- Test: `tests/web/test_admin_invite.py`

Note: reuse the existing `require_admin` dependency from `web/routers/credits.py`
(import it) rather than redefining it.

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_admin_invite.py
# Mirror the client/auth setup used in tests/web/test_admin_set_tier.py
# (same require_admin path). Copy its fixtures/helpers for building an
# admin-authenticated and a non-admin TestClient.
from unittest.mock import patch

from db.database import AllowedEmail


def test_invite_requires_admin(user_client):
    r = user_client.post("/api/admin/invite", json={"email": "x@example.com"})
    assert r.status_code == 403


def test_invite_inserts_and_sends(admin_client, db_session):
    with patch("web.routers.admin.send_invite", return_value=True) as send:
        r = admin_client.post("/api/admin/invite", json={"email": "New@Example.com"})
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "new@example.com"
    assert body["already_invited"] is False
    assert body["emailed"] is True
    send.assert_called_once_with("new@example.com")
    assert db_session.query(AllowedEmail).filter_by(email="new@example.com").count() == 1


def test_invite_idempotent(admin_client, db_session):
    with patch("web.routers.admin.send_invite", return_value=False):
        admin_client.post("/api/admin/invite", json={"email": "dup@example.com"})
        r = admin_client.post("/api/admin/invite", json={"email": "dup@example.com"})
    assert r.json()["already_invited"] is True
    assert db_session.query(AllowedEmail).filter_by(email="dup@example.com").count() == 1


def test_list_invites(admin_client):
    with patch("web.routers.admin.send_invite", return_value=False):
        admin_client.post("/api/admin/invite", json={"email": "a@example.com"})
    r = admin_client.get("/api/admin/invites")
    assert r.status_code == 200
    emails = [row["email"] for row in r.json()]
    assert "a@example.com" in emails
```

Note: `admin_client` / `user_client` / `db_session` must match the fixture names
in `tests/web/test_admin_set_tier.py`. Open that file first and reuse its exact
fixtures; rename the parameters here to match if they differ.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/web/test_admin_invite.py -v`
Expected: FAIL (404 on the routes — router not mounted yet).

- [ ] **Step 3: Implement `web/routers/admin.py`**

```python
"""Admin-only operations: user invites (allowlist + email)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from core.email import send_invite
from db.database import Account, AllowedEmail, get_db
from web.routers.credits import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class InviteRequest(BaseModel):
    email: EmailStr


@router.post("/invite")
def invite_user(body: InviteRequest, db: Session = Depends(get_db),
                admin: Account = Depends(require_admin)):
    email = str(body.email).strip().lower()
    existing = db.query(AllowedEmail).filter_by(email=email).first()
    already = existing is not None
    if not already:
        db.add(AllowedEmail(email=email, invited_by=admin.id, created_at=_now()))
        db.commit()
    emailed = send_invite(email)
    return {"email": email, "already_invited": already, "emailed": emailed}


@router.get("/invites")
def list_invites(db: Session = Depends(get_db),
                 admin: Account = Depends(require_admin)):
    rows = db.query(AllowedEmail).order_by(AllowedEmail.id.desc()).all()
    return [{"email": r.email, "created_at": r.created_at} for r in rows]
```

Note: `EmailStr` requires `email-validator`. If `python -c "import email_validator"`
fails, either add it to `requirements.txt` and install into `.venv`, OR replace
`email: EmailStr` with `email: str` plus a basic check
(`if "@" not in email: raise HTTPException(400, "invalid email")`). Prefer the
plain-`str` route to avoid a new dependency unless `email-validator` is already
present.

- [ ] **Step 4: Mount the router in `web/main.py`**

Add with the other router imports (~line 29):

```python
from web.routers import admin as admin_router
```

Add with the other `include_router` calls (~line 130):

```python
app.include_router(admin_router.router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/web/test_admin_invite.py -v`
Expected: PASS (all 4)

- [ ] **Step 6: Commit**

```bash
git add web/routers/admin.py web/main.py tests/web/test_admin_invite.py
git commit -m "[feat] Add admin invite + list endpoints"
```

---

## Task 5: API client functions

**Files:**
- Modify: `react-dashboard/src/api.js` (near `getSystemBalance`, line ~286)

- [ ] **Step 1: Add the functions**

In `react-dashboard/src/api.js`, after `getSystemBalance`:

```javascript
export const inviteUser = (email) =>
  _fetch('/api/admin/invite', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  })

export const getInvites = () => _fetch('/api/admin/invites')
```

- [ ] **Step 2: Verify the build still compiles**

Run: `cd react-dashboard && npm run build`
Expected: build succeeds (no syntax errors).

- [ ] **Step 3: Commit**

```bash
git add react-dashboard/src/api.js
git commit -m "[feat] Add inviteUser/getInvites API client functions"
```

---

## Task 6: `CreditBalance` — admin system-balance with $/credits toggle

**Files:**
- Modify: `react-dashboard/src/components/widgets/CreditBalance.jsx`

Behavior: when `isAdmin` is true, fetch `getSystemBalance()` and show the system
balance instead of personal credits; clicking toggles `$X.XX` ⇄ `{remaining*1000}
credits` (no Buy modal). Non-admin behavior is unchanged.

- [ ] **Step 1: Update the component**

Replace the body of `react-dashboard/src/components/widgets/CreditBalance.jsx`
with:

```javascript
import { useState, useEffect, useCallback } from 'react'
import { getCredits, getSystemBalance } from '../../api'

const CREDITS_PER_DOLLAR = 1000

/**
 * Balance display. Non-admins see personal credits (click → Buy modal, via
 * `onClick`). Admins see the platform system balance instead; clicking toggles
 * between a dollar amount and the equivalent credit amount (no Buy modal).
 * `variant` selects navbar ('nav') vs settings-panel ('panel') vs 'settings'.
 */
export default function CreditBalance({ variant = 'nav', onClick, isAdmin = false }) {
  const [balance, setBalance] = useState(null)
  const [remaining, setRemaining] = useState(null) // admin: system $ remaining
  const [unit, setUnit] = useState('usd')           // admin toggle: 'usd' | 'credits'
  const [error, setError] = useState(false)

  const refresh = useCallback(() => {
    if (isAdmin) {
      getSystemBalance()
        .then((d) => { setRemaining(d.remaining); setError(false) })
        .catch(() => setError(true))
      return
    }
    getCredits()
      .then((d) => {
        setBalance(d.balance); setError(false)
        window.__creditRate = d.rate ?? 0
      })
      .catch(() => setError(true))
  }, [isAdmin])

  useEffect(() => {
    refresh()
    window.addEventListener('auto-apply:credits-stale', refresh)
    return () => window.removeEventListener('auto-apply:credits-stale', refresh)
  }, [refresh])

  let text
  if (error) {
    text = isAdmin ? '— balance' : '— credits'
  } else if (isAdmin) {
    if (remaining == null) text = '…'
    else if (unit === 'usd') {
      text = `$${Number(remaining).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    } else {
      text = `${Math.round(remaining * CREDITS_PER_DOLLAR).toLocaleString()} credits`
    }
  } else {
    text = balance == null ? '…' : `${balance.toLocaleString()} credits`
  }

  // Admin: click toggles units. Non-admin: delegate to `onClick` (Buy modal).
  const handleClick = isAdmin
    ? () => setUnit((u) => (u === 'usd' ? 'credits' : 'usd'))
    : onClick
  const title = isAdmin ? 'System balance — click to toggle $/credits' : undefined

  if (variant === 'panel') {
    return (
      <div className="flex items-center justify-between px-3 py-2 rounded-lg border border-space-border bg-white/5">
        <span className="text-xs uppercase tracking-widest text-space-dim">
          {isAdmin ? 'System' : 'Credits'}
        </span>
        <span className="text-sm font-mono text-purple-400">{text}</span>
      </div>
    )
  }

  if (variant === 'settings') {
    return (
      <button
        type="button"
        onClick={handleClick}
        title={title ?? 'Buy credits'}
        className="self-center text-sm font-mono text-purple-400 hover:text-purple-300 transition-colors"
      >
        {text}
      </button>
    )
  }

  return (
    <span
      className="text-sm font-medium text-purple-400 cursor-pointer hover:text-purple-300"
      title={title ?? 'Session usage'}
      onClick={handleClick}
    >
      {text}
    </span>
  )
}
```

- [ ] **Step 2: Verify the build compiles**

Run: `cd react-dashboard && npm run build`
Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add react-dashboard/src/components/widgets/CreditBalance.jsx
git commit -m "[feat] Admin system-balance display with $/credits toggle in CreditBalance"
```

---

## Task 7: `UserHome` — pass `isAdmin`, drop `SystemBalancePanel`

**Files:**
- Modify: `react-dashboard/src/components/widgets/UserHome.jsx`

- [ ] **Step 1: Track admin state in `UserHome`**

Near the other `useState` hooks in the `UserHome` component (~line 220), add:

```javascript
  const [isAdmin, setIsAdmin] = useState(false)
```

Add an effect to resolve it (place near the other top-level effects, ~line 222):

```javascript
  useEffect(() => { getMe().then((me) => setIsAdmin(!!me?.is_admin)).catch(() => {}) }, [])
```

- [ ] **Step 2: Pass `isAdmin` into `CreditBalance` and stop opening Buy for admins**

Replace the existing balance line (~line 383):

```javascript
        <CreditBalance variant="settings" onClick={() => setBuyOpen(true)} />
```

with:

```javascript
        <CreditBalance
          variant="settings"
          isAdmin={isAdmin}
          onClick={() => setBuyOpen(true)}
        />
```

(When `isAdmin` is true, `CreditBalance` ignores `onClick` and toggles units instead.)

- [ ] **Step 3: Remove the now-redundant `SystemBalancePanel`**

Delete the `SystemBalancePanel` function definition (lines ~12-49) and its usage
(`<SystemBalancePanel />`, ~line 401). Remove `getSystemBalance` and `getMe` from
the imports **only if** they become unused — note `getMe` is now used by the
effect in Step 1, so keep `getMe`; remove `getSystemBalance` from the import list
(it's used inside `CreditBalance`, not here).

- [ ] **Step 4: Verify the build compiles**

Run: `cd react-dashboard && npm run build`
Expected: build succeeds, no "unused import" or "undefined" errors.

- [ ] **Step 5: Commit**

```bash
git add react-dashboard/src/components/widgets/UserHome.jsx
git commit -m "[refactor] Fold system balance into CreditBalance for admins"
```

---

## Task 8: Navbar admin link + `/admin` route + AdminPage

**Files:**
- Modify: `react-dashboard/src/App.jsx` (pass `me` to Navbar; add route)
- Modify: `react-dashboard/src/components/Navbar.jsx` (admin link)
- Create: `react-dashboard/src/components/AdminPage.jsx`

- [ ] **Step 1: Create `AdminPage.jsx`**

```javascript
import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { getMe, inviteUser, getInvites } from '../api'

export default function AdminPage() {
  const [allowed, setAllowed] = useState(undefined) // undefined=loading
  const [email, setEmail] = useState('')
  const [status, setStatus] = useState(null) // { kind: 'ok'|'err', text }
  const [submitting, setSubmitting] = useState(false)
  const [invites, setInvites] = useState([])

  useEffect(() => {
    getMe().then((me) => setAllowed(!!me?.is_admin)).catch(() => setAllowed(false))
  }, [])

  const refreshInvites = useCallback(() => {
    getInvites().then(setInvites).catch(() => {})
  }, [])

  useEffect(() => { if (allowed) refreshInvites() }, [allowed, refreshInvites])

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

  if (allowed === undefined) return null
  if (!allowed) {
    return (
      <div className="min-h-screen flex items-center justify-center text-space-dim">
        <p>Not authorized. <Link to="/" className="text-purple-400 hover:underline">Go home</Link></p>
      </div>
    )
  }

  return (
    <div className="min-h-screen text-space-text p-8 max-w-xl mx-auto">
      <Link to="/" className="text-sm text-space-dim hover:text-purple-400">← Back</Link>
      <h1 className="text-2xl font-bold mt-4 mb-6">Admin — Invite Users</h1>

      <form onSubmit={submit} className="flex gap-2 mb-3">
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
        <p className={`text-sm mb-6 ${status.kind === 'ok' ? 'text-green-400' : 'text-red-400'}`}>
          {status.text}
        </p>
      )}

      <h2 className="text-xs uppercase tracking-widest text-space-dim mb-2">Invited</h2>
      <ul className="flex flex-col gap-1">
        {invites.map((inv) => (
          <li key={inv.email} className="flex justify-between text-sm border-b border-space-border/50 py-1">
            <span>{inv.email}</span>
            <span className="text-space-dim text-xs">{new Date(inv.created_at).toLocaleDateString()}</span>
          </li>
        ))}
        {invites.length === 0 && <li className="text-xs text-space-dim">No invites yet.</li>}
      </ul>
    </div>
  )
}
```

- [ ] **Step 2: Add the admin link to `Navbar.jsx`**

`Navbar` must accept `me`. Change the signature:

```javascript
export default function Navbar({ me }) {
```

In the right-hand nav `<div className="flex items-center gap-4">`, add the admin
link before the Help link:

```javascript
        {me?.is_admin && (
          <Link
            to="/admin"
            className="text-sm text-space-dim hover:text-purple-400 transition-colors"
          >
            Admin
          </Link>
        )}
```

Ensure `Link` is imported (it already is: `import { Link } from "react-router-dom"`).

- [ ] **Step 3: Wire `App.jsx` — pass `me`, add route, import AdminPage**

Add the import near the other component imports (~line 9):

```javascript
import AdminPage from './components/AdminPage'
```

Pass `me` to Navbar (~line 202):

```javascript
          <Navbar me={me} />
```

Add the `/admin` route inside `<Routes>` (alongside `/docs`, ~line 193):

```javascript
      <Route path="/admin" element={<AdminPage />} />
```

- [ ] **Step 4: Verify the build compiles**

Run: `cd react-dashboard && npm run build`
Expected: build succeeds.

- [ ] **Step 5: Commit**

```bash
git add react-dashboard/src/components/AdminPage.jsx react-dashboard/src/components/Navbar.jsx react-dashboard/src/App.jsx
git commit -m "[feat] Add admin navbar tab and invite page"
```

---

## Task 9: Full verification + docs

- [ ] **Step 1: Run the full backend test suite**

Run: `python -m pytest tests/ -q`
Expected: all pass (no regressions from the `is_allowed_email` signature change).

- [ ] **Step 2: Frontend build**

Run: `cd react-dashboard && npm run build`
Expected: succeeds.

- [ ] **Step 3: Manual smoke test (note results, do not skip)**

Start the app (`start.bat dev`), then as an **admin** account:
- Navbar shows an **Admin** link; the balance under your name shows `$…` and
  toggles to `… credits` on click.
- `/admin` page: submit an email → see a success message and the email appears
  in the Invited list.
As a **non-admin** (or logged-out check): no Admin link; balance shows personal
credits and opens the Buy modal on click.

- [ ] **Step 4: Update CONTEXT docs**

- `web/CONTEXT.md`: note the new `admin.py` router (invite/list, `require_admin`)
  and that `is_allowed_email` now checks the `allowed_email` table in addition to
  the `ALLOWED_EMAILS` env var.
- `react-dashboard/CONTEXT.md`: add `AdminPage.jsx` to the routing table and note
  `CreditBalance` admin behavior (system balance + $/credits toggle).
- `db/CONTEXT.md`: add the `allowed_email` table.

- [ ] **Step 5: Commit**

```bash
git add web/CONTEXT.md react-dashboard/CONTEXT.md db/CONTEXT.md
git commit -m "[docs] Document admin invite flow and allowed_email table"
```

---

## Deployment Notes (post-merge, requires user)

- Set Railway env vars: `ZOHO_SMTP_USER`, `ZOHO_SMTP_PASSWORD` (Zoho app-specific
  password), and optionally `APP_BASE_URL`.
- Alembic runs on startup (`init_db` / alembic-on-startup), so `allowed_email` is
  created automatically on deploy. No manual migration step needed.
