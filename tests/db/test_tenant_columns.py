"""Tenant-owned models must declare a profile_id column."""
from sqlalchemy import create_engine, inspect

import core.job  # noqa: F401 — register models
import core.user  # noqa: F401
from db.database import Base


def _cols(table: str) -> set[str]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    cols = {c["name"] for c in inspect(engine).get_columns(table)}
    engine.dispose()
    return cols


def test_jobs_has_profile_id():
    assert "profile_id" in _cols("jobs")


def test_documents_has_profile_id():
    assert "profile_id" in _cols("documents")


def test_skill_aliases_has_profile_id():
    assert "profile_id" in _cols("skill_aliases")
