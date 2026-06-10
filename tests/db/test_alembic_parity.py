"""Gate: the Alembic baseline must reproduce Base.metadata exactly.

Builds two SQLite databases — one via ``Base.metadata.create_all``, one via
``alembic upgrade head`` — and asserts identical tables, columns, types, and
unique constraints. If this fails, the Alembic baseline has drifted from the
ORM models and must be regenerated before later phases rely on it.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

import core.job  # noqa: F401 — register models
import core.user  # noqa: F401
from db.database import Base

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _schema_snapshot(engine) -> dict:
    """Return {table: {"columns": {name: type_str}, "unique": {frozenset(cols)}}}."""
    insp = inspect(engine)
    snapshot: dict = {}
    for table in sorted(insp.get_table_names()):
        if table == "alembic_version":
            continue  # Alembic's bookkeeping table; not part of the app schema.
        columns = {c["name"]: str(c["type"]).upper() for c in insp.get_columns(table)}
        uniques = {
            frozenset(uc["column_names"]) for uc in insp.get_unique_constraints(table)
        }
        snapshot[table] = {"columns": columns, "unique": uniques}
    return snapshot


def _create_all_snapshot(tmp_path) -> dict:
    db_path = tmp_path / "create_all.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    snap = _schema_snapshot(engine)
    engine.dispose()
    return snap


def _alembic_snapshot(tmp_path, monkeypatch) -> dict:
    db_path = tmp_path / "alembic.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    command.upgrade(cfg, "head")
    engine = create_engine(url)
    snap = _schema_snapshot(engine)
    engine.dispose()
    return snap


def test_alembic_baseline_matches_create_all(tmp_path, monkeypatch):
    expected = _create_all_snapshot(tmp_path)
    actual = _alembic_snapshot(tmp_path, monkeypatch)

    assert set(actual) == set(expected), (
        f"Table set differs. Only in Alembic: {set(actual) - set(expected)}; "
        f"only in create_all: {set(expected) - set(actual)}"
    )
    for table in expected:
        assert set(actual[table]["columns"]) == set(expected[table]["columns"]), (
            f"Column set differs for '{table}'. "
            f"Only in Alembic: {set(actual[table]['columns']) - set(expected[table]['columns'])}; "
            f"only in create_all: {set(expected[table]['columns']) - set(actual[table]['columns'])}"
        )
        assert actual[table]["unique"] == expected[table]["unique"], (
            f"Unique constraints differ for '{table}': "
            f"alembic={actual[table]['unique']} create_all={expected[table]['unique']}"
        )
