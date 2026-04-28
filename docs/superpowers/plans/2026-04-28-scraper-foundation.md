# Scraper Foundation + API Sources Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the scraper foundation (ScrapedJob dataclass, JobSource ABC, runner, deduplication) and two API-based job sources (Remotive, RemoteOK), accessible via CLI and a POST /api/scraper/run web endpoint.

**Architecture:** `scraper/base.py` defines the data contract; `remotive.py` and `remoteok.py` implement it; `runner.py` orchestrates config loading, fetch, and DB writes; `web/routers/scraper.py` triggers a background thread; `scraper/__main__.py` provides a CLI. Sources never touch the DB — the runner owns all persistence.

**Tech Stack:** Python, httpx, SQLAlchemy, FastAPI, pytest + monkeypatch

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `db/seed.py` | Modify | Add `max_jobs_per_source` and `scraper_sources` to `DEFAULT_CONFIG` |
| `scraper/__init__.py` | Create | Package marker |
| `scraper/base.py` | Create | `ScrapedJob` dataclass + `JobSource` ABC |
| `scraper/remotive.py` | Create | `RemotiveSource` — REST API, server-side keyword search |
| `scraper/remoteok.py` | Create | `RemoteOKSource` — REST API, client-side filtering |
| `scraper/runner.py` | Create | `run_scraper`, `save_jobs`, `load_search_config`, `load_max_jobs` |
| `scraper/__main__.py` | Create | CLI: `python -m scraper [--source <id>]` |
| `web/routers/scraper.py` | Create | `POST /api/scraper/run` |
| `web/main.py` | Modify | Register scraper router |
| `tests/scraper/__init__.py` | Create | Package marker |
| `tests/scraper/test_base.py` | Create | `ScrapedJob` defaults and construction |
| `tests/scraper/test_remotive.py` | Create | Field mapping, filtering, max_jobs |
| `tests/scraper/test_remoteok.py` | Create | Field mapping, filtering, max_jobs, metadata skip |
| `tests/scraper/test_runner.py` | Create | Dedup, aggregation, error resilience, config loading |
| `tests/web/test_scraper_api.py` | Create | Web endpoint: started response, 400 cases, thread spawn |
| `tests/db/test_models.py` | Modify | Add seed tests for new config keys |

---

### Task 1: Seed scraper config keys

**Files:**
- Modify: `db/seed.py`
- Modify: `tests/db/test_models.py`

- [ ] **Step 1: Write failing tests**

Append to the bottom of `tests/db/test_models.py`:

```python
def test_scraper_config_keys_seeded(db_session):
    seed_default_config(db_session)
    row = db_session.query(Config).filter_by(key="max_jobs_per_source").first()
    assert row is not None
    assert row.value == "50"

    row2 = db_session.query(Config).filter_by(key="scraper_sources").first()
    assert row2 is not None
    assert row2.value == "remotive,remoteok"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd C:/Users/barlo/Projects/auto_apply && python -m pytest tests/db/test_models.py::test_scraper_config_keys_seeded -v
```

Expected: FAIL — `AssertionError: assert None is not None`

- [ ] **Step 3: Add keys to DEFAULT_CONFIG in db/seed.py**

Add these two entries to the `DEFAULT_CONFIG` dict (anywhere in the dict):

```python
    "max_jobs_per_source": "50",
    "scraper_sources": "remotive,remoteok",
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd C:/Users/barlo/Projects/auto_apply && python -m pytest tests/db/test_models.py::test_scraper_config_keys_seeded -v
```

Expected: PASS

- [ ] **Step 5: Run full suite**

```bash
cd C:/Users/barlo/Projects/auto_apply && python -m pytest -q
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
cd C:/Users/barlo/Projects/auto_apply && git add db/seed.py tests/db/test_models.py && git commit -m "[feat] Seed scraper config keys"
```

---

### Task 2: ScrapedJob dataclass + JobSource ABC

**Files:**
- Create: `scraper/__init__.py`
- Create: `scraper/base.py`
- Create: `tests/scraper/__init__.py`
- Create: `tests/scraper/test_base.py`

- [ ] **Step 1: Create package markers**

Create `scraper/__init__.py` (empty) and `tests/scraper/__init__.py` (empty).

- [ ] **Step 2: Write failing tests**

Create `tests/scraper/test_base.py`:

```python
import pytest

from core.types import SearchConfig
from scraper.base import JobSource, ScrapedJob


def test_scraped_job_required_fields():
    job = ScrapedJob(
        source="remotive",
        job_key="remotive_1",
        title="Python Dev",
        company="Corp",
        url="https://example.com/1",
        description="Python required.",
    )
    assert job.source == "remotive"
    assert job.job_key == "remotive_1"
    assert job.title == "Python Dev"
    assert job.company == "Corp"
    assert job.url == "https://example.com/1"
    assert job.description == "Python required."


def test_scraped_job_defaults():
    job = ScrapedJob(
        source="remotive", job_key="remotive_1", title="Dev",
        company="Corp", url="https://example.com/1", description="desc",
    )
    assert job.location == ""
    assert job.salary == ""
    assert job.remote is False
    assert job.posted_at == ""


def test_scraped_job_optional_fields():
    job = ScrapedJob(
        source="remoteok", job_key="remoteok_99", title="SWE",
        company="Acme", url="https://example.com/99", description="Go dev",
        location="Remote", salary="$120k", remote=True, posted_at="2026-01-01",
    )
    assert job.location == "Remote"
    assert job.salary == "$120k"
    assert job.remote is True
    assert job.posted_at == "2026-01-01"


def test_job_source_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        JobSource()
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd C:/Users/barlo/Projects/auto_apply && python -m pytest tests/scraper/test_base.py -v
```

Expected: ERROR — `ModuleNotFoundError: No module named 'scraper.base'`

- [ ] **Step 4: Create scraper/base.py**

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from core.types import SearchConfig


@dataclass
class ScrapedJob:
    source: str
    job_key: str
    title: str
    company: str
    url: str
    description: str
    location: str = ""
    salary: str = ""
    remote: bool = False
    posted_at: str = ""


class JobSource(ABC):
    @property
    @abstractmethod
    def source_id(self) -> str: ...

    @abstractmethod
    def fetch(self, config: SearchConfig, max_jobs: int) -> list[ScrapedJob]: ...
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd C:/Users/barlo/Projects/auto_apply && python -m pytest tests/scraper/test_base.py -v
```

Expected: 4 PASS

- [ ] **Step 6: Run full suite**

```bash
cd C:/Users/barlo/Projects/auto_apply && python -m pytest -q
```

Expected: all pass

- [ ] **Step 7: Commit**

```bash
cd C:/Users/barlo/Projects/auto_apply && git add scraper/__init__.py scraper/base.py tests/scraper/__init__.py tests/scraper/test_base.py && git commit -m "[feat] Add ScrapedJob dataclass and JobSource ABC"
```

---

### Task 3: RemotiveSource

**Files:**
- Create: `scraper/remotive.py`
- Create: `tests/scraper/test_remotive.py`

- [ ] **Step 1: Write failing tests**

Create `tests/scraper/test_remotive.py`:

```python
import pytest
from unittest.mock import MagicMock, patch

from core.types import SearchConfig
from scraper.remotive import RemotiveSource


def _config(**kwargs) -> SearchConfig:
    defaults = dict(
        keywords_whitelist=[], keywords_blacklist=[],
        location="", remote_only=True, full_time_only=True,
    )
    defaults.update(kwargs)
    return SearchConfig(**defaults)


def _mock_response(jobs: list[dict]) -> MagicMock:
    m = MagicMock()
    m.json.return_value = {"jobs": jobs}
    m.raise_for_status.return_value = None
    return m


def _api_job(
    id=1, title="Python Dev", company="Corp",
    url="https://remotive.com/remote-jobs/1",
    description="Python required.",
    location="Worldwide", salary="$100k–$120k",
    publication_date="2026-01-15",
) -> dict:
    return dict(
        id=id, title=title, company_name=company, url=url,
        description=description, candidate_required_location=location,
        salary=salary, publication_date=publication_date,
    )


def test_remotive_source_id():
    assert RemotiveSource().source_id == "remotive"


def test_remotive_maps_fields_correctly():
    with patch("scraper.remotive.httpx.get", return_value=_mock_response([_api_job()])):
        results = RemotiveSource().fetch(_config(), max_jobs=10)

    assert len(results) == 1
    job = results[0]
    assert job.source == "remotive"
    assert job.job_key == "remotive_1"
    assert job.title == "Python Dev"
    assert job.company == "Corp"
    assert job.url == "https://remotive.com/remote-jobs/1"
    assert job.description == "Python required."
    assert job.location == "Worldwide"
    assert job.salary == "$100k–$120k"
    assert job.remote is True
    assert job.posted_at == "2026-01-15"


def test_remotive_filters_blacklist_in_title():
    jobs = [
        _api_job(id=1, title="Senior Python Dev", url="https://remotive.com/remote-jobs/1"),
        _api_job(id=2, title="Python Dev", url="https://remotive.com/remote-jobs/2"),
    ]
    with patch("scraper.remotive.httpx.get", return_value=_mock_response(jobs)):
        results = RemotiveSource().fetch(_config(keywords_blacklist=["senior"]), max_jobs=10)

    assert len(results) == 1
    assert results[0].job_key == "remotive_2"


def test_remotive_filters_blacklist_in_description():
    jobs = [
        _api_job(id=1, description="Must have 10+ years senior experience.", url="https://remotive.com/remote-jobs/1"),
        _api_job(id=2, description="Junior Python role.", url="https://remotive.com/remote-jobs/2"),
    ]
    with patch("scraper.remotive.httpx.get", return_value=_mock_response(jobs)):
        results = RemotiveSource().fetch(_config(keywords_blacklist=["senior"]), max_jobs=10)

    assert len(results) == 1
    assert results[0].job_key == "remotive_2"


def test_remotive_sends_first_whitelist_keyword():
    with patch("scraper.remotive.httpx.get", return_value=_mock_response([])) as mock_get:
        RemotiveSource().fetch(_config(keywords_whitelist=["python", "django"]), max_jobs=10)

    params = mock_get.call_args[1]["params"]
    assert params["search"] == "python"


def test_remotive_sends_empty_search_when_no_whitelist():
    with patch("scraper.remotive.httpx.get", return_value=_mock_response([])) as mock_get:
        RemotiveSource().fetch(_config(keywords_whitelist=[]), max_jobs=5)

    params = mock_get.call_args[1]["params"]
    assert params["search"] == ""
    assert params["limit"] == 5


def test_remotive_skips_jobs_without_url():
    jobs = [
        dict(id=1, title="Dev", company_name="Corp", url="", description="desc",
             candidate_required_location="", salary="", publication_date=""),
        _api_job(id=2, url="https://remotive.com/remote-jobs/2"),
    ]
    with patch("scraper.remotive.httpx.get", return_value=_mock_response(jobs)):
        results = RemotiveSource().fetch(_config(), max_jobs=10)

    assert len(results) == 1
    assert results[0].job_key == "remotive_2"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd C:/Users/barlo/Projects/auto_apply && python -m pytest tests/scraper/test_remotive.py -v
```

Expected: ERROR — `ModuleNotFoundError: No module named 'scraper.remotive'`

- [ ] **Step 3: Create scraper/remotive.py**

```python
from __future__ import annotations

import warnings

import httpx

from core.types import SearchConfig
from scraper.base import JobSource, ScrapedJob

_BASE_URL = "https://remotive.com/api/remote-jobs"


class RemotiveSource(JobSource):
    @property
    def source_id(self) -> str:
        return "remotive"

    def fetch(self, config: SearchConfig, max_jobs: int) -> list[ScrapedJob]:
        keyword = config.keywords_whitelist[0] if config.keywords_whitelist else ""
        response = httpx.get(
            _BASE_URL,
            params={"search": keyword, "limit": max_jobs},
            timeout=30,
        )
        response.raise_for_status()

        blacklist = [term.lower() for term in config.keywords_blacklist]
        results: list[ScrapedJob] = []

        for job in response.json().get("jobs", []):
            url = job.get("url", "")
            if not url:
                continue

            title = job.get("title", "")
            description = job.get("description", "")
            text = (title + " " + description).lower()

            if blacklist and any(term in text for term in blacklist):
                continue

            results.append(ScrapedJob(
                source=self.source_id,
                job_key=f"remotive_{job.get('id', '')}",
                title=title,
                company=job.get("company_name", ""),
                url=url,
                description=description,
                location=job.get("candidate_required_location", ""),
                salary=job.get("salary", "") or "",
                remote=True,
                posted_at=job.get("publication_date", ""),
            ))

        return results
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd C:/Users/barlo/Projects/auto_apply && python -m pytest tests/scraper/test_remotive.py -v
```

Expected: 7 PASS

- [ ] **Step 5: Run full suite**

```bash
cd C:/Users/barlo/Projects/auto_apply && python -m pytest -q
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
cd C:/Users/barlo/Projects/auto_apply && git add scraper/remotive.py tests/scraper/test_remotive.py && git commit -m "[feat] Add RemotiveSource"
```

---

### Task 4: RemoteOKSource

**Files:**
- Create: `scraper/remoteok.py`
- Create: `tests/scraper/test_remoteok.py`

- [ ] **Step 1: Write failing tests**

Create `tests/scraper/test_remoteok.py`:

```python
import pytest
from unittest.mock import MagicMock, patch

from core.types import SearchConfig
from scraper.remoteok import RemoteOKSource


def _config(**kwargs) -> SearchConfig:
    defaults = dict(
        keywords_whitelist=[], keywords_blacklist=[],
        location="", remote_only=True, full_time_only=True,
    )
    defaults.update(kwargs)
    return SearchConfig(**defaults)


def _mock_response(jobs: list[dict]) -> MagicMock:
    m = MagicMock()
    # First element is always a metadata object (no "id" key)
    m.json.return_value = [{"legal": "RemoteOK API"}] + jobs
    m.raise_for_status.return_value = None
    return m


def _api_job(
    id="123", position="Python Dev", company="Corp",
    url="https://remoteok.com/remote-jobs/123",
    description="Python required.",
    location="Remote", date="2026-01-15T00:00:00Z",
) -> dict:
    return dict(
        id=id, position=position, company=company, url=url,
        description=description, location=location, date=date,
    )


def test_remoteok_source_id():
    assert RemoteOKSource().source_id == "remoteok"


def test_remoteok_maps_fields_correctly():
    with patch("scraper.remoteok.httpx.get", return_value=_mock_response([_api_job()])):
        results = RemoteOKSource().fetch(_config(), max_jobs=10)

    assert len(results) == 1
    job = results[0]
    assert job.source == "remoteok"
    assert job.job_key == "remoteok_123"
    assert job.title == "Python Dev"
    assert job.company == "Corp"
    assert job.url == "https://remoteok.com/remote-jobs/123"
    assert job.description == "Python required."
    assert job.location == "Remote"
    assert job.remote is True
    assert job.posted_at == "2026-01-15T00:00:00Z"


def test_remoteok_skips_metadata_element():
    # Metadata dict has no "id" key — must be skipped
    raw = MagicMock()
    raw.raise_for_status.return_value = None
    raw.json.return_value = [
        {"legal": "metadata, no id key"},
        _api_job(id="1", url="https://remoteok.com/remote-jobs/1"),
    ]
    with patch("scraper.remoteok.httpx.get", return_value=raw):
        results = RemoteOKSource().fetch(_config(), max_jobs=10)

    assert len(results) == 1
    assert results[0].job_key == "remoteok_1"


def test_remoteok_filters_by_whitelist():
    jobs = [
        _api_job(id="1", position="Python Dev", url="https://remoteok.com/remote-jobs/1"),
        _api_job(id="2", position="Java Engineer", url="https://remoteok.com/remote-jobs/2"),
    ]
    with patch("scraper.remoteok.httpx.get", return_value=_mock_response(jobs)):
        results = RemoteOKSource().fetch(_config(keywords_whitelist=["python"]), max_jobs=10)

    assert len(results) == 1
    assert results[0].job_key == "remoteok_1"


def test_remoteok_no_whitelist_keeps_all():
    jobs = [
        _api_job(id="1", url="https://remoteok.com/remote-jobs/1"),
        _api_job(id="2", url="https://remoteok.com/remote-jobs/2"),
    ]
    with patch("scraper.remoteok.httpx.get", return_value=_mock_response(jobs)):
        results = RemoteOKSource().fetch(_config(keywords_whitelist=[]), max_jobs=10)

    assert len(results) == 2


def test_remoteok_filters_blacklist_terms():
    jobs = [
        _api_job(id="1", position="Senior Python Dev", url="https://remoteok.com/remote-jobs/1"),
        _api_job(id="2", position="Python Dev", url="https://remoteok.com/remote-jobs/2"),
    ]
    with patch("scraper.remoteok.httpx.get", return_value=_mock_response(jobs)):
        results = RemoteOKSource().fetch(_config(keywords_blacklist=["senior"]), max_jobs=10)

    assert len(results) == 1
    assert results[0].job_key == "remoteok_2"


def test_remoteok_respects_max_jobs():
    jobs = [_api_job(id=str(i), url=f"https://remoteok.com/remote-jobs/{i}") for i in range(10)]
    with patch("scraper.remoteok.httpx.get", return_value=_mock_response(jobs)):
        results = RemoteOKSource().fetch(_config(), max_jobs=3)

    assert len(results) == 3


def test_remoteok_skips_jobs_without_url():
    jobs = [
        dict(id="1", position="Dev", company="Corp", url="",
             description="desc", location="", date=""),
        _api_job(id="2", url="https://remoteok.com/remote-jobs/2"),
    ]
    with patch("scraper.remoteok.httpx.get", return_value=_mock_response(jobs)):
        results = RemoteOKSource().fetch(_config(), max_jobs=10)

    assert len(results) == 1
    assert results[0].job_key == "remoteok_2"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd C:/Users/barlo/Projects/auto_apply && python -m pytest tests/scraper/test_remoteok.py -v
```

Expected: ERROR — `ModuleNotFoundError: No module named 'scraper.remoteok'`

- [ ] **Step 3: Create scraper/remoteok.py**

```python
from __future__ import annotations

import httpx

from core.types import SearchConfig
from scraper.base import JobSource, ScrapedJob

_BASE_URL = "https://remoteok.com/api"


class RemoteOKSource(JobSource):
    @property
    def source_id(self) -> str:
        return "remoteok"

    def fetch(self, config: SearchConfig, max_jobs: int) -> list[ScrapedJob]:
        response = httpx.get(
            _BASE_URL,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=30,
        )
        response.raise_for_status()

        whitelist = [term.lower() for term in config.keywords_whitelist]
        blacklist = [term.lower() for term in config.keywords_blacklist]

        # Skip first element (metadata object has no "id" key)
        raw_jobs = [item for item in response.json() if isinstance(item, dict) and "id" in item]

        results: list[ScrapedJob] = []
        for job in raw_jobs:
            url = job.get("url", "")
            if not url:
                continue

            title = job.get("position", "")
            description = job.get("description", "") or ""
            text = (title + " " + description).lower()

            if whitelist and not any(term in text for term in whitelist):
                continue
            if blacklist and any(term in text for term in blacklist):
                continue

            results.append(ScrapedJob(
                source=self.source_id,
                job_key=f"remoteok_{job.get('id', '')}",
                title=title,
                company=job.get("company", ""),
                url=url,
                description=description,
                location=job.get("location", "") or "",
                remote=True,
                posted_at=job.get("date", ""),
            ))

            if len(results) >= max_jobs:
                break

        return results
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd C:/Users/barlo/Projects/auto_apply && python -m pytest tests/scraper/test_remoteok.py -v
```

Expected: 8 PASS

- [ ] **Step 5: Run full suite**

```bash
cd C:/Users/barlo/Projects/auto_apply && python -m pytest -q
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
cd C:/Users/barlo/Projects/auto_apply && git add scraper/remoteok.py tests/scraper/test_remoteok.py && git commit -m "[feat] Add RemoteOKSource"
```

---

### Task 5: Runner

**Files:**
- Create: `scraper/runner.py`
- Create: `tests/scraper/test_runner.py`

- [ ] **Step 1: Write failing tests**

Create `tests/scraper/test_runner.py`:

```python
import json
import warnings

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.types import JobState, SearchConfig
from db.models import Base, Config, Job
from scraper.base import JobSource, ScrapedJob
from scraper.runner import (
    load_max_jobs,
    load_search_config,
    run_scraper,
    save_jobs,
)


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


def _scraped(n: int = 1) -> ScrapedJob:
    return ScrapedJob(
        source="remotive",
        job_key=f"remotive_{n}",
        title="Python Dev",
        company="Corp",
        url=f"https://example.com/job/{n}",
        description="desc",
        remote=True,
    )


class _MockSource(JobSource):
    def __init__(self, source_id: str, jobs: list[ScrapedJob]):
        self._id = source_id
        self._jobs = jobs

    @property
    def source_id(self) -> str:
        return self._id

    def fetch(self, config: SearchConfig, max_jobs: int) -> list[ScrapedJob]:
        return self._jobs


class _FailingSource(JobSource):
    @property
    def source_id(self) -> str:
        return "failing"

    def fetch(self, config: SearchConfig, max_jobs: int) -> list[ScrapedJob]:
        raise RuntimeError("network error")


# --- save_jobs ---

def test_save_jobs_inserts_new_jobs(db_session):
    count = save_jobs(db_session, [_scraped(1), _scraped(2)])
    assert count == 2
    assert db_session.query(Job).count() == 2


def test_save_jobs_deduplicates_by_url(db_session):
    save_jobs(db_session, [_scraped(1)])
    count = save_jobs(db_session, [_scraped(1), _scraped(2)])
    assert count == 1
    assert db_session.query(Job).count() == 2


def test_save_jobs_sets_scraped_state(db_session):
    save_jobs(db_session, [_scraped(1)])
    job = db_session.query(Job).first()
    assert job.state == JobState.SCRAPED.value


def test_save_jobs_maps_all_fields(db_session):
    scraped = ScrapedJob(
        source="remotive", job_key="remotive_42", title="SWE",
        company="Acme", url="https://example.com/42",
        description="Python expert", location="Remote",
        salary="$120k", remote=True, posted_at="2026-01-01",
    )
    save_jobs(db_session, [scraped])
    job = db_session.query(Job).first()
    assert job.job_key == "remotive_42"
    assert job.source == "remotive"
    assert job.title == "SWE"
    assert job.company == "Acme"
    assert job.location == "Remote"
    assert job.salary == "$120k"
    assert job.remote is True
    assert job.posted_at == "2026-01-01"


# --- run_scraper ---

def test_run_scraper_aggregates_sources(db_session):
    sources = [
        _MockSource("remotive", [_scraped(1), _scraped(2)]),
        _MockSource("remoteok", [_scraped(3)]),
    ]
    count = run_scraper(db_session, sources)
    assert count == 3
    assert db_session.query(Job).count() == 3


def test_run_scraper_continues_on_source_error(db_session):
    sources = [_FailingSource(), _MockSource("remoteok", [_scraped(1)])]
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        count = run_scraper(db_session, sources)
    assert count == 1
    assert any("failing" in str(w.message) for w in caught)


# --- load_search_config ---

def test_load_search_config_from_db(db_session):
    db_session.add(Config(key="keywords_whitelist", value='["python", "django"]'))
    db_session.add(Config(key="keywords_blacklist", value='["senior"]'))
    db_session.add(Config(key="remote_only", value="true"))
    db_session.add(Config(key="full_time_only", value="false"))
    db_session.add(Config(key="location", value="New York"))
    db_session.add(Config(key="benefits_priorities", value='["401k"]'))
    db_session.commit()

    config = load_search_config(db_session)
    assert config.keywords_whitelist == ["python", "django"]
    assert config.keywords_blacklist == ["senior"]
    assert config.remote_only is True
    assert config.full_time_only is False
    assert config.location == "New York"
    assert config.benefits_priorities == ["401k"]


def test_load_search_config_uses_defaults_when_missing(db_session):
    config = load_search_config(db_session)
    assert config.keywords_whitelist == []
    assert config.keywords_blacklist == []
    assert config.remote_only is True


# --- load_max_jobs ---

def test_load_max_jobs_defaults_to_50(db_session):
    assert load_max_jobs(db_session) == 50


def test_load_max_jobs_from_db(db_session):
    db_session.add(Config(key="max_jobs_per_source", value="25"))
    db_session.commit()
    assert load_max_jobs(db_session) == 25
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd C:/Users/barlo/Projects/auto_apply && python -m pytest tests/scraper/test_runner.py -v
```

Expected: ERROR — `ModuleNotFoundError: No module named 'scraper.runner'`

- [ ] **Step 3: Create scraper/runner.py**

```python
from __future__ import annotations

import json
import warnings

from sqlalchemy.orm import Session

from core.types import JobState, SearchConfig
from db.models import Config, Job
from scraper.base import JobSource, ScrapedJob


def load_search_config(db: Session) -> SearchConfig:
    def _get(key: str, default: str = "") -> str:
        row = db.query(Config).filter_by(key=key).first()
        return row.value if row else default

    raw_salary = _get("target_salary_min", "0")
    try:
        salary_min = int(raw_salary) or None
    except (ValueError, TypeError):
        salary_min = None

    return SearchConfig(
        keywords_whitelist=json.loads(_get("keywords_whitelist", "[]")),
        keywords_blacklist=json.loads(_get("keywords_blacklist", "[]")),
        location=_get("location", ""),
        remote_only=_get("remote_only", "true").lower() == "true",
        full_time_only=_get("full_time_only", "true").lower() == "true",
        target_salary_min=salary_min,
        benefits_priorities=json.loads(_get("benefits_priorities", "[]")),
    )


def load_max_jobs(db: Session) -> int:
    row = db.query(Config).filter_by(key="max_jobs_per_source").first()
    if row:
        try:
            return int(row.value)
        except (ValueError, TypeError):
            pass
    return 50


def save_jobs(db: Session, jobs: list[ScrapedJob]) -> int:
    count = 0
    for scraped in jobs:
        if db.query(Job).filter_by(url=scraped.url).first():
            continue
        db.add(Job(
            job_key=scraped.job_key,
            source=scraped.source,
            title=scraped.title,
            company=scraped.company,
            url=scraped.url,
            description=scraped.description,
            location=scraped.location,
            salary=scraped.salary,
            remote=scraped.remote,
            posted_at=scraped.posted_at,
            state=JobState.SCRAPED.value,
        ))
        count += 1
    db.commit()
    return count


def run_scraper(db: Session, sources: list[JobSource]) -> int:
    config = load_search_config(db)
    max_jobs = load_max_jobs(db)

    all_jobs: list[ScrapedJob] = []
    for source in sources:
        try:
            jobs = source.fetch(config, max_jobs)
            print(f"[scraper] {source.source_id}: fetched {len(jobs)} jobs")
            all_jobs.extend(jobs)
        except Exception as e:
            warnings.warn(f"[scraper] {source.source_id} failed: {e}")

    new_count = save_jobs(db, all_jobs)
    print(f"[scraper] saved {new_count} new jobs (skipped {len(all_jobs) - new_count} duplicates)")
    return new_count
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd C:/Users/barlo/Projects/auto_apply && python -m pytest tests/scraper/test_runner.py -v
```

Expected: 11 PASS

- [ ] **Step 5: Run full suite**

```bash
cd C:/Users/barlo/Projects/auto_apply && python -m pytest -q
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
cd C:/Users/barlo/Projects/auto_apply && git add scraper/runner.py tests/scraper/test_runner.py && git commit -m "[feat] Add scraper runner with dedup and config loading"
```

---

### Task 6: CLI entrypoint

**Files:**
- Create: `scraper/__main__.py`

No automated tests for the CLI entrypoint itself — the underlying functions are fully tested. The CLI is verified manually.

- [ ] **Step 1: Create scraper/__main__.py**

```python
from __future__ import annotations

import argparse
import sys

from db.database import SessionLocal
from db.models import Config
from scraper.remotive import RemotiveSource
from scraper.remoteok import RemoteOKSource
from scraper.runner import run_scraper

_SOURCES = {
    "remotive": RemotiveSource,
    "remoteok": RemoteOKSource,
}


def _enabled_from_config(db) -> list[str]:
    row = db.query(Config).filter_by(key="scraper_sources").first()
    if not row or not row.value.strip():
        return list(_SOURCES.keys())
    return [s.strip() for s in row.value.split(",") if s.strip() in _SOURCES]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run job scrapers.")
    parser.add_argument(
        "--source", action="append", dest="sources", metavar="SOURCE",
        help="Source to run (remotive, remoteok). Repeatable. Defaults to all enabled sources.",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.sources:
            unknown = [s for s in args.sources if s not in _SOURCES]
            if unknown:
                print(f"Unknown source(s): {', '.join(unknown)}", file=sys.stderr)
                sys.exit(1)
            source_ids = args.sources
        else:
            source_ids = _enabled_from_config(db)

        if not source_ids:
            print("No sources configured. Set 'scraper_sources' in the config table.", file=sys.stderr)
            sys.exit(1)

        sources = [_SOURCES[sid]() for sid in source_ids]
        print(f"[scraper] running: {', '.join(source_ids)}")
        total = run_scraper(db, sources)
        print(f"[scraper] done. {total} new jobs saved.")
    finally:
        db.close()
```

- [ ] **Step 2: Verify import works**

```bash
cd C:/Users/barlo/Projects/auto_apply && python -c "import scraper.__main__"
```

Expected: no output (import succeeds without running the CLI)

- [ ] **Step 3: Run full suite**

```bash
cd C:/Users/barlo/Projects/auto_apply && python -m pytest -q
```

Expected: all pass

- [ ] **Step 4: Commit**

```bash
cd C:/Users/barlo/Projects/auto_apply && git add scraper/__main__.py && git commit -m "[feat] Add scraper CLI entrypoint"
```

---

### Task 7: Web endpoint + router registration

**Files:**
- Create: `web/routers/scraper.py`
- Modify: `web/main.py`
- Create: `tests/web/test_scraper_api.py`

- [ ] **Step 1: Write failing tests**

Create `tests/web/test_scraper_api.py`:

```python
import types

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import get_db
from db.models import Base, Config
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


def _seed_sources(db_session, value: str = "remotive,remoteok") -> None:
    db_session.add(Config(key="scraper_sources", value=value))
    db_session.commit()


def test_trigger_scrape_returns_started(client, db_session, monkeypatch):
    import web.routers.scraper as scraper_router
    _seed_sources(db_session)

    spawned = []

    class MockThread:
        def __init__(self, **kwargs):
            spawned.append(kwargs)

        def start(self):
            pass

    monkeypatch.setattr(
        scraper_router, "threading",
        types.SimpleNamespace(Thread=MockThread),
        raising=False,
    )

    resp = client.post("/api/scraper/run")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "started"
    assert set(data["sources"]) == {"remotive", "remoteok"}
    assert len(spawned) == 1


def test_trigger_scrape_returns_400_when_no_config_key(client, db_session):
    resp = client.post("/api/scraper/run")
    assert resp.status_code == 400


def test_trigger_scrape_returns_400_when_sources_empty(client, db_session):
    _seed_sources(db_session, value="")
    resp = client.post("/api/scraper/run")
    assert resp.status_code == 400


def test_trigger_scrape_ignores_unknown_source_ids(client, db_session, monkeypatch):
    import web.routers.scraper as scraper_router
    _seed_sources(db_session, value="remotive,nonexistent")

    spawned = []

    class MockThread:
        def __init__(self, **kwargs):
            spawned.append(kwargs)

        def start(self):
            pass

    monkeypatch.setattr(
        scraper_router, "threading",
        types.SimpleNamespace(Thread=MockThread),
        raising=False,
    )

    resp = client.post("/api/scraper/run")
    assert resp.status_code == 200
    assert resp.json()["sources"] == ["remotive"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd C:/Users/barlo/Projects/auto_apply && python -m pytest tests/web/test_scraper_api.py -v
```

Expected: ERROR — `404 Not Found` (route not registered yet)

- [ ] **Step 3: Create web/routers/scraper.py**

```python
from __future__ import annotations

import threading
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.database import SessionLocal, get_db
from db.models import Config
from scraper.remotive import RemotiveSource
from scraper.remoteok import RemoteOKSource
from scraper.runner import run_scraper

router = APIRouter(prefix="/api/scraper")

_SOURCES = {
    "remotive": RemotiveSource,
    "remoteok": RemoteOKSource,
}


def _get_enabled_source_ids(db: Session) -> list[str]:
    row = db.query(Config).filter_by(key="scraper_sources").first()
    if not row or not row.value.strip():
        return []
    return [s.strip() for s in row.value.split(",") if s.strip() in _SOURCES]


def _run_in_background(source_ids: list[str]) -> None:
    db = SessionLocal()
    try:
        sources = [_SOURCES[sid]() for sid in source_ids]
        run_scraper(db, sources)
    finally:
        db.close()


@router.post("/run")
def trigger_scrape(db: Session = Depends(get_db)) -> dict[str, Any]:
    source_ids = _get_enabled_source_ids(db)

    if not source_ids:
        raise HTTPException(
            status_code=400,
            detail="No enabled sources configured. Set 'scraper_sources' in the config table.",
        )

    t = threading.Thread(target=_run_in_background, args=(source_ids,), daemon=True)
    t.start()
    return {"status": "started", "sources": source_ids}
```

- [ ] **Step 4: Register scraper router in web/main.py**

Replace the full contents of `web/main.py`:

```python
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from web.routers import jobs
from web.routers import scraper

app = FastAPI(title="Auto Apply")

_STATIC = Path(__file__).parent / "static"

app.include_router(jobs.router)
app.include_router(scraper.router)
app.mount("/static", StaticFiles(directory=_STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(_STATIC / "index.html")
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd C:/Users/barlo/Projects/auto_apply && python -m pytest tests/web/test_scraper_api.py -v
```

Expected: 4 PASS

- [ ] **Step 6: Run full suite**

```bash
cd C:/Users/barlo/Projects/auto_apply && python -m pytest -q
```

Expected: all pass

- [ ] **Step 7: Commit**

```bash
cd C:/Users/barlo/Projects/auto_apply && git add web/routers/scraper.py web/main.py tests/web/test_scraper_api.py && git commit -m "[feat] Add scraper web endpoint and register router"
```

---

## Self-Review

**Spec coverage:**
- ✅ `ScrapedJob` dataclass with all fields and defaults — Task 2
- ✅ `JobSource` ABC with `source_id` and `fetch` — Task 2
- ✅ `RemotiveSource`: server-side keyword search, client-side blacklist, field mapping, URL skip — Task 3
- ✅ `RemoteOKSource`: all-jobs endpoint, whitelist + blacklist filter, max_jobs cap, metadata skip, URL skip — Task 4
- ✅ `load_search_config` reads all config keys including `target_salary_min` and `benefits_priorities` — Task 5
- ✅ `load_max_jobs` defaults to 50 — Task 5
- ✅ `save_jobs` deduplicates by URL, sets `scraped` state, maps all fields — Task 5
- ✅ `run_scraper` continues on source error, logs per-source counts — Task 5
- ✅ CLI: `python -m scraper [--source <id>]`, defaults to config, exits on unknown source — Task 6
- ✅ `POST /api/scraper/run`: async thread, returns `{status, sources}`, 400 on missing/empty config — Task 7
- ✅ `scraper_sources` and `max_jobs_per_source` seeded in `db/seed.py` — Task 1
- ✅ Scraper router registered in `web/main.py` — Task 7

**Placeholder scan:** None found.

**Type consistency:**
- `save_jobs(db: Session, jobs: list[ScrapedJob]) -> int` — consistent across Task 5 impl and test
- `run_scraper(db: Session, sources: list[JobSource]) -> int` — consistent
- `load_search_config(db: Session) -> SearchConfig` — consistent
- `load_max_jobs(db: Session) -> int` — consistent
- `JobSource.fetch(config: SearchConfig, max_jobs: int) -> list[ScrapedJob]` — consistent across ABC (Task 2), sources (Tasks 3–4), mock in tests (Task 5)
- `_get_enabled_source_ids` in web router returns `list[str]` filtered to known keys — consistent with `_SOURCES` dict
