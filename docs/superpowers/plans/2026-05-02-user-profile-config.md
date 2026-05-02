# User Profile Config Section Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the User Profile config section with support for multiple named profiles, PDF/Markdown upload-and-parse, inline editing, and an active profile radio selector.

**Architecture:** `core/profile_parser.py` owns the PDF→Markdown→JSON pipeline. Seven new API endpoints in `web/routers/config.py` handle profile CRUD, active-profile selection, and file parsing. `UserProfileModel` gains a `name` column via a lightweight SQLite migration function added to `db/database.py`. The frontend mirrors the LLM providers pattern — a row-per-profile radio selector plus a full edit form (flat fields, dynamic work-history rows, dynamic education rows) for the selected profile.

**Tech Stack:** FastAPI, SQLAlchemy, SQLite, pdfplumber, vanilla JS, pytest

---

### Task 1: Add pdfplumber dependency + DB migration

**Files:**
- Modify: `requirements.txt`
- Modify: `db/models.py`
- Modify: `db/database.py`

- [ ] **Step 1: Add pdfplumber to requirements.txt**

```text
sqlalchemy>=2.0
fastapi>=0.121
uvicorn>=0.38
httpx>=0.28
python-dotenv>=1.0
anthropic>=0.40
openai>=1.0
pdfplumber>=0.11
playwright>=1.49
playwright-stealth>=1.0
pytest>=8.0
pytest-asyncio>=0.24
```

- [ ] **Step 2: Install pdfplumber**

Run: `pip install "pdfplumber>=0.11"`

- [ ] **Step 3: Add `name` column to UserProfileModel in db/models.py**

```python
class UserProfileModel(Base):
    __tablename__ = "user_profile"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, default="Default")
    data = Column(Text, nullable=False)
```

- [ ] **Step 4: Add migration function to db/database.py**

Replace the full contents of `db/database.py`:

```python
from __future__ import annotations

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from db.models import Base

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///auto_apply.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)


def _migrate_profile_name() -> None:
    with engine.connect() as conn:
        cols = [r[1] for r in conn.execute(text("PRAGMA table_info(user_profile)")).fetchall()]
        if "name" not in cols:
            conn.execute(text("ALTER TABLE user_profile ADD COLUMN name TEXT NOT NULL DEFAULT 'Default'"))
            conn.commit()


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _migrate_profile_name()


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 5: Commit**

```bash
git add requirements.txt db/models.py db/database.py
git commit -m "[feat] Add pdfplumber dependency and profile name DB migration"
```

---

### Task 2: profile_parser.py — markdown_to_profile (TDD)

**Files:**
- Create: `core/profile_parser.py`
- Create: `tests/core/test_profile_parser.py`

- [ ] **Step 1: Create tests/core/test_profile_parser.py**

```python
import pytest
from core.profile_parser import markdown_to_profile

SAMPLE_MD = """
John Doe
john@example.com | (555) 123-4567 | New York, NY

## Skills
Python, SQL, FastAPI, Docker

## Experience
Software Engineer at Acme Corp (2022-01–2024-03)
- Built internal APIs using FastAPI.
- Reduced query time by 40%.

## Education
B.S. in Computer Science, Columbia University (2018)
GPA: 3.7
"""


def test_extracts_email():
    result = markdown_to_profile(SAMPLE_MD)
    assert result["email"] == "john@example.com"


def test_extracts_phone():
    result = markdown_to_profile(SAMPLE_MD)
    assert "555" in result["phone"]


def test_extracts_name():
    result = markdown_to_profile(SAMPLE_MD)
    assert result["name"] == "John Doe"


def test_extracts_skills():
    result = markdown_to_profile(SAMPLE_MD)
    assert "Python" in result["skills"]
    assert "SQL" in result["skills"]


def test_extracts_work_history():
    result = markdown_to_profile(SAMPLE_MD)
    assert len(result["work_history"]) == 1
    entry = result["work_history"][0]
    assert entry["title"] == "Software Engineer"
    assert entry["company"] == "Acme Corp"
    assert entry["start"] == "2022-01"
    assert entry["end"] == "2024-03"
    assert "FastAPI" in entry["summary"]


def test_extracts_education():
    result = markdown_to_profile(SAMPLE_MD)
    assert len(result["education"]) == 1
    edu = result["education"][0]
    assert edu["institution"] == "Columbia University"
    assert edu["degree"] == "B.S."
    assert edu["field"] == "Computer Science"
    assert edu["graduated"] == "2018"
    assert edu["gpa"] == pytest.approx(3.7)


def test_returns_defaults_for_missing_sections():
    result = markdown_to_profile("Jane Smith\njane@example.com")
    assert result["skills"] == []
    assert result["work_history"] == []
    assert result["education"] == []
    assert result["target_roles"] == []
    assert result["target_salary_min"] is None
    assert result["target_salary_max"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/core/test_profile_parser.py -v`
Expected: ImportError — module not found

- [ ] **Step 3: Create core/profile_parser.py with markdown_to_profile**

```python
from __future__ import annotations

import io
import re


def markdown_to_profile(md_text: str) -> dict:
    profile = {
        "name": "",
        "email": "",
        "phone": "",
        "location": "",
        "skills": [],
        "work_history": [],
        "education": [],
        "target_salary_min": None,
        "target_salary_max": None,
        "target_roles": [],
        "resume_path": "",
    }

    email_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", md_text)
    if email_match:
        profile["email"] = email_match.group()

    phone_match = re.search(r"(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}", md_text)
    if phone_match:
        profile["phone"] = phone_match.group().strip()

    for line in md_text.splitlines():
        stripped = line.strip()
        if (
            stripped
            and not stripped.startswith("#")
            and not re.search(r"[@\d|]", stripped)
            and len(stripped.split()) <= 5
        ):
            profile["name"] = stripped
            break

    sections = _split_sections(md_text)

    for key in ("skills", "technical skills", "core competencies"):
        if key in sections:
            profile["skills"] = _extract_list_items(sections[key])
            break

    for key in ("experience", "work history", "work experience", "employment"):
        if key in sections:
            profile["work_history"] = _extract_work_history(sections[key])
            break

    if "education" in sections:
        profile["education"] = _extract_education(sections["education"])

    return profile


def _split_sections(md_text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current_key: str | None = None
    current_lines: list[str] = []

    for line in md_text.splitlines():
        heading = re.match(r"^#{1,3}\s+(.+)", line)
        if heading:
            if current_key is not None:
                sections[current_key] = "\n".join(current_lines)
            current_key = heading.group(1).strip().lower()
            current_lines = []
        elif current_key is not None:
            current_lines.append(line)

    if current_key is not None:
        sections[current_key] = "\n".join(current_lines)

    return sections


def _extract_list_items(text: str) -> list[str]:
    items: list[str] = []
    for line in text.splitlines():
        line = line.strip().lstrip("-•·* ")
        if not line:
            continue
        if "," in line:
            items.extend(p.strip() for p in line.split(",") if p.strip())
        else:
            items.append(line)
    return items


def _extract_work_history(text: str) -> list[dict]:
    entries: list[dict] = []
    pattern = re.compile(
        r"^(?P<title>[^|@\n]+?)\s+at\s+(?P<company>[^(\n]+?)\s*"
        r"\((?P<start>[\w-]+)\s*[–\-]\s*(?P<end>[\w-]+)\)",
        re.MULTILINE,
    )
    matches = list(pattern.finditer(text))
    for i, m in enumerate(matches):
        summary_start = m.end()
        summary_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        summary_lines = [
            ln.strip().lstrip("-•·* ")
            for ln in text[summary_start:summary_end].splitlines()
            if ln.strip()
        ]
        entries.append({
            "title": m.group("title").strip(),
            "company": m.group("company").strip(),
            "start": m.group("start").strip(),
            "end": m.group("end").strip(),
            "summary": " ".join(summary_lines),
        })
    return entries


def _extract_education(text: str) -> list[dict]:
    entries: list[dict] = []
    degree_pattern = re.compile(
        r"(?P<degree>B\.?S\.?|B\.?A\.?|M\.?S\.?|M\.?A\.?|Ph\.?D\.?|Bachelor|Master|Associate)"
        r"[^\n,]*?(?:\s+in\s+(?P<field>[^,\n]+?))?\s*,\s*"
        r"(?P<institution>[^(\n,]+?)\s*\(?(?P<graduated>\d{4})\)?",
        re.IGNORECASE,
    )
    gpa_pattern = re.compile(r"GPA[:\s]+(\d+\.\d+)", re.IGNORECASE)
    for m in degree_pattern.finditer(text):
        window = text[m.start(): m.start() + 200]
        gpa_match = gpa_pattern.search(window)
        entries.append({
            "institution": m.group("institution").strip().rstrip(","),
            "degree": m.group("degree").strip(),
            "field": (m.group("field") or "").strip(),
            "graduated": m.group("graduated"),
            "gpa": float(gpa_match.group(1)) if gpa_match else 0.0,
        })
    return entries


def pdf_to_markdown(pdf_bytes: bytes) -> str:
    raise NotImplementedError
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/core/test_profile_parser.py -v`
Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add core/profile_parser.py tests/core/test_profile_parser.py
git commit -m "[feat] Add profile_parser.py with markdown_to_profile"
```

---

### Task 3: profile_parser.py — pdf_to_markdown (TDD)

**Files:**
- Modify: `core/profile_parser.py`
- Modify: `tests/core/test_profile_parser.py`

- [ ] **Step 1: Append failing tests for pdf_to_markdown to tests/core/test_profile_parser.py**

```python
from unittest.mock import MagicMock, patch


def _make_mock_pdf(pages_text: list):
    mock_pdf = MagicMock()
    mock_pages = []
    for text in pages_text:
        page = MagicMock()
        page.extract_text.return_value = text
        mock_pages.append(page)
    mock_pdf.pages = mock_pages
    mock_pdf.__enter__ = lambda s: s
    mock_pdf.__exit__ = MagicMock(return_value=False)
    return mock_pdf


def test_pdf_to_markdown_extracts_text():
    from core.profile_parser import pdf_to_markdown

    page_text = "EXPERIENCE\nSoftware Engineer at Acme (2022-2024)\n• Built APIs"
    mock_pdf = _make_mock_pdf([page_text])

    with patch("core.profile_parser.pdfplumber.open", return_value=mock_pdf):
        result = pdf_to_markdown(b"fake-pdf-bytes")

    assert "## Experience" in result
    assert "Software Engineer" in result
    assert "- Built APIs" in result


def test_pdf_to_markdown_handles_empty_page():
    from core.profile_parser import pdf_to_markdown

    mock_pdf = _make_mock_pdf([None])
    with patch("core.profile_parser.pdfplumber.open", return_value=mock_pdf):
        result = pdf_to_markdown(b"fake-pdf-bytes")
    assert result == ""
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/core/test_profile_parser.py::test_pdf_to_markdown_extracts_text -v`
Expected: FAILED — NotImplementedError

- [ ] **Step 3: Implement pdf_to_markdown in core/profile_parser.py**

Add `import pdfplumber` at the top of `core/profile_parser.py` (after `import re`), then replace the `pdf_to_markdown` stub:

```python
import pdfplumber


def pdf_to_markdown(pdf_bytes: bytes) -> str:
    lines: list[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.splitlines():
                stripped = line.strip()
                if not stripped:
                    lines.append("")
                    continue
                if stripped.isupper() and len(stripped) < 50:
                    lines.append(f"## {stripped.title()}")
                elif stripped.startswith(("•", "·", "-", "*")):
                    lines.append(f"- {stripped.lstrip('•·-* ')}")
                elif line.startswith("  ") and stripped:
                    lines.append(f"- {stripped}")
                else:
                    lines.append(stripped)
    return "\n".join(lines)
```

- [ ] **Step 4: Run all profile parser tests**

Run: `pytest tests/core/test_profile_parser.py -v`
Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add core/profile_parser.py tests/core/test_profile_parser.py
git commit -m "[feat] Add pdf_to_markdown to profile_parser"
```

---

### Task 4: Profile API endpoints (TDD)

**Files:**
- Modify: `web/routers/config.py`
- Create: `tests/web/test_profile_api.py`

- [ ] **Step 1: Create tests/web/test_profile_api.py**

```python
import io
import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import get_db
from db.models import Base, Config, UserProfileModel
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
    Base.metadata.drop_all(engine)


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


EMPTY_DATA = json.dumps({
    "email": "", "phone": "", "location": "", "skills": [],
    "work_history": [], "education": [], "target_salary_min": None,
    "target_salary_max": None, "target_roles": [], "resume_path": "",
})


def test_get_profiles_empty(client):
    resp = client.get("/api/config/profiles")
    assert resp.status_code == 200
    data = resp.json()
    assert data["profiles"] == []
    assert data["active_id"] is None


def test_post_profile_creates_row(client, db_session):
    resp = client.post("/api/config/profiles", json={"name": "Software Engineer"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Software Engineer"
    assert "id" in data
    assert db_session.query(UserProfileModel).count() == 1


def test_get_profile_by_id(client, db_session):
    db_session.add(UserProfileModel(name="Data Engineer", data=EMPTY_DATA))
    db_session.commit()
    row = db_session.query(UserProfileModel).first()

    resp = client.get(f"/api/config/profiles/{row.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Data Engineer"
    assert "data" in data


def test_get_profile_by_id_not_found(client):
    resp = client.get("/api/config/profiles/999")
    assert resp.status_code == 404


def test_put_profile_updates_data(client, db_session):
    db_session.add(UserProfileModel(name="Old Name", data=EMPTY_DATA))
    db_session.commit()
    row = db_session.query(UserProfileModel).first()

    body = {
        "name": "New Name",
        "data": {
            "email": "new@example.com", "phone": "", "location": "",
            "skills": ["Python"], "work_history": [], "education": [],
            "target_salary_min": None, "target_salary_max": None,
            "target_roles": [], "resume_path": "",
        },
    }
    resp = client.put(f"/api/config/profiles/{row.id}", json=body)
    assert resp.status_code == 200

    db_session.refresh(row)
    assert row.name == "New Name"
    assert json.loads(row.data)["email"] == "new@example.com"


def test_delete_profile(client, db_session):
    db_session.add(UserProfileModel(name="To Delete", data=EMPTY_DATA))
    db_session.commit()
    row = db_session.query(UserProfileModel).first()

    resp = client.delete(f"/api/config/profiles/{row.id}")
    assert resp.status_code == 204
    assert db_session.query(UserProfileModel).count() == 0


def test_put_active_sets_config(client, db_session):
    db_session.add(UserProfileModel(name="Profile A", data=EMPTY_DATA))
    db_session.commit()
    row = db_session.query(UserProfileModel).first()

    resp = client.put("/api/config/profiles/active", json={"active_id": row.id})
    assert resp.status_code == 200

    cfg = db_session.query(Config).filter_by(key="active_profile_id").first()
    assert cfg is not None
    assert int(cfg.value) == row.id


def test_parse_endpoint_md_returns_profile_dict(client, monkeypatch):
    import core.profile_parser as pp
    monkeypatch.setattr(pp, "markdown_to_profile", lambda text: {
        "name": "Test User", "email": "t@t.com", "phone": "", "location": "",
        "skills": ["Python"], "work_history": [], "education": [],
        "target_salary_min": None, "target_salary_max": None,
        "target_roles": [], "resume_path": "",
    })

    resp = client.post(
        "/api/config/profile/parse",
        files={"file": ("resume.md", io.BytesIO(b"# Test"), "text/plain")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "t@t.com"
    assert data["skills"] == ["Python"]


def test_parse_endpoint_pdf_calls_pdf_to_markdown(client, monkeypatch):
    import core.profile_parser as pp
    pdf_calls = []

    def fake_pdf_to_md(b):
        pdf_calls.append(b)
        return "# Resume"

    monkeypatch.setattr(pp, "pdf_to_markdown", fake_pdf_to_md)
    monkeypatch.setattr(pp, "markdown_to_profile", lambda t: {
        "name": "", "email": "", "phone": "", "location": "",
        "skills": [], "work_history": [], "education": [],
        "target_salary_min": None, "target_salary_max": None,
        "target_roles": [], "resume_path": "",
    })

    resp = client.post(
        "/api/config/profile/parse",
        files={"file": ("resume.pdf", io.BytesIO(b"%PDF-fake"), "application/pdf")},
    )
    assert resp.status_code == 200
    assert len(pdf_calls) == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/web/test_profile_api.py -v`
Expected: all FAILED — routes not found

- [ ] **Step 3: Add imports to web/routers/config.py**

Add these to the existing imports at the top of `web/routers/config.py`:

```python
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
import core.profile_parser as _parser
from db.models import Config, UserProfileModel
```

(Replace the existing `from fastapi import APIRouter, Depends, HTTPException` line and add the `UserProfileModel` import alongside `Config`.)

- [ ] **Step 4: Append profile endpoints to web/routers/config.py**

Append after the LLM section, before the `# ---- Init ----` comment if one exists, otherwise at the end of the file:

```python
# ---- User Profiles ----

_EMPTY_PROFILE_DATA: dict = {
    "email": "", "phone": "", "location": "", "skills": [],
    "work_history": [], "education": [], "target_salary_min": None,
    "target_salary_max": None, "target_roles": [], "resume_path": "",
}


class ProfileNameBody(BaseModel):
    name: str


class ProfileBody(BaseModel):
    name: str
    data: dict


class ActiveProfileBody(BaseModel):
    active_id: int


@router.get("/api/config/profiles")
def get_profiles(db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.query(UserProfileModel).all()
    active_raw = _get(db, "active_profile_id")
    active_id = int(active_raw) if active_raw else None
    return {
        "profiles": [{"id": r.id, "name": r.name} for r in rows],
        "active_id": active_id,
    }


@router.post("/api/config/profiles")
def create_profile(body: ProfileNameBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    row = UserProfileModel(name=body.name, data=json.dumps(_EMPTY_PROFILE_DATA))
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "name": row.name, "data": _EMPTY_PROFILE_DATA}


@router.put("/api/config/profiles/active")
def set_active_profile(body: ActiveProfileBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    _set(db, "active_profile_id", str(body.active_id))
    return {"active_id": body.active_id}


@router.get("/api/config/profiles/{profile_id}")
def get_profile(profile_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    row = db.query(UserProfileModel).filter_by(id=profile_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Profile not found")
    return {"id": row.id, "name": row.name, "data": json.loads(row.data)}


@router.put("/api/config/profiles/{profile_id}")
def update_profile(profile_id: int, body: ProfileBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    row = db.query(UserProfileModel).filter_by(id=profile_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Profile not found")
    row.name = body.name
    row.data = json.dumps(body.data)
    db.commit()
    return {"id": row.id, "name": row.name, "data": body.data}


@router.delete("/api/config/profiles/{profile_id}", status_code=204)
def delete_profile(profile_id: int, db: Session = Depends(get_db)) -> None:
    row = db.query(UserProfileModel).filter_by(id=profile_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Profile not found")
    db.delete(row)
    db.commit()


@router.post("/api/config/profile/parse")
async def parse_profile(file: UploadFile = File(...)) -> dict[str, Any]:
    contents = await file.read()
    filename = file.filename or ""
    if filename.lower().endswith(".pdf"):
        md_text = _parser.pdf_to_markdown(contents)
    else:
        md_text = contents.decode("utf-8", errors="replace")
    return _parser.markdown_to_profile(md_text)
```

**Note:** `/api/config/profiles/active` is registered before `/api/config/profiles/{profile_id}` so FastAPI does not match the literal string "active" as an integer ID.

- [ ] **Step 5: Run profile API tests**

Run: `pytest tests/web/test_profile_api.py -v`
Expected: all PASSED

- [ ] **Step 6: Run full test suite**

Run: `pytest -v`
Expected: all PASSED

- [ ] **Step 7: Commit**

```bash
git add web/routers/config.py tests/web/test_profile_api.py
git commit -m "[feat] Add user profile CRUD and parse endpoints"
```

---

### Task 5: Update scorer and seed_profile to use named/active profiles

**Files:**
- Modify: `core/scorer.py`
- Modify: `db/seed_profile.py`
- Modify: `tests/scorer/test_scorer.py`

- [ ] **Step 1: Update load_user_profile in core/scorer.py**

Replace the `load_user_profile` function:

```python
def load_user_profile(db: Session) -> UserProfile:
    active_raw = db.query(Config).filter_by(key="active_profile_id").first()
    if active_raw:
        row = db.query(UserProfileModel).filter_by(id=int(active_raw.value)).first()
    else:
        row = db.query(UserProfileModel).first()

    if not row:
        print("No user profile found. Add one via /config.", file=sys.stderr)
        sys.exit(1)

    data = json.loads(row.data)
    data["work_history"] = [WorkHistoryEntry(**e) for e in data.get("work_history", [])]
    data["education"] = [EducationEntry(**e) for e in data.get("education", [])]
    return UserProfile(**data)
```

Note: `data` from the JSON already contains the person's name (e.g. "Matt Barlow"). `row.name` is the profile label (e.g. "Software Engineer") and is not injected into `UserProfile`.

- [ ] **Step 2: Update db/seed_profile.py to set the name column**

Replace the `seed_profile` function:

```python
def seed_profile(db: Session, input_path: str) -> None:
    with open(input_path) as f:
        data = json.load(f)

    name = data.get("name", "Default")
    row = db.query(UserProfileModel).first()
    if row:
        row.name = name
        row.data = json.dumps(data)
    else:
        db.add(UserProfileModel(name=name, data=json.dumps(data)))
    db.commit()
```

Add `from db.models import UserProfileModel` to `db/seed_profile.py` imports if not already present.

- [ ] **Step 3: Update test fixtures in tests/scorer/test_scorer.py**

Add `name="Test"` to all `UserProfileModel(...)` instantiations in this file. There are three locations:

`test_seed_profile_inserts` and `test_seed_profile_upserts` call `seed_profile(db_session, str(profile_file))` — no change needed there since `seed_profile` now sets the name from the JSON.

`test_load_user_profile` — update:
```python
def test_load_user_profile(db_session):
    db_session.add(UserProfileModel(name="Test", data=json.dumps(SAMPLE_PROFILE_DICT)))
    db_session.commit()

    profile = load_user_profile(db_session)
    assert isinstance(profile, UserProfile)
    assert profile.name == "Matt Barlow"
    assert isinstance(profile.work_history[0], WorkHistoryEntry)
    assert isinstance(profile.education[0], EducationEntry)
```

`seeded_db` fixture — update:
```python
@pytest.fixture
def seeded_db(db_session):
    db_session.add(UserProfileModel(name="Test", data=json.dumps(SAMPLE_PROFILE_DICT)))
    for key, value in [("w1", "0.5"), ("w2", "0.5"), ("auto_reject_threshold", "0.3"), ("auto_approve_threshold", "0.8")]:
        db_session.add(Config(key=key, value=value))
    db_session.commit()
    return db_session
```

- [ ] **Step 4: Run full test suite**

Run: `pytest -v`
Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add core/scorer.py db/seed_profile.py tests/scorer/test_scorer.py
git commit -m "[feat] Update scorer and seed_profile for named/active profile support"
```

---

### Task 6: Frontend — User Profile section

**Files:**
- Modify: `web/static/config.html`
- Modify: `web/static/style.css`

- [ ] **Step 1: Replace the User Profile section in config.html**

Find and replace:
```html
  <!-- Section 3: User Profile (disabled) -->
  <details class="config-section config-section--disabled">
    <summary>User Profile</summary>
    <div class="config-body">
      <p class="coming-soon">Coming soon — will accept a PDF or Markdown file and convert it to a structured user profile.</p>
    </div>
  </details>
```

With:
```html
  <!-- Section 3: User Profile -->
  <details class="config-section">
    <summary>User Profile</summary>
    <div class="config-body">

      <h2>Profiles</h2>
      <div id="profile-list"></div>
      <button class="btn btn-secondary" id="btn-add-profile" type="button">+ Add User</button>

      <div id="profile-edit-form" style="display:none">
        <h2>Upload Resume</h2>
        <div class="config-row">
          <input type="file" id="profile-file" accept=".pdf,.md">
          <button class="btn btn-secondary" id="btn-parse-profile" type="button" disabled>Parse</button>
        </div>

        <h2>Details</h2>
        <label class="config-label">Name</label>
        <input class="config-input" type="text" id="profile-name">
        <label class="config-label">Email</label>
        <input class="config-input" type="text" id="profile-email">
        <label class="config-label">Phone</label>
        <input class="config-input" type="text" id="profile-phone">
        <label class="config-label">Location</label>
        <input class="config-input" type="text" id="profile-location">
        <label class="config-label">Skills (comma-separated)</label>
        <input class="config-input" type="text" id="profile-skills">

        <h2>Work History</h2>
        <div id="work-history-list"></div>
        <button class="btn btn-secondary" id="btn-add-work" type="button">+ Add Work History</button>

        <h2>Education</h2>
        <div id="education-list"></div>
        <button class="btn btn-secondary" id="btn-add-education" type="button">+ Add Education</button>

        <div class="config-actions">
          <button class="btn btn-save" id="save-profile">Save</button>
          <span class="save-status" id="status-profile"></span>
        </div>
      </div>

    </div>
  </details>
```

- [ ] **Step 2: Add User Profile JS inside the script block**

Add this section inside the `(function () {` IIFE, immediately before the `// ---- Section 4: Scoring ----` comment:

```javascript
  // ---- Section 3: User Profile ----

  let _selectedProfileId = null;

  function buildWorkRow(entry) {
    entry = entry || {};
    const row = document.createElement('div');
    row.className = 'profile-subrow';
    row.innerHTML = `
      <input type="text" class="config-input ph-title" placeholder="Title" value="${entry.title || ''}">
      <input type="text" class="config-input ph-company" placeholder="Company" value="${entry.company || ''}">
      <input type="text" class="config-input ph-start" placeholder="Start (2022-01)" value="${entry.start || ''}">
      <input type="text" class="config-input ph-end" placeholder="End (2024-03)" value="${entry.end || ''}">
      <input type="text" class="config-input ph-summary" placeholder="Summary" value="${entry.summary || ''}">
      <button class="btn-remove-llm" type="button">✕</button>
    `;
    row.querySelector('.btn-remove-llm').addEventListener('click', () => row.remove());
    return row;
  }

  function buildEducationRow(entry) {
    entry = entry || {};
    const row = document.createElement('div');
    row.className = 'profile-subrow';
    row.innerHTML = `
      <input type="text" class="config-input ph-institution" placeholder="Institution" value="${entry.institution || ''}">
      <input type="text" class="config-input ph-degree" placeholder="Degree" value="${entry.degree || ''}">
      <input type="text" class="config-input ph-field" placeholder="Field" value="${entry.field || ''}">
      <input type="text" class="config-input ph-graduated" placeholder="Graduated (2018)" value="${entry.graduated || ''}">
      <input type="text" class="config-input ph-gpa" placeholder="GPA" value="${entry.gpa || ''}">
      <button class="btn-remove-llm" type="button">✕</button>
    `;
    row.querySelector('.btn-remove-llm').addEventListener('click', () => row.remove());
    return row;
  }

  function populateEditForm(data) {
    document.getElementById('profile-name').value = data.name || '';
    document.getElementById('profile-email').value = data.email || '';
    document.getElementById('profile-phone').value = data.phone || '';
    document.getElementById('profile-location').value = data.location || '';
    document.getElementById('profile-skills').value = (data.skills || []).join(', ');

    const wl = document.getElementById('work-history-list');
    wl.innerHTML = '';
    (data.work_history || []).forEach(function(e) { wl.appendChild(buildWorkRow(e)); });

    const el = document.getElementById('education-list');
    el.innerHTML = '';
    (data.education || []).forEach(function(e) { el.appendChild(buildEducationRow(e)); });
  }

  function collectEditForm(profileLabel) {
    return {
      name: profileLabel,
      data: {
        name: document.getElementById('profile-name').value,
        email: document.getElementById('profile-email').value,
        phone: document.getElementById('profile-phone').value,
        location: document.getElementById('profile-location').value,
        skills: document.getElementById('profile-skills').value
          .split(',').map(function(s) { return s.trim(); }).filter(Boolean),
        work_history: Array.from(document.querySelectorAll('#work-history-list .profile-subrow')).map(function(r) {
          return {
            title: r.querySelector('.ph-title').value,
            company: r.querySelector('.ph-company').value,
            start: r.querySelector('.ph-start').value,
            end: r.querySelector('.ph-end').value,
            summary: r.querySelector('.ph-summary').value,
          };
        }),
        education: Array.from(document.querySelectorAll('#education-list .profile-subrow')).map(function(r) {
          return {
            institution: r.querySelector('.ph-institution').value,
            degree: r.querySelector('.ph-degree').value,
            field: r.querySelector('.ph-field').value,
            graduated: r.querySelector('.ph-graduated').value,
            gpa: parseFloat(r.querySelector('.ph-gpa').value) || 0,
          };
        }),
        target_salary_min: null,
        target_salary_max: null,
        target_roles: [],
        resume_path: '',
      },
    };
  }

  function buildProfileRow(profile, isActive) {
    const row = document.createElement('div');
    row.className = 'llm-row';
    row.dataset.id = profile.id;
    row.innerHTML = `
      <input type="radio" name="profile-active" value="${profile.id}"${isActive ? ' checked' : ''}>
      <span class="weight-label" style="flex:1;cursor:pointer">${profile.name}</span>
      <button class="btn-remove-llm" type="button">✕</button>
    `;
    row.querySelector('input[type=radio]').addEventListener('change', function() {
      selectProfile(profile.id);
    });
    row.querySelector('.weight-label').addEventListener('click', function() {
      row.querySelector('input[type=radio]').checked = true;
      selectProfile(profile.id);
    });
    row.querySelector('.btn-remove-llm').addEventListener('click', async function() {
      await fetch('/api/config/profiles/' + profile.id, { method: 'DELETE' });
      row.remove();
      if (_selectedProfileId === profile.id) {
        document.getElementById('profile-edit-form').style.display = 'none';
        _selectedProfileId = null;
      }
    });
    return row;
  }

  async function selectProfile(id) {
    _selectedProfileId = id;
    const resp = await fetch('/api/config/profiles/' + id);
    const data = await resp.json();
    populateEditForm(Object.assign({ name: data.name }, data.data));
    document.getElementById('profile-edit-form').style.display = '';
  }

  async function loadProfiles() {
    const resp = await fetch('/api/config/profiles');
    const data = await resp.json();
    const list = document.getElementById('profile-list');
    list.innerHTML = '';
    data.profiles.forEach(function(p) {
      list.appendChild(buildProfileRow(p, p.id === data.active_id));
    });
    if (data.active_id) {
      selectProfile(data.active_id);
    }
  }

  document.getElementById('btn-add-profile').addEventListener('click', async function() {
    const name = prompt('Profile name (e.g. "Software Engineer"):');
    if (!name) return;
    const resp = await fetch('/api/config/profiles', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name }),
    });
    const profile = await resp.json();
    document.getElementById('profile-list').appendChild(buildProfileRow(profile, false));
    document.querySelector('input[name="profile-active"][value="' + profile.id + '"]').checked = true;
    selectProfile(profile.id);
  });

  document.getElementById('profile-file').addEventListener('change', function(e) {
    document.getElementById('btn-parse-profile').disabled = !e.target.files.length;
  });

  document.getElementById('btn-parse-profile').addEventListener('click', async function() {
    const file = document.getElementById('profile-file').files[0];
    if (!file) return;
    const form = new FormData();
    form.append('file', file);
    try {
      const resp = await fetch('/api/config/profile/parse', { method: 'POST', body: form });
      if (!resp.ok) { showStatus('status-profile', 'Parse failed', true); return; }
      const data = await resp.json();
      populateEditForm(data);
    } catch (e) {
      showStatus('status-profile', 'Parse error', true);
    }
  });

  document.getElementById('btn-add-work').addEventListener('click', function() {
    document.getElementById('work-history-list').appendChild(buildWorkRow());
  });

  document.getElementById('btn-add-education').addEventListener('click', function() {
    document.getElementById('education-list').appendChild(buildEducationRow());
  });

  document.getElementById('save-profile').addEventListener('click', async function() {
    if (!_selectedProfileId) { showStatus('status-profile', 'Select a profile first', true); return; }
    const row = document.querySelector('#profile-list .llm-row[data-id="' + _selectedProfileId + '"]');
    const profileLabel = row ? row.querySelector('.weight-label').textContent : 'Default';
    const body = collectEditForm(profileLabel);
    const activeRadio = document.querySelector('input[name="profile-active"]:checked');
    const newActiveId = activeRadio ? parseInt(activeRadio.value) : null;

    try {
      const saves = [
        fetch('/api/config/profiles/' + _selectedProfileId, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        }),
      ];
      if (newActiveId) {
        saves.push(fetch('/api/config/profiles/active', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ active_id: newActiveId }),
        }));
      }
      const results = await Promise.all(saves);
      if (results.every(function(r) { return r.ok; })) showStatus('status-profile', 'Saved ✓', false);
      else showStatus('status-profile', 'Error saving', true);
    } catch (e) {
      showStatus('status-profile', 'Error saving', true);
    }
  });
```

- [ ] **Step 3: Update the init block**

Change:
```javascript
  Promise.all([loadApiConfig(), loadTemplates(), loadScoring(), loadLLM()]).catch(console.error);
```
To:
```javascript
  Promise.all([loadApiConfig(), loadTemplates(), loadProfiles(), loadScoring(), loadLLM()]).catch(console.error);
```

- [ ] **Step 4: Append CSS for profile sub-rows to web/static/style.css**

```css
/* Profile sub-rows (work history, education) */
.profile-subrow {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin-bottom: 0.4rem;
  flex-wrap: wrap;
}

.profile-subrow .config-input {
  flex: 1;
  min-width: 6rem;
}
```

- [ ] **Step 5: Start dev server and verify manually**

Run: `uvicorn web.main:app --reload`

Open `http://localhost:8000/config` and verify:
- User Profile section is no longer grayed out and opens cleanly
- "+ Add User" prompts for a name, creates a row in the profile list, shows the edit form
- Selecting a different profile radio loads that profile's data into the edit form
- Uploading a `.md` file and clicking Parse populates the form fields with parsed data
- Work History "+ Add Work History" adds a row; ✕ removes it
- Education "+ Add Education" adds a row; ✕ removes it
- Save persists both profile data and active selection — reload the page to confirm data survives
- Removing a profile via ✕ hides the edit form if it was selected
- All other sections (API Config, Templates, Scoring, LLM Providers) still work

- [ ] **Step 6: Run full test suite**

Run: `pytest -v`
Expected: all PASSED

- [ ] **Step 7: Commit**

```bash
git add web/static/config.html web/static/style.css
git commit -m "[feat] Implement User Profile config section with multi-profile support"
```
