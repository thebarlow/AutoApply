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
