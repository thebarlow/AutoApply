# Scraper Context

API-based job scrapers for Remotive and RemoteOK. Fetches jobs and saves them to the DB. An endpoint exists (`POST /api/scraper/run` in `web/routers/scraper.py`) that runs them as a background thread and feeds new jobs into `intake_pipeline` — but it is **dormant**: nothing in the React UI calls it, it is only reachable via raw HTTP, and it requires a `scraper_sources` config row (else returns 400). Not currently part of the active workflow.

## Architecture

```
scraper/
├── __init__.py     # empty package marker
├── base.py         # JobSource ABC, ScrapedJob dataclass
├── remotive.py     # Remotive API scraper
├── remoteok.py     # RemoteOK API scraper
├── runner.py       # Orchestrates sources, loads config, saves jobs
└── __main__.py     # CLI entry point (direct invocation)
```

## How It Works

1. `web/routers/scraper.py` reads `scraper_sources` from the Config table (comma-separated, e.g. `"remotive,remoteok"`) to determine which sources to run.
2. `runner.py` loads `SearchConfig` and `max_jobs_per_source` from the Config DB table.
3. Each source's `fetch()` is called with the config and max job count.
4. Results are deduped by URL and saved to the DB with `state=scraped`.
5. Each new job is passed to `job.intake()` and then `run_pipeline()` (scoring + generation).

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
