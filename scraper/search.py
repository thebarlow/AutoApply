from __future__ import annotations

from scraper.base import ScrapedJob, SearchConfig
from scraper.remoteok import RemoteOKSource
from scraper.remotive import RemotiveSource


def _identity(job: ScrapedJob) -> tuple[str, str, str]:
    """Normalized (title, company, location) key used to collapse duplicates."""
    return (
        (job.title or "").strip().lower(),
        (job.company or "").strip().lower(),
        (job.location or "").strip().lower(),
    )


def search_sources(
    query: str,
    max_jobs: int = 50,
    exclude: list[str] | None = None,
    location: str | None = None,
) -> list[ScrapedJob]:
    """Search all API job sources for a keyword and merge the results.

    Runs every source best-effort — a source that raises is skipped so a
    single failing board never blanks the whole search. Results are deduped
    both by URL and by normalized title/company/location, so the same posting
    surfacing under multiple URLs is only shown once.

    Args:
        query: Free-text keyword (e.g. "python developer").
        max_jobs: Per-source result cap.
        exclude: Banned words — any posting whose title/description contains one
            (case-insensitive) is dropped by the source.
        location: If set, keep only postings whose location contains this text
            (case-insensitive). "Worldwide"/"Anywhere" postings always pass.

    Returns:
        Deduped list of candidate jobs. Empty when query is blank.
    """
    if not query or not query.strip():
        return []

    config = SearchConfig(
        keywords_whitelist=[query.strip()],
        keywords_blacklist=[w.strip() for w in (exclude or []) if w.strip()],
    )
    loc = (location or "").strip().lower()
    seen_urls: set[str] = set()
    seen_ids: set[tuple[str, str, str]] = set()
    merged: list[ScrapedJob] = []
    for source_cls in (RemotiveSource, RemoteOKSource):
        try:
            results = source_cls().fetch(config, max_jobs)
        except Exception as exc:  # best-effort: skip a failing source
            print(f"[search] {source_cls!r} failed: {exc}", flush=True)
            continue
        for job in results:
            if not job.url or job.url in seen_urls:
                continue
            ident = _identity(job)
            if ident in seen_ids:
                continue
            if loc and not _location_matches(job.location, loc):
                continue
            seen_urls.add(job.url)
            seen_ids.add(ident)
            merged.append(job)
    return merged


def _location_matches(job_location: str, wanted: str) -> bool:
    """True if the posting's location satisfies the wanted-location filter."""
    text = (job_location or "").strip().lower()
    if not text:
        return False
    if "worldwide" in text or "anywhere" in text:
        return True
    return wanted in text
