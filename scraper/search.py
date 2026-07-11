from __future__ import annotations

from scraper.base import ScrapedJob, SearchConfig
from scraper.remoteok import RemoteOKSource
from scraper.remotive import RemotiveSource


def search_sources(query: str, max_jobs: int = 50) -> list[ScrapedJob]:
    """Search all API job sources for a keyword and merge the results.

    Runs every source best-effort — a source that raises is skipped so a
    single failing board never blanks the whole search. Results are deduped
    by URL, keeping the first occurrence.

    Args:
        query: Free-text keyword (e.g. "python developer").
        max_jobs: Per-source result cap.

    Returns:
        Deduped list of candidate jobs. Empty when query is blank.
    """
    if not query or not query.strip():
        return []

    config = SearchConfig(keywords_whitelist=[query.strip()])
    seen: set[str] = set()
    merged: list[ScrapedJob] = []
    for source_cls in (RemotiveSource, RemoteOKSource):
        try:
            results = source_cls().fetch(config, max_jobs)
        except Exception as exc:  # best-effort: skip a failing source
            print(f"[search] {source_cls!r} failed: {exc}", flush=True)
            continue
        for job in results:
            if not job.url or job.url in seen:
                continue
            seen.add(job.url)
            merged.append(job)
    return merged
