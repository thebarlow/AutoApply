"""Fetch the raw text data of the most recent N jobs from auto_apply.db.

Step 1 of the local data-processing workflow: pull job description text
straight from the DB, independent of the web app/React dashboard. There is
no raw HTML anywhere in the schema — `description` is already plain text
extracted at scrape time (scrapers and browser extension both do this
before insert) — so this is a plain read, no HTML stripping needed.

Usage:
    python -m workflows.fetch_recent_jobs --n 20
    python -m workflows.fetch_recent_jobs --n 20 --out workflows/output/recent_jobs.json
    python -m workflows.fetch_recent_jobs --job-key linkedin_123 --job-key linkedin_456
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import bindparam, create_engine, text

_LOCAL_URL = "sqlite:///auto_apply.db"
_DEFAULT_OUT = Path("workflows/output/recent_jobs.json")


def fetch_recent_jobs(engine, n: int) -> list[dict]:
    """Return the N most recently scraped jobs, newest first.

    Args:
        engine: SQLAlchemy engine pointed at the target DB.
        n: Number of jobs to fetch.

    Returns:
        List of job dicts with job_key, title, company, location, source,
        state, scraped_at, and description (raw text).
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT job_key, title, company, location, source, state,
                       scraped_at, description
                FROM jobs
                ORDER BY scraped_at DESC
                LIMIT :n
                """
            ),
            {"n": n},
        ).mappings().fetchall()
    return [dict(row) for row in rows]


def fetch_jobs_by_key(engine, job_keys: list[str]) -> list[dict]:
    """Return the given jobs by job_key, in the same order as `job_keys`."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT job_key, title, company, location, source, state,
                       scraped_at, description
                FROM jobs
                WHERE job_key IN :keys
                """
            ).bindparams(bindparam("keys", value=tuple(job_keys), expanding=True)),
        ).mappings().fetchall()
    by_key = {row["job_key"]: dict(row) for row in rows}
    return [by_key[k] for k in job_keys if k in by_key]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=20, help="Number of recent jobs to fetch.")
    parser.add_argument("--job-key", action="append", dest="job_keys", help="Fetch this specific job_key instead of the N most recent. Repeatable.")
    parser.add_argument("--out", type=Path, default=_DEFAULT_OUT, help="Output JSON path.")
    args = parser.parse_args()

    engine = create_engine(_LOCAL_URL)
    jobs = fetch_jobs_by_key(engine, args.job_keys) if args.job_keys else fetch_recent_jobs(engine, args.n)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(jobs, indent=2), encoding="utf-8")

    print(f"fetched {len(jobs)} jobs -> {args.out}")


if __name__ == "__main__":
    main()
