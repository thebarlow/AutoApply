"""Root-level pytest configuration for auto_apply tests."""
from __future__ import annotations

import pytest


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
