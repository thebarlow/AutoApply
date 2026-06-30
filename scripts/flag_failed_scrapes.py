"""Backfill: flag jobs whose raw description is blank as failed scrapes.

A job with a blank ``description`` was never scraped successfully, so any score
it carries is meaningless. This clears those score fields and sets the standard
error marker so the dashboard shows the warning icon.

Dry-run by default; pass ``--confirm`` to write. Defaults to the local SQLite
DB; ``--target live`` reads ``DATABASE_PUBLIC_URL`` (Postgres). Idempotent.

Usage:
    python -m scripts.flag_failed_scrapes                 # dry run, local
    python -m scripts.flag_failed_scrapes --confirm       # apply, local
    python -m scripts.flag_failed_scrapes --target live --confirm
"""
from __future__ import annotations

import argparse
import os

from sqlalchemy import Engine, create_engine, text, bindparam

_LOCAL_URL = "sqlite:///auto_apply.db"
_ERROR_MSG = "Scrape failed: empty description."


def flag_failed_scrapes(engine: Engine, *, apply: bool) -> dict:
    """Find blank-description jobs; optionally clear scores and flag them.

    Args:
        engine: SQLAlchemy engine pointed at the target DB.
        apply: When True, write changes; when False, report only.

    Returns:
        Dict with ``matched`` (count of blank-description jobs) and ``sample``
        (up to 10 affected ``job_key`` values).
    """
    # Fetch all jobs and filter in Python to match .strip() semantics exactly.
    # (SQL TRIM only strips ASCII spaces, not tabs/newlines/etc.)
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT job_key, description FROM jobs")
        ).fetchall()

    # A job is blank when description is None or strip() yields empty string.
    keys = [
        r.job_key
        for r in rows
        if not (r.description or "").strip()
    ]

    if apply and keys:
        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE jobs SET
                        desirability_score = NULL,
                        fit_score = NULL,
                        final_score = NULL,
                        score_justification = NULL,
                        unread_indicator = 'error',
                        last_result_error = :msg
                    WHERE job_key IN :keys
                    """).bindparams(
                    bindparam("keys", value=tuple(keys), expanding=True)
                ),
                {"msg": _ERROR_MSG},
            )

    return {"matched": len(keys), "sample": keys[:10]}


def _resolve_url(target: str) -> str:
    if target == "live":
        url = os.environ.get("DATABASE_PUBLIC_URL")
        if not url:
            raise SystemExit("DATABASE_PUBLIC_URL is not set; cannot target live.")
        return url
    return _LOCAL_URL


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=["local", "live"], default="local")
    parser.add_argument(
        "--confirm", action="store_true", help="Apply changes (default: dry run)."
    )
    args = parser.parse_args()

    engine = create_engine(_resolve_url(args.target))
    result = flag_failed_scrapes(engine, apply=args.confirm)

    mode = "APPLIED" if args.confirm else "DRY RUN (no changes written)"
    print(f"[{mode}] target={args.target}")
    print(f"blank-description jobs matched: {result['matched']}")
    if result["sample"]:
        print("sample job_keys: " + ", ".join(result["sample"]))


if __name__ == "__main__":
    main()
