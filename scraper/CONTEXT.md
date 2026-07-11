# Scraper Context

API-based job scrapers for Remotive and RemoteOK. Now **live and UI-triggered** via the "Find Jobs" tab (`react-dashboard/src/components/FindJobs.jsx`): `scraper/search.py::search_sources(query, max_jobs=50)` runs both sources best-effort and merges/dedupes results by URL. `POST /api/scraper/search` (`web/routers/scraper.py`) previews candidates (no DB persist); the user multi-selects and `POST /api/scraper/scrape-selected` persists the chosen jobs and runs the intake pipeline. The old dormant `POST /api/scraper/run` endpoint and the `scraper_sources` config gate were removed.

## Architecture

```
scraper/
├── __init__.py     # empty package marker
├── base.py         # JobSource ABC, ScrapedJob dataclass
├── remotive.py     # Remotive API scraper
├── remoteok.py     # RemoteOK API scraper
├── search.py       # search_sources(query, max_jobs) — runs both sources, merges/dedupes by URL; used by POST /api/scraper/search
├── runner.py       # Orchestrates sources, loads config, saves jobs
└── __main__.py     # CLI entry point (direct invocation)
```

## How It Works

1. `POST /api/scraper/search` (body `{query}`) calls `search.py::search_sources(query)`; a blank query returns `[]` without calling either source. Each candidate's status (`applied`/`scraped`/`none`) is computed against this profile's existing jobs. The query is persisted to `profile_config['last_job_search']`; candidates themselves are NOT persisted.
2. The user checkbox-selects candidates in the Find Jobs UI and calls `POST /api/scraper/scrape-selected` (body `{jobs:[...]}`), which saves the batch, runs `job.intake()`, and kicks off `run_pipeline()` (scoring + generation) via a threaded background job with SSE updates.
3. Each source's `fetch()` is called with the config and max job count (shared by both `search_sources` and the underlying scraper logic).
4. Results are deduped by URL.

## Search Config Keys (Config table)

| Key | Type | Used by |
|---|---|---|
| `keywords_whitelist` | JSON array | Both (see Known Issues) |
| `keywords_blacklist` | JSON array | Both (client-side filter) |
| `max_jobs_per_source` | int | Both |
| `location` | str | Stored only — not wired |
| `remote_only` | bool | Stored only — not wired |
| `full_time_only` | bool | Stored only — not wired |
| `target_salary_min` | int | Stored only — not wired |
| `benefits_priorities` | JSON array | Stored only — not wired |

## Known Issues (open)

- **Remotive only uses first whitelist keyword** — `fetch()` sends only `config.keywords_whitelist[0]` as the `search` param. Should either iterate over all keywords (one request per keyword, dedupe results) or join them. Remotive accepts full phrases (e.g. "Python Dev"), not just single words.
- **Remotive missing client-side whitelist filter** — after the API response, results are not filtered against the full whitelist. Only the blacklist is applied client-side. Should add whitelist filtering matching RemoteOK's approach.
