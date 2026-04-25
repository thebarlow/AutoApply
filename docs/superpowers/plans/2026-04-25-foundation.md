# Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish the shared database models, types, and project skeleton that every subsequent subsystem will build on.

**Architecture:** SQLite database accessed via SQLAlchemy ORM. Shared Python types (enums, dataclasses) live in `core/types.py` and are imported by all modules. The DB layer (`db/`) owns model definitions, engine setup, and default config seeding — nothing else touches those concerns directly.

**Tech Stack:** Python 3.13, SQLAlchemy 2.0, pytest

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `requirements.txt` | Create | All project dependencies |
| `.env.example` | Create | Environment variable template |
| `pytest.ini` | Create | Pytest configuration |
| `core/__init__.py` | Create | Package marker |
| `core/types.py` | Create | `JobState` enum, `SearchConfig` dataclass, `UserProfile` dataclass |
| `db/__init__.py` | Create | Package marker |
| `db/models.py` | Create | SQLAlchemy ORM models: `Job`, `Config`, `UserProfile` |
| `db/database.py` | Create | Engine, `SessionLocal`, `init_db()`, `get_db()` |
| `db/seed.py` | Create | `seed_default_config()` — inserts defaults on first run |
| `tests/__init__.py` | Create | Package marker |
| `tests/conftest.py` | Create | In-memory SQLite session fixture |
| `tests/db/__init__.py` | Create | Package marker |
| `tests/db/test_models.py` | Create | CRUD + constraint tests for all three models |

---

### Task 1: Install missing dependencies and create requirements.txt

**Files:**
- Create: `requirements.txt`

- [ ] **Step 1: Install missing packages**

```bash
pip install anthropic playwright playwright-stealth gspread google-auth pytest-asyncio
```

Expected: packages install without errors.

- [ ] **Step 2: Install Playwright browsers**

```bash
playwright install chromium
```

Expected: Chromium browser downloaded.

- [ ] **Step 3: Create requirements.txt**

```
sqlalchemy>=2.0
fastapi>=0.121
uvicorn>=0.38
httpx>=0.28
python-dotenv>=1.0
anthropic>=0.40
playwright>=1.49
playwright-stealth>=1.0
gspread>=6.1
google-auth>=2.37
pytest>=8.0
pytest-asyncio>=0.24
```

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "[chore] Add requirements.txt"
```

---

### Task 2: Create .env.example and pytest.ini

**Files:**
- Create: `.env.example`
- Create: `pytest.ini`

- [ ] **Step 1: Create .env.example**

```
DATABASE_URL=sqlite:///auto_apply.db
ANTHROPIC_API_KEY=your_anthropic_api_key_here
GOOGLE_SHEETS_ID=your_google_sheet_id_here
GOOGLE_SERVICE_ACCOUNT_JSON=path/to/service_account.json
```

- [ ] **Step 2: Verify .env is in .gitignore**

```bash
grep "^\.env$" .gitignore
```

Expected: prints `.env`. If missing, add `.env` to `.gitignore` before continuing.

- [ ] **Step 3: Create pytest.ini**

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
```

- [ ] **Step 4: Commit**

```bash
git add .env.example pytest.ini
git commit -m "[chore] Add .env.example and pytest config"
```

---

### Task 3: Create core/types.py

**Files:**
- Create: `core/__init__.py`
- Create: `core/types.py`

- [ ] **Step 1: Write the failing test**

Create `tests/__init__.py` (empty) and `tests/core/__init__.py` (empty), then create `tests/core/test_types.py`:

```python
from core.types import JobState, SearchConfig, UserProfile


def test_job_state_values():
    assert JobState.SCRAPED == "scraped"
    assert JobState.SCORED == "scored"
    assert JobState.PENDING_REVIEW == "pending_review"
    assert JobState.APPROVED == "approved"
    assert JobState.GENERATED == "generated"
    assert JobState.APPLIED == "applied"
    assert JobState.REJECTED == "rejected"
    assert JobState.FAILED == "failed"


def test_search_config_defaults():
    config = SearchConfig()
    assert config.keywords_whitelist == []
    assert config.keywords_blacklist == []
    assert config.remote_only is True
    assert config.full_time_only is True


def test_user_profile_defaults():
    profile = UserProfile()
    assert profile.name == ""
    assert profile.skills == []
    assert profile.work_history == []
    assert profile.education == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/core/test_types.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'core'`

- [ ] **Step 3: Create core/__init__.py (empty)**

```bash
mkdir core && touch core/__init__.py
```

- [ ] **Step 4: Create core/types.py**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class JobState(str, Enum):
    SCRAPED = "scraped"
    SCORED = "scored"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    GENERATED = "generated"
    APPLIED = "applied"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass
class SearchConfig:
    keywords_whitelist: list[str] = field(default_factory=list)
    keywords_blacklist: list[str] = field(default_factory=list)
    location: str = ""
    remote_only: bool = True
    full_time_only: bool = True
    target_salary_min: Optional[int] = None
    benefits_priorities: list[str] = field(default_factory=list)


@dataclass
class UserProfile:
    name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    skills: list[str] = field(default_factory=list)
    work_history: list[dict] = field(default_factory=list)
    education: list[dict] = field(default_factory=list)
    target_salary_min: Optional[int] = None
    target_salary_max: Optional[int] = None
    target_roles: list[str] = field(default_factory=list)
    resume_path: str = ""
```

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/core/test_types.py -v
```

Expected: 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add core/ tests/__init__.py tests/core/
git commit -m "[feat] Add core types: JobState, SearchConfig, UserProfile"
```

---

### Task 4: Create db/models.py

**Files:**
- Create: `db/__init__.py`
- Create: `db/models.py`

- [ ] **Step 1: Write the failing test**

Create `tests/db/__init__.py` (empty), then create `tests/db/test_models.py`:

```python
import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

from db.models import Base, Job, Config, UserProfileModel
from core.types import JobState


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


def test_create_job(db_session):
    job = Job(
        job_key="indeed_12345",
        source="indeed",
        title="Software Engineer",
        company="Acme Corp",
        url="https://indeed.com/viewjob?jk=12345",
        state=JobState.SCRAPED,
    )
    db_session.add(job)
    db_session.commit()

    result = db_session.query(Job).filter_by(job_key="indeed_12345").first()
    assert result.title == "Software Engineer"
    assert result.state == JobState.SCRAPED
    assert result.scraped_at is not None


def test_job_url_uniqueness(db_session):
    url = "https://example.com/job1"
    db_session.add(Job(job_key="k1", source="indeed", url=url, state=JobState.SCRAPED))
    db_session.commit()
    db_session.add(Job(job_key="k2", source="indeed", url=url, state=JobState.SCRAPED))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_job_key_uniqueness(db_session):
    db_session.add(Job(job_key="dup", source="indeed", url="https://a.com/1", state=JobState.SCRAPED))
    db_session.commit()
    db_session.add(Job(job_key="dup", source="indeed", url="https://a.com/2", state=JobState.SCRAPED))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_create_and_retrieve_config(db_session):
    db_session.add(Config(key="w1", value="0.5"))
    db_session.commit()

    result = db_session.query(Config).filter_by(key="w1").first()
    assert result.value == "0.5"


def test_create_user_profile(db_session):
    data = {"name": "Matt", "skills": ["Python", "SQL"]}
    db_session.add(UserProfileModel(data=json.dumps(data)))
    db_session.commit()

    result = db_session.query(UserProfileModel).first()
    assert json.loads(result.data)["name"] == "Matt"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/db/test_models.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'db'`

- [ ] **Step 3: Create db/__init__.py (empty)**

```bash
mkdir db && touch db/__init__.py
```

- [ ] **Step 4: Create db/models.py**

```python
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True)
    job_key = Column(String, unique=True, nullable=False)
    source = Column(String, nullable=False)
    title = Column(String)
    company = Column(String)
    location = Column(String)
    salary = Column(String)
    remote = Column(Boolean)
    description = Column(Text)
    url = Column(String, unique=True, nullable=False)
    posted_at = Column(String)
    scraped_at = Column(String, default=lambda: datetime.now(timezone.utc).isoformat())
    state = Column(String, nullable=False)
    desirability_score = Column(Float)
    fit_score = Column(Float)
    final_score = Column(Float)
    score_justification = Column(Text)
    resume_path = Column(String)
    cover_path = Column(String)
    applied_at = Column(String)
    sheets_row_id = Column(String)


class Config(Base):
    __tablename__ = "config"

    key = Column(String, primary_key=True)
    value = Column(Text)


class UserProfileModel(Base):
    __tablename__ = "user_profile"

    id = Column(Integer, primary_key=True)
    data = Column(Text, nullable=False)
```

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/db/test_models.py -v
```

Expected: 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add db/__init__.py db/models.py tests/db/
git commit -m "[feat] Add SQLAlchemy ORM models: Job, Config, UserProfileModel"
```

---

### Task 5: Create db/database.py and db/seed.py

**Files:**
- Create: `db/database.py`
- Create: `db/seed.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/db/test_models.py`:

```python
from db.database import init_db, get_db, SessionLocal
from db.seed import seed_default_config, DEFAULT_CONFIG


def test_init_db_creates_tables():
    import tempfile, os
    from sqlalchemy import create_engine, inspect
    from sqlalchemy.orm import sessionmaker

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        engine = create_engine(f"sqlite:///{path}")
        Base.metadata.create_all(engine)
        inspector = inspect(engine)
        assert "jobs" in inspector.get_table_names()
        assert "config" in inspector.get_table_names()
        assert "user_profile" in inspector.get_table_names()
    finally:
        os.unlink(path)


def test_seed_default_config(db_session):
    seed_default_config(db_session)

    w1 = db_session.query(Config).filter_by(key="w1").first()
    assert w1 is not None
    assert float(w1.value) == 0.5

    reject = db_session.query(Config).filter_by(key="auto_reject_threshold").first()
    assert float(reject.value) == 0.3


def test_seed_is_idempotent(db_session):
    seed_default_config(db_session)
    seed_default_config(db_session)  # second call must not raise or duplicate

    results = db_session.query(Config).filter_by(key="w1").all()
    assert len(results) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/db/test_models.py::test_init_db_creates_tables tests/db/test_models.py::test_seed_default_config tests/db/test_models.py::test_seed_is_idempotent -v
```

Expected: FAIL — `ImportError`

- [ ] **Step 3: Create db/database.py**

```python
from __future__ import annotations

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from db.models import Base

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///auto_apply.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)


def init_db() -> None:
    """Create all tables if they do not exist."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency that yields a database session."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 4: Create db/seed.py**

```python
from __future__ import annotations

from sqlalchemy.orm import Session

from db.models import Config

DEFAULT_CONFIG: dict[str, str] = {
    "w1": "0.5",
    "w2": "0.5",
    "auto_reject_threshold": "0.3",
    "auto_approve_threshold": "0.8",
    "keywords_whitelist": "[]",
    "keywords_blacklist": "[]",
    "location": "",
    "remote_only": "true",
    "full_time_only": "true",
    "target_salary_min": "0",
    "benefits_priorities": "[]",
}


def seed_default_config(db: Session) -> None:
    """Insert default config entries if they do not already exist."""
    for key, value in DEFAULT_CONFIG.items():
        if not db.query(Config).filter_by(key=key).first():
            db.add(Config(key=key, value=value))
    db.commit()
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/db/test_models.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add db/database.py db/seed.py
git commit -m "[feat] Add database engine setup and default config seeding"
```

---

### Task 6: Smoke test — init DB and seed from command line

**Files:**
- Create: `scripts/init_db.py`
- Create: `scripts/__init__.py`

- [ ] **Step 1: Create scripts/init_db.py**

```python
"""One-time setup script: create tables and seed default config."""
from db.database import init_db, SessionLocal
from db.seed import seed_default_config

if __name__ == "__main__":
    init_db()
    db = SessionLocal()
    try:
        seed_default_config(db)
        print("Database initialised and default config seeded.")
    finally:
        db.close()
```

- [ ] **Step 2: Run the script**

```bash
python scripts/init_db.py
```

Expected output:
```
Database initialised and default config seeded.
```

Also verify `auto_apply.db` was created:

```bash
ls -lh auto_apply.db
```

Expected: file exists with non-zero size.

- [ ] **Step 3: Add auto_apply.db to .gitignore**

Open `.gitignore` and add:
```
auto_apply.db
```

- [ ] **Step 4: Run the full test suite**

```bash
pytest -v
```

Expected: all tests PASS, no warnings about missing modules.

- [ ] **Step 5: Commit**

```bash
git add scripts/ .gitignore
git commit -m "[chore] Add init_db script and exclude db file from git"
```

---

## Self-Review

**Spec coverage:**
- ✅ SQLite database with `jobs`, `config`, `user_profile` tables
- ✅ All columns from the spec's schema section
- ✅ `JobState` enum covering all state machine values
- ✅ `SearchConfig` dataclass with all fields from spec
- ✅ `UserProfile` dataclass for application context
- ✅ Default config seeding (w1, w2, thresholds, search preferences)
- ✅ `get_db()` FastAPI dependency ready for web layer

**Placeholder scan:** None found.

**Type consistency:**
- `UserProfileModel` is the SQLAlchemy model; `UserProfile` is the dataclass in `core/types.py` — these are intentionally separate. Later tasks that read from DB will deserialize `UserProfileModel.data` (JSON) into a `UserProfile` dataclass.
- `JobState` is a `str` enum so SQLAlchemy stores it as plain text without a custom type adapter.
