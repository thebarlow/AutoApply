# Misc Dashboard & Server Features — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add session cost tracking, graceful shutdown, empty-section badges, export master resume, and minor navbar polish to the auto-apply dashboard.

**Architecture:** Backend changes are additive (new modules + router registrations). Frontend Navbar is rewritten to be stateful. ProfileDetail receives incremental changes only — AccordionSection gets an `empty` prop, sections compute their own emptiness, and an Export Master button is inserted above Delete.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy, PyQt6, React 18, Tailwind CSS, Playwright (PDF rendering)

---

## Files Changed

| File | Change |
|---|---|
| `core/session_cost.py` | New — thread-safe in-memory cost accumulator |
| `core/llm.py` | Extract cost from `response.usage` after every call |
| `core/job.py` | Same cost extraction in `score()` and `extract_description()` |
| `web/routers/session_cost_router.py` | New — `GET /api/session-cost` |
| `web/routers/shutdown.py` | New — `POST /api/shutdown` |
| `web/routers/llm_status_router.py` | Enrich response with `in_flight` list (title + company) |
| `web/main.py` | Register both new routers |
| `generator/master_template.html` | New — Jinja2 HTML template for unconstrained master resume |
| `generator/master.css` | New — CSS for master resume (relaxed page constraints) |
| `web/routers/config.py` | Add `POST /api/profile/export-master` |
| `tray_app/main.py` | Add server heartbeat → auto-exit when server dies |
| `react-dashboard/src/components/Navbar.jsx` | Full rewrite: Help text, Session Cost + modal, Power button |
| `react-dashboard/src/components/widgets/ProfileDetail.jsx` | AccordionSection `empty` prop + Export Master button |
| `tests/core/test_session_cost.py` | New — unit tests |
| `tests/web/test_session_cost_router.py` | New — endpoint tests |
| `tests/web/test_shutdown.py` | New — shutdown endpoint tests |
| `tests/web/test_llm_status_router.py` | New — enriched llm-status tests |

---

## Task 1: `core/session_cost.py` — session cost accumulator

**Files:**
- Create: `core/session_cost.py`
- Create: `tests/core/test_session_cost.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/core/test_session_cost.py`:

```python
import importlib
import sys
import pytest


def _fresh():
    """Reload module so each test starts with a zeroed accumulator."""
    if "core.session_cost" in sys.modules:
        del sys.modules["core.session_cost"]
    import core.session_cost as m
    return m


def test_initial_total_is_zero():
    m = _fresh()
    assert m.get_total() == 0.0


def test_add_cost_accumulates():
    m = _fresh()
    m.add_cost(0.001)
    m.add_cost(0.002)
    assert abs(m.get_total() - 0.003) < 1e-10


def test_add_cost_zero_is_noop():
    m = _fresh()
    m.add_cost(0.0)
    assert m.get_total() == 0.0


def test_reset_clears_total():
    m = _fresh()
    m.add_cost(1.5)
    m.reset()
    assert m.get_total() == 0.0


def test_thread_safety():
    import threading
    m = _fresh()
    threads = [threading.Thread(target=lambda: m.add_cost(1.0)) for _ in range(100)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert abs(m.get_total() - 100.0) < 1e-6
```

- [ ] **Step 2: Run tests — expect failure**

```
pytest tests/core/test_session_cost.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` for `core.session_cost`.

- [ ] **Step 3: Implement `core/session_cost.py`**

```python
from __future__ import annotations

import threading

_lock = threading.Lock()
_total: float = 0.0


def add_cost(cost: float) -> None:
    global _total
    with _lock:
        _total += cost


def get_total() -> float:
    with _lock:
        return _total


def reset() -> None:
    global _total
    with _lock:
        _total = 0.0
```

- [ ] **Step 4: Run tests — expect pass**

```
pytest tests/core/test_session_cost.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```
git add core/session_cost.py tests/core/test_session_cost.py
git commit -m "[feat] Add session cost accumulator"
```

---

## Task 2: Wire cost extraction into all LLM callers

**Files:**
- Modify: `core/llm.py:150-176` (`call_llm`)
- Modify: `core/job.py:310-318` (`score`)
- Modify: `core/job.py:400-410` (`extract_description`)

The OpenRouter API returns a `cost` attribute on the `usage` object. Other providers leave it absent — we use `0.0` silently.

- [ ] **Step 1: Update `call_llm` in `core/llm.py`**

Replace the function body (lines 165-176):

```python
def call_llm(prompt: str, client: Any, model: str, max_tokens: int = 8192) -> str:
    from core import session_cost

    response = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    usage = getattr(response, "usage", None)
    if usage is not None:
        session_cost.add_cost(float(getattr(usage, "cost", None) or 0.0))
    choice = response.choices[0]
    content = choice.message.content
    if not content:
        raise RuntimeError(
            f"LLM returned empty response (finish_reason={choice.finish_reason!r})"
        )
    return content.strip()
```

- [ ] **Step 2: Update `score()` in `core/job.py`**

After line 318 (`raise RuntimeError(f"LLM API error: {e}") from e`), add cost extraction. Insert after the entire try/except block (after line 318, before line 319 `choice = response.choices[0]`):

```python
        usage = getattr(response, "usage", None)
        if usage is not None:
            from core import session_cost
            session_cost.add_cost(float(getattr(usage, "cost", None) or 0.0))
```

- [ ] **Step 3: Update `extract_description()` in `core/job.py`**

After the `client.chat.completions.create(...)` call (around line 402-406), add cost extraction immediately after the call, before the `choice = response.choices[0]` line:

```python
        usage = getattr(response, "usage", None)
        if usage is not None:
            from core import session_cost
            session_cost.add_cost(float(getattr(usage, "cost", None) or 0.0))
```

- [ ] **Step 4: Run existing LLM tests to confirm nothing broke**

```
pytest tests/core/test_llm.py tests/core/test_job.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```
git add core/llm.py core/job.py
git commit -m "[feat] Extract LLM response cost into session accumulator"
```

---

## Task 3: `GET /api/session-cost` endpoint

**Files:**
- Create: `web/routers/session_cost_router.py`
- Create: `tests/web/test_session_cost_router.py`
- Modify: `web/main.py`

- [ ] **Step 1: Write the failing test**

Create `tests/web/test_session_cost_router.py`:

```python
import sys
import pytest
from fastapi.testclient import TestClient

from web.main import app


@pytest.fixture(autouse=True)
def reset_cost():
    import core.session_cost as sc
    sc.reset()
    yield
    sc.reset()


@pytest.fixture
def client():
    return TestClient(app)


def test_session_cost_starts_at_zero(client):
    resp = client.get("/api/session-cost")
    assert resp.status_code == 200
    assert resp.json() == {"total": 0.0}


def test_session_cost_reflects_accumulated_cost(client):
    import core.session_cost as sc
    sc.add_cost(0.00123456)
    resp = client.get("/api/session-cost")
    assert resp.status_code == 200
    assert abs(resp.json()["total"] - 0.00123456) < 1e-10
```

- [ ] **Step 2: Run — expect failure**

```
pytest tests/web/test_session_cost_router.py -v
```

Expected: 404 for `/api/session-cost`.

- [ ] **Step 3: Create `web/routers/session_cost_router.py`**

```python
from __future__ import annotations

from fastapi import APIRouter

from core import session_cost

router = APIRouter(prefix="/api")


@router.get("/session-cost")
def get_session_cost() -> dict:
    return {"total": session_cost.get_total()}
```

- [ ] **Step 4: Register the router in `web/main.py`**

Add import and `app.include_router` alongside the other routers:

```python
from web.routers import session_cost_router
```

```python
app.include_router(session_cost_router.router)
```

- [ ] **Step 5: Run — expect pass**

```
pytest tests/web/test_session_cost_router.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```
git add web/routers/session_cost_router.py web/main.py tests/web/test_session_cost_router.py
git commit -m "[feat] Add GET /api/session-cost endpoint"
```

---

## Task 4: Shutdown endpoint + enriched LLM status

**Files:**
- Create: `web/routers/shutdown.py`
- Create: `tests/web/test_shutdown.py`
- Modify: `web/routers/llm_status_router.py`
- Create: `tests/web/test_llm_status_router.py`
- Modify: `web/main.py`

- [ ] **Step 1: Write failing tests for shutdown**

Create `tests/web/test_shutdown.py`:

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import get_db, Base
from web.main import app


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def client(db_session, monkeypatch):
    app.dependency_overrides[get_db] = lambda: db_session
    # Patch os._exit so tests don't kill the process
    monkeypatch.setattr("web.routers.shutdown._exit_process", lambda: None)
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_shutdown_immediate_returns_ok(client):
    resp = client.post("/api/shutdown?mode=immediate")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert resp.json()["mode"] == "immediate"


def test_shutdown_wait_returns_ok(client):
    resp = client.post("/api/shutdown?mode=wait")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert resp.json()["mode"] == "wait"
```

- [ ] **Step 2: Run — expect failure**

```
pytest tests/web/test_shutdown.py -v
```

Expected: 404 or attribute error.

- [ ] **Step 3: Create `web/routers/shutdown.py`**

```python
from __future__ import annotations

import os
import threading
import time

from fastapi import APIRouter

from web import llm_status

router = APIRouter(prefix="/api")


def _exit_process() -> None:
    os._exit(0)


def _delayed_exit(delay: float = 0.3) -> None:
    def _run():
        time.sleep(delay)
        _exit_process()
    threading.Thread(target=_run, daemon=True).start()


def _wait_and_exit() -> None:
    def _run():
        while llm_status.snapshot():
            time.sleep(1)
        _exit_process()
    threading.Thread(target=_run, daemon=True).start()


@router.post("/shutdown")
def shutdown(mode: str = "immediate") -> dict:
    if mode == "wait":
        _wait_and_exit()
        return {"ok": True, "mode": "wait"}
    _delayed_exit()
    return {"ok": True, "mode": "immediate"}
```

- [ ] **Step 4: Write failing tests for enriched llm-status**

Create `tests/web/test_llm_status_router.py`:

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import get_db, Base
from web.main import app
from core.job import Job


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_llm_status_empty(client):
    resp = client.get("/api/llm-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["processing"] == []
    assert data["in_flight"] == []


def test_llm_status_in_flight_includes_display_info(client, db_session):
    from web import llm_status
    job = Job(job_key="abc123", title="Backend Engineer", company="Acme Corp", state="pending", description="x")
    db_session.add(job)
    db_session.commit()

    llm_status.start("abc123", "score")
    try:
        resp = client.get("/api/llm-status")
        data = resp.json()
        assert len(data["in_flight"]) == 1
        entry = data["in_flight"][0]
        assert entry["job_key"] == "abc123"
        assert entry["title"] == "Backend Engineer"
        assert entry["company"] == "Acme Corp"
        assert "score" in entry["actions"]
    finally:
        llm_status.finish("abc123", "score")
```

- [ ] **Step 5: Run llm-status tests — expect failure**

```
pytest tests/web/test_llm_status_router.py -v
```

Expected: `KeyError: 'in_flight'`.

- [ ] **Step 6: Update `web/routers/llm_status_router.py`**

```python
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db.database import get_db
from core.job import Job
from web import llm_status

router = APIRouter(prefix="/api")


@router.get("/llm-status")
def get_llm_status(db: Session = Depends(get_db)) -> dict:
    job_keys = llm_status.snapshot()
    actions = llm_status.action_snapshot()

    jobs = (
        db.query(Job).filter(Job.job_key.in_(job_keys)).all()
        if job_keys else []
    )
    display = {j.job_key: {"title": j.title or "", "company": j.company or ""} for j in jobs}

    in_flight = [
        {
            "job_key": jk,
            "title": display.get(jk, {}).get("title", jk),
            "company": display.get(jk, {}).get("company", ""),
            "actions": actions.get(jk, []),
        }
        for jk in job_keys
    ]

    return {
        "processing": job_keys,
        "actions": actions,
        "in_flight": in_flight,
    }
```

- [ ] **Step 7: Register shutdown router in `web/main.py`**

Add import:

```python
from web.routers import shutdown as shutdown_router
```

Add include:

```python
app.include_router(shutdown_router.router)
```

- [ ] **Step 8: Run all new tests**

```
pytest tests/web/test_shutdown.py tests/web/test_llm_status_router.py -v
```

Expected: all pass.

- [ ] **Step 9: Commit**

```
git add web/routers/shutdown.py web/routers/llm_status_router.py web/main.py tests/web/test_shutdown.py tests/web/test_llm_status_router.py
git commit -m "[feat] Add shutdown endpoint and enrich llm-status with job display info"
```

---

## Task 5: Tray app — server heartbeat auto-exit

**Files:**
- Modify: `tray_app/main.py`

No automated test for this (requires PyQt6 event loop). Manual verification is in Task 9.

- [ ] **Step 1: Add heartbeat to `tray_app/main.py`**

Add `urllib.request` import at the top (stdlib, no new dep):

```python
import urllib.request
```

Add this function before `main()`:

```python
def _make_heartbeat(app: QApplication) -> QTimer:
    """Exit the tray app when the FastAPI server is unreachable for 2 consecutive checks."""
    _misses: list[int] = [0]

    def _check() -> None:
        try:
            urllib.request.urlopen("http://localhost:8080/api/session-cost", timeout=1)
            _misses[0] = 0
        except Exception:
            _misses[0] += 1
            if _misses[0] >= 2:
                app.quit()

    t = QTimer()
    t.timeout.connect(_check)
    return t
```

In `main()`, after `ws.start()` and before `sys.exit(app.exec())`, add:

```python
    heartbeat = _make_heartbeat(app)
    # Delay 5 seconds to allow server startup before monitoring begins
    QTimer.singleShot(5000, lambda: heartbeat.start(2000))
```

- [ ] **Step 2: Commit**

```
git add tray_app/main.py
git commit -m "[feat] Tray app exits automatically when server shuts down"
```

---

## Task 6: Export Master PDF

**Files:**
- Create: `generator/master_template.html`
- Create: `generator/master.css`
- Modify: `web/routers/config.py`
- Create: `tests/web/test_export_master.py`

- [ ] **Step 1: Create `generator/master_template.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Master Resume</title>
  <style>{{ css }}</style>
</head>
<body>
  <main class="resume">

    {% if name %}
    <header class="resume-header">
      <h1>{{ name }}</h1>
      <div class="contact-grid">

        {% if email %}
        <div class="contact-item">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="m2 7 10 7 10-7"/></svg>
          <span>{{ email }}</span>
        </div>
        {% endif %}

        {% if phone %}
        <div class="contact-item">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07A19.5 19.5 0 0 1 4.69 13a19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 3.62 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg>
          <span>{{ phone }}</span>
        </div>
        {% endif %}

        {% if location %}
        <div class="contact-item">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7z"/><circle cx="12" cy="9" r="2.5"/></svg>
          <span>{{ location }}</span>
        </div>
        {% endif %}

        {% if website %}
        <div class="contact-item">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
          <a href="{{ website }}">{{ website | strip_url }}</a>
        </div>
        {% endif %}

        {% if linkedin %}
        <div class="contact-item">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><path d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-2-2 2 2 0 0 0-2 2v7h-4v-7a6 6 0 0 1 6-6z"/><rect x="2" y="9" width="4" height="12"/><circle cx="4" cy="4" r="2"/></svg>
          <a href="{{ linkedin }}">{{ linkedin | strip_url }}</a>
        </div>
        {% endif %}

        {% if github %}
        <div class="contact-item">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0 1 12 6.844a9.59 9.59 0 0 1 2.504.337c1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0 0 22 12.017C22 6.484 17.522 2 12 2z"/></svg>
          <a href="{{ github }}">{{ github | strip_url }}</a>
        </div>
        {% endif %}

      </div>
    </header>
    {% endif %}

    {{ content_html | safe }}

  </main>
</body>
</html>
```

- [ ] **Step 2: Create `generator/master.css`**

```css
@page {
  size: letter;
  margin: 0.55in 0.6in 0.55in 0.6in;
}

html, body {
  margin: 0;
  padding: 0;
  font-family: "Helvetica Neue", "Helvetica", "Arial", sans-serif;
  font-size: 10pt;
  line-height: 1.4;
  color: #111;
}

.resume-header {
  margin-bottom: 0.15in;
}

.resume-header h1 {
  font-size: 20pt;
  font-weight: 700;
  letter-spacing: 0.01em;
  margin: 0 0 0.06in 0;
}

.contact-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  row-gap: 0.04in;
  column-gap: 0.1in;
}

.contact-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 8.5pt;
  color: #444;
}

.contact-item a {
  color: #444;
  text-decoration: none;
}

h2 {
  font-size: 10pt;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  border-bottom: 1pt solid #bbb;
  margin: 0.18in 0 0.06in 0;
  padding-bottom: 0.03in;
}

p, li {
  margin: 0.03in 0;
}

ul {
  margin: 0.03in 0 0.06in 0.18in;
  padding: 0;
}

strong {
  font-weight: 600;
}

em {
  font-style: italic;
}
```

- [ ] **Step 3: Write the failing test**

Create `tests/web/test_export_master.py`:

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import get_db, Base
from web.main import app
from core.user import User


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def client(db_session, monkeypatch):
    app.dependency_overrides[get_db] = lambda: db_session
    # Stub render_pdf so the test doesn't need Playwright/pandoc
    def _fake_render_pdf(md_path, pdf_path, template_path, max_pages=None, meta=None):
        pdf_path.write_bytes(b"%PDF-1.4 fake")
    monkeypatch.setattr("web.routers.config.render_pdf", _fake_render_pdf)
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_export_master_returns_pdf(client, db_session):
    user = User(name="Test", data='{"first_name":"Jane","last_name":"Doe","email":"jane@example.com","skills":["Python"],"work_history":[],"education":[],"projects":[]}')
    db_session.add(user)
    db_session.commit()

    resp = client.post("/api/profile/export-master")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert "master_resume.pdf" in resp.headers.get("content-disposition", "")


def test_export_master_no_profile_returns_404(client):
    resp = client.post("/api/profile/export-master")
    assert resp.status_code == 404
```

- [ ] **Step 4: Run — expect failure**

```
pytest tests/web/test_export_master.py -v
```

Expected: 404 for the endpoint (not yet created).

- [ ] **Step 5: Add helper and endpoint to `web/routers/config.py`**

Add these imports at the top of `config.py` (alongside existing ones):

```python
import shutil
import tempfile
from pathlib import Path as _Path
from fastapi.responses import Response
from core.utils import render_pdf
```

Add the helper function and endpoint (before or after existing profile endpoints):

```python
_MASTER_TEMPLATE = _Path(__file__).parent.parent.parent / "generator" / "master_template.html"


def _build_master_resume_md(user) -> str:
    lines: list[str] = []

    if user.skills:
        lines += ["## Skills", ", ".join(user.skills), ""]

    if user.work_history:
        lines.append("## Experience")
        for entry in user.work_history:
            end = entry.end or "Present"
            lines.append(f"**{entry.title}** | {entry.company} | {entry.start} – {end}")
            if entry.summary:
                lines += ["", entry.summary]
            lines.append("")

    if user.education:
        lines.append("## Education")
        for edu in user.education:
            gpa_str = f" — GPA: {edu.gpa}" if edu.gpa else ""
            lines.append(
                f"**{edu.degree} {edu.field}** | {edu.institution} | {edu.graduated}{gpa_str}"
            )
            lines.append("")

    if user.projects:
        lines.append("## Projects")
        for proj in user.projects:
            tech_str = (
                f"  \n*Technologies: {', '.join(proj.technologies)}*"
                if proj.technologies else ""
            )
            url_str = f"  \n{proj.url}" if proj.url else ""
            lines.append(f"**{proj.name}** — {proj.description}{tech_str}{url_str}")
            lines.append("")

    roles = user.target_roles
    has_roles = (isinstance(roles, list) and len(roles) > 0) or bool(roles)
    if has_roles or user.target_salary_min or user.target_salary_max:
        lines.append("## Target Roles")
        if has_roles:
            roles_str = ", ".join(roles) if isinstance(roles, list) else str(roles)
            lines.append(f"Seeking: {roles_str}")
        if user.target_salary_min or user.target_salary_max:
            sal_min = f"${int(user.target_salary_min):,}" if user.target_salary_min else "?"
            sal_max = f"${int(user.target_salary_max):,}" if user.target_salary_max else "?"
            lines.append(f"Salary Range: {sal_min} – {sal_max}")
        lines.append("")

    return "\n".join(lines)


@router.post("/api/profile/export-master")
def export_master_resume(db: Session = Depends(get_db)) -> Response:
    from core.user import User

    user = User.load(db)
    if user is None:
        raise HTTPException(status_code=404, detail="No profile found")

    md_content = _build_master_resume_md(user)
    tmpdir = _Path(tempfile.mkdtemp())
    try:
        md_path = tmpdir / "master.md"
        pdf_path = tmpdir / "master_resume.pdf"
        md_path.write_text(md_content, encoding="utf-8")

        meta = {
            "name": f"{user.first_name} {user.last_name}".strip(),
            "email": user.email,
            "phone": user.phone,
            "location": user.location,
            "linkedin": user.linkedin,
            "github": user.github,
            "website": user.website,
        }
        render_pdf(md_path, pdf_path, _MASTER_TEMPLATE, meta=meta)
        pdf_bytes = pdf_path.read_bytes()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=master_resume.pdf"},
    )
```

- [ ] **Step 6: Run — expect pass**

```
pytest tests/web/test_export_master.py -v
```

Expected: 2 passed.

- [ ] **Step 7: Commit**

```
git add generator/master_template.html generator/master.css web/routers/config.py tests/web/test_export_master.py
git commit -m "[feat] Add export master resume endpoint"
```

---

## Task 7: Rewrite `Navbar.jsx`

**Files:**
- Modify: `react-dashboard/src/components/Navbar.jsx`

No automated JS test infra is present; verify manually in Task 9.

- [ ] **Step 1: Replace `Navbar.jsx` entirely**

```jsx
import { useState, useEffect, useRef } from "react";
import { Link } from "react-router-dom";

export default function Navbar() {
  const [sessionCost, setSessionCost] = useState(0);
  const [costModalOpen, setCostModalOpen] = useState(false);
  const [shutdownOpen, setShutdownOpen] = useState(false);
  const [inFlight, setInFlight] = useState([]);
  const shutdownRef = useRef(null);

  useEffect(() => {
    const poll = () =>
      fetch("/api/session-cost")
        .then((r) => r.json())
        .then((d) => setSessionCost(d.total))
        .catch(() => {});
    poll();
    const id = setInterval(poll, 5000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (!shutdownOpen) return;
    const handler = (e) => {
      if (shutdownRef.current && !shutdownRef.current.contains(e.target))
        setShutdownOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [shutdownOpen]);

  useEffect(() => {
    if (!costModalOpen) return;
    const handler = (e) => {
      if (e.key === "Escape") setCostModalOpen(false);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [costModalOpen]);

  const handlePower = async () => {
    const data = await fetch("/api/llm-status").then((r) => r.json());
    if (!data.in_flight || data.in_flight.length === 0) {
      await fetch("/api/shutdown?mode=immediate", { method: "POST" });
    } else {
      setInFlight(data.in_flight);
      setShutdownOpen(true);
    }
  };

  const doShutdown = async (mode) => {
    await fetch(`/api/shutdown?mode=${mode}`, { method: "POST" });
    setShutdownOpen(false);
  };

  return (
    <nav className="sticky top-0 z-50 w-full backdrop-blur-md bg-space-bg/80 border-b border-space-border px-6 py-3 flex items-center justify-between">
      <Link
        to="/"
        className="text-lg font-bold tracking-tight text-white hover:text-purple-300 transition-colors"
      >
        Auto Apply
      </Link>

      <div className="flex items-center gap-4">
        {/* Session Cost */}
        <button
          onClick={() => setCostModalOpen(true)}
          className="text-sm font-medium text-purple-400 hover:text-purple-300 transition-colors bg-transparent border-0 p-0 cursor-pointer"
        >
          Session Cost: ${sessionCost.toFixed(2)}
        </button>

        {/* Help link */}
        <a
          href="/docs"
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm text-space-dim hover:text-purple-400 transition-colors"
          aria-label="Help"
        >
          Help
        </a>

        {/* Power button */}
        <div className="relative" ref={shutdownRef}>
          <button
            onClick={handlePower}
            className="w-7 h-7 rounded-full border-2 border-red-500 flex items-center justify-center text-red-500 hover:bg-red-500/10 transition-colors"
            aria-label="Shutdown"
          >
            <svg
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
            >
              <path d="M12 2v8" />
              <path d="M6.3 5.3a9 9 0 1 0 11.4 0" />
            </svg>
          </button>

          {shutdownOpen && (
            <div className="absolute right-0 top-9 bg-[#0f0f1a] border border-space-border rounded-lg shadow-xl w-68 p-3 z-50">
              <p className="text-xs text-space-dim mb-2">LLM calls in progress:</p>
              <ul className="flex flex-col gap-1 mb-3">
                {inFlight.map((item, i) => (
                  <li key={i} className="text-xs text-space-text">
                    {item.title} | {item.company}
                    {item.actions.length > 0 && (
                      <span className="text-space-dim ml-1">
                        ({item.actions.join(", ")})
                      </span>
                    )}
                  </li>
                ))}
              </ul>
              <div className="flex gap-2">
                <button
                  onClick={() => doShutdown("immediate")}
                  className="flex-1 py-1.5 text-xs rounded bg-red-600 hover:bg-red-500 text-white font-semibold transition-colors"
                >
                  Exit Now
                </button>
                <button
                  onClick={() => doShutdown("wait")}
                  className="flex-1 py-1.5 text-xs rounded border border-space-border text-space-dim hover:text-space-text transition-colors"
                >
                  Exit After LLM
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Session Cost modal */}
      {costModalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
          onClick={() => setCostModalOpen(false)}
        >
          <div
            className="bg-[#0f0f1a] border border-space-border rounded-xl p-6 shadow-2xl min-w-[240px]"
            onClick={(e) => e.stopPropagation()}
          >
            <p className="text-sm font-semibold text-space-text mb-2">Session Cost</p>
            <p className="text-2xl font-mono text-purple-400">
              ${sessionCost.toFixed(8)}
            </p>
            <p className="text-xs text-space-dim mt-2">Resets on server restart</p>
            <button
              className="mt-4 w-full py-1.5 text-xs text-space-dim border border-space-border rounded hover:text-space-text transition-colors"
              onClick={() => setCostModalOpen(false)}
            >
              Close
            </button>
          </div>
        </div>
      )}
    </nav>
  );
}
```

- [ ] **Step 2: Commit**

```
git add react-dashboard/src/components/Navbar.jsx
git commit -m "[feat] Navbar: Help text, session cost display, power shutdown button"
```

---

## Task 8: ProfileDetail — empty badges + Export Master button

**Files:**
- Modify: `react-dashboard/src/components/widgets/ProfileDetail.jsx`

Four changes to this file:
1. `AccordionSection` gains an `empty` prop.
2. Each section component computes its own `empty` and passes it down.
3. `isSectionEmpty` helper added.
4. Export Master button + handler inserted above Delete button.

- [ ] **Step 1: Add `isSectionEmpty` helper**

Add this function after the `ChevronDown` component (around line 33), before `AccordionSection`:

```jsx
function isSectionEmpty(section, d) {
  switch (section) {
    case "identity":
      return (
        !d.first_name && !d.last_name && !d.hero &&
        !d.email && !d.phone && !d.location &&
        !d.linkedin && !d.github && !d.website
      );
    case "skills":
      return !d.skills || d.skills.length === 0;
    case "experience":
      return !d.work_history || d.work_history.length === 0;
    case "education":
      return !d.education || d.education.length === 0;
    case "projects":
      return !d.projects || d.projects.length === 0;
    case "job_prefs": {
      const roles = d.target_roles;
      const hasRoles = Array.isArray(roles) ? roles.length > 0 : Boolean(roles);
      return !hasRoles && !d.target_salary_min && !d.target_salary_max;
    }
    default:
      return false;
  }
}
```

- [ ] **Step 2: Add `empty` prop to `AccordionSection`**

Change the function signature from:

```jsx
function AccordionSection({ id, title, editButton, children }) {
```

to:

```jsx
function AccordionSection({ id, title, editButton, empty, children }) {
```

Change the title span from:

```jsx
<span className="text-xs font-semibold uppercase tracking-widest text-space-dim">{title}</span>
```

to:

```jsx
<span className="text-xs font-semibold uppercase tracking-widest text-space-dim flex items-center gap-2">
  {title}
  {empty && (
    <span className="font-normal normal-case tracking-normal text-[10px] text-space-dim/50">
      [empty]
    </span>
  )}
</span>
```

- [ ] **Step 3: Pass `empty` in each section component**

For each section listed below, find its `<AccordionSection ...>` call and add the `empty` prop:

**IdentitySection** (around line 183):
```jsx
<AccordionSection id="identity" title="Identity" editButton={<EditBtn onClick={openModal} />} empty={isSectionEmpty("identity", data)}>
```

**SkillsSection** — find its `<AccordionSection id="skills" ...>` call and add:
```jsx
empty={isSectionEmpty("skills", data)}
```

**ExperienceSection** — find its `<AccordionSection id="experience" ...>` call and add:
```jsx
empty={isSectionEmpty("experience", data)}
```

**EducationSection** — find its `<AccordionSection id="education" ...>` call and add:
```jsx
empty={isSectionEmpty("education", data)}
```

**ProjectsSection** — find its `<AccordionSection id="projects" ...>` call and add:
```jsx
empty={isSectionEmpty("projects", data)}
```

**JobPrefsSection** — find its `<AccordionSection id="job_prefs" ...>` (or similar id) call and add:
```jsx
empty={isSectionEmpty("job_prefs", data)}
```

- [ ] **Step 4: Add Export Master state and handler in `ProfileDetailPanel`**

In the `ProfileDetailPanel` function (around line 1244), add state alongside existing `confirmDelete`/`deleting` state:

```jsx
const [exporting, setExporting] = useState(false)
```

Add the handler alongside `handleDelete`:

```jsx
const handleExportMaster = async () => {
  setExporting(true)
  try {
    const res = await fetch(`/api/profile/export-master`, { method: 'POST' })
    if (!res.ok) throw new Error('Export failed')
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'master_resume.pdf'
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    console.error('Export master failed:', e)
  } finally {
    setExporting(false)
  }
}
```

- [ ] **Step 5: Insert Export Master button above Delete button**

Find the Delete button (around line 1304):

```jsx
        <button
          onClick={() => { setDeleteError(null); setConfirmDelete(true) }}
          className="w-full py-2 rounded-lg border border-red-500/30 text-sm text-red-400 hover:bg-red-500/10 transition-colors mt-2"
        >
          Delete Profile
        </button>
```

Insert the Export Master button immediately before it:

```jsx
        <button
          onClick={handleExportMaster}
          disabled={exporting}
          className="w-full py-2 rounded-lg border border-purple-500/30 text-sm text-purple-400 hover:bg-purple-500/10 transition-colors mt-2 disabled:opacity-50"
        >
          {exporting ? 'Generating…' : 'Export Master'}
        </button>
```

- [ ] **Step 6: Commit**

```
git add react-dashboard/src/components/widgets/ProfileDetail.jsx
git commit -m "[feat] Profile: empty section badges and Export Master button"
```

---

## Task 9: Build and verify

- [ ] **Step 1: Run full backend test suite**

```
pytest -v
```

Expected: all existing tests pass, new tests pass.

- [ ] **Step 2: Build the React dashboard**

```
cd react-dashboard && npm run build
```

Expected: exits 0, `dist/` updated.

- [ ] **Step 3: Start the app**

```
start.bat
```

Verify in browser at `http://localhost:8080`:
- Navbar shows "Session Cost: $0.00" (clickable → modal with 8 decimal places)
- Navbar shows "Help" link (opens docs)
- Navbar shows red power button (top right)
- Profile panel shows `[empty]` on sections with no content
- Profile panel shows "Export Master" button above "Delete Profile"
- Clicking power button with no LLM in-flight shuts down immediately
- Clicking "Export Master" downloads a PDF

- [ ] **Step 4: Final commit if any fixups were needed**

```
git add -A
git commit -m "[chore] Post-verification fixups"
```
