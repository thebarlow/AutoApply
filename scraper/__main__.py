from __future__ import annotations

import argparse
import sys

from db.database import SessionLocal
from db.database import Config
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
