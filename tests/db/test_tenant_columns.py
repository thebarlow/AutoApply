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


def _uniques(table: str) -> set[frozenset]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    u = {frozenset(uc["column_names"]) for uc in inspect(engine).get_unique_constraints(table)}
    engine.dispose()
    return u


def test_jobs_composite_uniques():
    u = _uniques("jobs")
    assert frozenset({"profile_id", "job_key"}) in u
    assert frozenset({"profile_id", "url"}) in u


def test_documents_composite_unique():
    assert frozenset({"profile_id", "job_key", "doc_type"}) in _uniques("documents")
