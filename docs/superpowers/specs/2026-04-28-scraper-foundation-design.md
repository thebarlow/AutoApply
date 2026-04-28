# Scraper Foundation + API Sources Design Spec

**Sub-project 1 of 3 in the scraper module.** Establishes the `JobSource` ABC and `ScrapedJob` dataclass, implements two automated API sources (Remotive and RemoteOK), wires up a web trigger endpoint and CLI entrypoint, and seeds required config keys.

This sub-project covers only API-based sources. Playwright sources (Indeed, Monster) are sub-project 2. The browser extension (LinkedIn, Indeed) is sub-project 3.

---

## Goal

Automatically pull job listings from Remotive and RemoteOK on demand, deduplicate against existing DB records by URL, and write new jobs to SQLite in `scraped` state. Triggerable via `POST /api/scraper/run` (async, returns immediately) or `python -m scraper` (CLI). Scoring remains a separate manual step.

---

## Architecture

```
scraper/
├── __init__.py
├── base.py         # ScrapedJob dataclass + JobSource ABC
├── remotive.py     # RemotiveSource
├── remoteok.py     # RemoteOKSource
└── runner.py       # run_scraper(), load_search_config(), load_max_jobs(), save_jobs()

web/routers/scraper.py   # POST /api/scraper/run

tests/scraper/
├── __init__.py
├── test_base.py
├── test_remotive.py
├── test_remoteok.py
└── test_runner.py
```

Sources own only data fetching. `runner.py` owns orchestration, config loading, deduplication, and DB writes. The web router and CLI both call `run_scraper()`.

---

## Data Contract

### `ScrapedJob` (base.py)

```python
@dataclass
class ScrapedJob:
    source: str        # "remotive" or "remoteok"
    job_key: str       # "{source}_{external_id}"
    title: str
    company: str
    url: str           # deduplication key
    description: str
    location: str = ""
    salary: str = ""
    remote: bool = False
    posted_at: str = ""
```

### `JobSource` ABC (base.py)

```python
class JobSource(ABC):
    @property
    @abstractmethod
    def source_id(self) -> str: ...

    @abstractmethod
    def fetch(self, config: SearchConfig, max_jobs: int) -> list[ScrapedJob]: ...
```

Sources receive a fully-loaded `SearchConfig` and a `max_jobs` int. They return a list and do nothing else — no DB access, no side effects.

---

## Runner (runner.py)

### `load_search_config(db: Session) -> SearchConfig`
Reads config table keys (`keywords_whitelist`, `keywords_blacklist`, `location`, `remote_only`, `full_time_only`, `target_salary_min`, `benefits_priorities`) and constructs a `SearchConfig`. Keys are parsed from their stored string formats (JSON arrays for lists, string for location, etc.).

### `load_max_jobs(db: Session) -> int`
Reads `max_jobs_per_source` from the config table. Defaults to `50` if missing.

### `save_jobs(db: Session, jobs: list[ScrapedJob]) -> int`
For each job, checks whether a record with the same `url` already exists. Skips duplicates. Inserts new jobs as `Job` model instances with `state=scraped`. Commits once after all inserts. Returns count of newly inserted jobs.

### `run_scraper(db: Session, sources: list[JobSource]) -> int`
1. Calls `load_search_config(db)` and `load_max_jobs(db)`
2. For each source, calls `source.fetch(config, max_jobs)` inside a try/except — logs a warning and continues if a source raises
3. Passes all collected `ScrapedJob` lists to `save_jobs`
4. Logs per-source counts and total to stdout
5. Returns total new jobs saved

---

## API Sources

### RemotiveSource (remotive.py)

- `GET https://remotive.com/api/remote-jobs?search=<keyword>&limit=<max_jobs>`
- Uses the first term from `config.keywords_whitelist` as the search query; empty string if whitelist is empty
- Filters results client-side: drops jobs whose title or description contains any `keywords_blacklist` term
- Field mapping:

| Remotive field | ScrapedJob field |
|---|---|
| `id` | job_key suffix (`remotive_{id}`) |
| `url` | url |
| `title` | title |
| `company_name` | company |
| `candidate_required_location` | location |
| `salary` | salary |
| `description` | description |
| `publication_date` | posted_at |
| *(always)* | remote=True |

### RemoteOKSource (remoteok.py)

- `GET https://remoteok.com/api` — returns all jobs, no server-side filtering
- First element of the response array is a metadata object — skip it
- Filters client-side: keeps jobs where title or description contains any `keywords_whitelist` term (if whitelist non-empty); drops any matching `keywords_blacklist` term
- Caps results at `max_jobs` after filtering
- Field mapping:

| RemoteOK field | ScrapedJob field |
|---|---|
| `id` | job_key suffix (`remoteok_{id}`) |
| `url` | url |
| `position` | title |
| `company` | company |
| `location` | location |
| `description` | description |
| `date` | posted_at |
| *(always)* | remote=True |

---

## Web Endpoint (web/routers/scraper.py)

```
POST /api/scraper/run
```

Reads `scraper_sources` from the config table to determine which sources to instantiate. Spawns a daemon thread calling `run_scraper(SessionLocal(), sources)` — same pattern as the generator. Returns immediately:

```json
{ "status": "started", "sources": ["remotive", "remoteok"] }
```

If `scraper_sources` config key is missing or empty, returns `400` with a clear error message.

Registered in `web/main.py` alongside the jobs router.

---

## CLI (scraper/__main__.py)

```bash
python -m scraper                          # all sources from config
python -m scraper --source remotive        # single source
python -m scraper --source remotive --source remoteok  # explicit list
```

Opens its own DB session, calls `run_scraper()`, prints per-source counts and total to stdout. Same pattern as `scorer/scorer.py`.

---

## Config Keys (db/seed.py additions)

| Key | Default | Description |
|---|---|---|
| `max_jobs_per_source` | `"50"` | Max jobs fetched per source per run |
| `scraper_sources` | `"remotive,remoteok"` | Comma-separated enabled source IDs |

---

## Error Handling

| Scenario | Behavior |
|---|---|
| Source `fetch()` raises (network error, bad response) | Log warning with source name + error, continue with remaining sources |
| `save_jobs` raises (DB error) | Exception propagates — run fails rather than silently losing jobs |
| `scraper_sources` config key missing | Web endpoint returns 400; CLI prints error and exits |
| Source returns malformed job data | Skip that job, log warning, continue |

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `scraper/__init__.py` | Create | Package marker |
| `scraper/base.py` | Create | `ScrapedJob` dataclass, `JobSource` ABC |
| `scraper/remotive.py` | Create | `RemotiveSource` |
| `scraper/remoteok.py` | Create | `RemoteOKSource` |
| `scraper/runner.py` | Create | `run_scraper`, `save_jobs`, `load_search_config`, `load_max_jobs` |
| `scraper/__main__.py` | Create | CLI entrypoint |
| `web/routers/scraper.py` | Create | `POST /api/scraper/run` |
| `web/main.py` | Modify | Register scraper router |
| `db/seed.py` | Modify | Seed `max_jobs_per_source` and `scraper_sources` |
| `tests/scraper/__init__.py` | Create | Package marker |
| `tests/scraper/test_base.py` | Create | `ScrapedJob` construction + defaults |
| `tests/scraper/test_remotive.py` | Create | Field mapping, keyword filtering, max_jobs cap |
| `tests/scraper/test_remoteok.py` | Create | Field mapping, client-side filtering, max_jobs cap |
| `tests/scraper/test_runner.py` | Create | Dedup, aggregation, source error resilience, config loading |

---

## Testing

`tests/scraper/test_base.py` — `ScrapedJob` construction, field defaults

`tests/scraper/test_remotive.py` — mock `httpx.get`:
- `test_remotive_maps_fields_correctly` — assert all fields mapped from API response
- `test_remotive_filters_blacklist_terms` — jobs with blacklisted terms dropped
- `test_remotive_respects_max_jobs` — result capped at max_jobs

`tests/scraper/test_remoteok.py` — mock `httpx.get`:
- `test_remoteok_maps_fields_correctly` — assert all fields mapped
- `test_remoteok_filters_by_whitelist` — only jobs matching whitelist terms kept
- `test_remoteok_filters_blacklist_terms` — blacklisted terms dropped
- `test_remoteok_respects_max_jobs` — result capped at max_jobs after filtering
- `test_remoteok_skips_metadata_element` — first array element skipped

`tests/scraper/test_runner.py` — in-memory SQLite + StaticPool:
- `test_save_jobs_inserts_new_jobs` — new URLs inserted, returns correct count
- `test_save_jobs_deduplicates_by_url` — existing URL skipped
- `test_run_scraper_aggregates_sources` — two mock sources, correct total
- `test_run_scraper_continues_on_source_error` — one source raises, other still runs
- `test_load_search_config_from_db` — seeded config keys map to correct `SearchConfig` fields
- `test_load_max_jobs_defaults_to_50` — missing key returns 50
