"""Root-level pytest configuration for auto_apply tests."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.user import User
from db.database import Base
from db.events import register_tenant_guard


@pytest.fixture(scope="session", autouse=True)
def configure_sqlalchemy_mappers():
    """Ensure SQLAlchemy mappers are fully configured before any test runs.

    Job.__new__(Job) bypasses __init__, so InstrumentedAttribute.impl is None
    unless configure_mappers() has been called first. This fixture guarantees
    that all ORM models are registered and their attribute impls are populated.
    """
    import core.job  # noqa: F401 — registers Job model
    import core.user  # noqa: F401 — registers User model
    from sqlalchemy.orm import configure_mappers

    configure_mappers()


@pytest.fixture(autouse=True)
def isolate_prompts_dir(tmp_path, monkeypatch):
    """Redirect prompt-blob persistence to a temp dir for every test.

    User hydration migrates inline prompt strings into files under
    core.user._PROMPTS_DIR (named ``{type}_{id}.md``). Without isolation, any
    test that constructs a User would write fixture junk into the real,
    version-controlled prompts/ directory. _PROMPTS_DEFAULTS_DIR is left
    pointing at the real defaults, which resolve_prompt tests rely on.
    """
    import core.user as _user_mod

    monkeypatch.setattr(_user_mod, "_PROMPTS_DIR", tmp_path / "prompts")


@pytest.fixture(autouse=True)
def disable_background_spawns(monkeypatch):
    """Neutralize fire-and-forget daemon threads spawned by web endpoints.

    Generation/edit endpoints spawn real ATS-gate/refinement threads that open
    the live SessionLocal. Left running, they linger past the test and can crash
    the interpreter at shutdown. Tests exercise those functions directly; the
    spawn itself is not under test here.
    """
    import web.routers.jobs as _jobs_mod

    monkeypatch.setattr(_jobs_mod, "_spawn", lambda *a, **k: None)


@pytest.fixture
def tenant_db():
    """In-memory DB with the tenant guard installed."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    register_tenant_guard()
    db = sessionmaker(bind=engine)()
    yield db
    db.close()


@pytest.fixture
def seed_tenant(tenant_db):
    """Factory: create a tenant (User row) and return its profile_id."""
    def _make(profile_id: int, name: str = "T") -> int:
        tenant_db.add(User(id=profile_id, name=name, data="{}"))
        tenant_db.commit()
        return profile_id
    return _make
