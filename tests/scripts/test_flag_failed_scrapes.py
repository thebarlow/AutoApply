"""Backfill clears scores + flags blank-description jobs; leaves good jobs alone."""
from sqlalchemy import create_engine, text

from scripts.flag_failed_scrapes import flag_failed_scrapes

_DDL = """
CREATE TABLE jobs (
    job_key TEXT,
    description TEXT,
    desirability_score REAL,
    fit_score REAL,
    final_score REAL,
    score_justification TEXT,
    unread_indicator TEXT,
    last_result_error TEXT
);
"""


def _seed(engine):
    with engine.begin() as c:
        c.execute(text(_DDL))
        # blank-description but scored (the bug)
        c.execute(text(
            "INSERT INTO jobs VALUES "
            "('bad', '', 0.83, 0.9, 0.83, 'looks great', 'ok', NULL)"))
        # whitespace-only
        c.execute(text(
            "INSERT INTO jobs VALUES "
            "('ws', '   ', 0.5, 0.5, 0.5, 'x', 'ok', NULL)"))
        # good job
        c.execute(text(
            "INSERT INTO jobs VALUES "
            "('good', 'Real description', 0.7, 0.7, 0.7, 'y', 'ok', NULL)"))


def test_dry_run_reports_without_writing():
    engine = create_engine("sqlite://")
    _seed(engine)
    result = flag_failed_scrapes(engine, apply=False)
    assert result["matched"] == 2
    assert set(result["sample"]) == {"bad", "ws"}
    with engine.connect() as c:
        row = c.execute(text(
            "SELECT final_score, unread_indicator FROM jobs WHERE job_key='bad'"
        )).one()
    assert row.final_score == 0.83  # unchanged in dry run


def test_apply_clears_and_flags_blank_jobs():
    engine = create_engine("sqlite://")
    _seed(engine)
    flag_failed_scrapes(engine, apply=True)
    with engine.connect() as c:
        bad = c.execute(text(
            "SELECT desirability_score, fit_score, final_score, "
            "score_justification, unread_indicator, last_result_error "
            "FROM jobs WHERE job_key='bad'")).one()
        good = c.execute(text(
            "SELECT final_score, unread_indicator FROM jobs WHERE job_key='good'"
        )).one()
    assert bad.desirability_score is None
    assert bad.fit_score is None
    assert bad.final_score is None
    assert bad.score_justification is None
    assert bad.unread_indicator == "error"
    assert bad.last_result_error == "Scrape failed: empty description."
    # good job untouched
    assert good.final_score == 0.7
    assert good.unread_indicator == "ok"


def test_idempotent():
    engine = create_engine("sqlite://")
    _seed(engine)
    flag_failed_scrapes(engine, apply=True)
    second = flag_failed_scrapes(engine, apply=False)
    assert second["matched"] == 2  # still matches by description, but nothing to change
