# web/ Context

FastAPI backend. Serves the REST API on port 8080. The frontend (React) is a separate Vite app in `react-dashboard/` — this module does **not** serve HTML.

## Architecture

```
web/
├── main.py                  # FastAPI app; includes all routers
├── sse.py                   # Server-Sent Events helpers (job update broadcasts)
├── llm_status.py            # In-memory tracker for active LLM jobs (keyed by job_key+action)
├── intake_pipeline.py       # Post-ingest pipeline (score + generate) run per new job
├── static/images/           # Favicon and apple-touch-icon (served by FastAPI)
└── routers/
    ├── jobs.py              # Core job endpoints: CRUD, score, generate resume/cover, serve PDFs
    ├── scraper.py           # POST /api/scraper/stage-job (browser ext) + POST /api/scraper/run (API scrapers)
    ├── config.py            # GET/PUT config key-value pairs
    ├── prompts.py           # GET/PUT per-profile prompt overrides
    ├── llm_test.py          # POST /api/llm/test (verify LLM connectivity)
    ├── llm_status_router.py # GET /api/llm/status (active LLM job status)
    ├── session_cost_router.py # GET /api/session-cost (cumulative LLM token spend)
    ├── setup_status.py      # GET /api/setup/status (onboarding completeness)
    ├── stats.py             # GET /api/stats (pipeline activity by time window) + GET /api/skill-frequency
    ├── shutdown.py          # POST /api/shutdown (graceful or immediate server exit)
    ├── tray.py              # Tray app integration endpoints
    ├── events.py            # SSE endpoint (/api/events)
    └── docs_router.py       # Serves Obsidian markdown docs as JSON
```

## Routing Rules

| Task | File |
|---|---|
| Job CRUD, scoring, resume/cover generation | `routers/jobs.py` |
| Ingesting a job from the browser extension or triggering API scrapers | `routers/scraper.py` |
| Pipeline activity stats by time window | `routers/stats.py` |
| Skill frequency across extracted jobs | `routers/stats.py` (delegates to `core/skill_analytics.py`) |
| Session LLM cost tracking | `routers/session_cost_router.py` |
| Server shutdown (immediate or wait for LLM) | `routers/shutdown.py` |
| LLM provider/model/key config | `routers/config.py` |
| Prompt template get/set per profile | `routers/prompts.py` |
| LLM connectivity test | `routers/llm_test.py` |
| Active LLM task status (for UI polling) | `routers/llm_status_router.py` |
| Onboarding/setup state | `routers/setup_status.py` |
| Tray app job card data | `routers/tray.py` |
| Real-time job update stream | `routers/events.py` |
| Documentation content for Docs page | `routers/docs_router.py` |

## Key Design Notes

- **Score/generate are in `core/job.py`** — `routers/jobs.py` resolves the LLM client, prompt content, and template paths, then delegates to `job.score()`, `job.generate_resume_md/pdf()`, `job.generate_cover_md/pdf()`.
- **Generation is synchronous** — resume/cover generation blocks the request 30–60s while Claude + pandoc run. Acceptable for single-user local use.
- **SSE for real-time updates** — `sse.py` broadcasts job state changes; `App.jsx` subscribes via `EventSource`.
- **`llm_status.py`** tracks in-progress LLM calls (start/finish) so the UI can show spinners without polling.

## API Surface

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/jobs` | All jobs ordered by `final_score` desc |
| `DELETE` | `/api/jobs/{job_key}` | Hard delete |
| `PATCH` | `/api/jobs/{job_key}/state` | State transition |
| `POST` | `/api/jobs/{job_key}/score` | Score job via LLM |
| `POST` | `/api/jobs/{job_key}/generate/resume` | Generate resume MD + PDF |
| `POST` | `/api/jobs/{job_key}/generate/cover` | Generate cover letter MD + PDF |
| `GET` | `/api/jobs/{job_key}/resume` | Serve resume PDF |
| `GET` | `/api/jobs/{job_key}/cover` | Serve cover letter PDF |
| `POST` | `/api/scraper/stage-job` | Ingest job from browser extension or scraper |
| `POST` | `/api/scraper/run` | Trigger background run of enabled API scrapers |
| `GET` | `/api/stats` | Pipeline activity bars + by-state counts (window param) |
| `GET` | `/api/skill-frequency` | Combined required+preferred skill counts (`skills`) plus `tech_stack`, distinct jobs, across all extracted jobs; no window. Also returns `profile_skills` (active user's skills, normalized) so the UI can flag covered skills. The job aggregation is cached in-process keyed by extracted-job count with a 60s TTL — a re-extraction that doesn't change the count can be up to 60s stale; tests reset `stats._SKILL_CACHE` via an autouse fixture. |
| `GET` | `/api/skill-frequency/jobs` | Job keys whose extraction data lists a given `skill` (normalized, any field) |
| `GET` | `/api/session-cost` | Cumulative LLM token cost for current session |
| `POST` | `/api/shutdown` | Shut down server (`mode=immediate` or `mode=wait`) |
| `GET/PUT` | `/api/config/{key}` | Config key-value store |
| `GET/PUT` | `/api/prompts/...` | Prompt templates per profile |
| `POST` | `/api/llm/test` | Test LLM connectivity |
| `GET` | `/api/llm/status` | Active LLM task status |
| `GET` | `/api/setup/status` | Onboarding completeness check |
| `GET` | `/api/events` | SSE stream for job updates |

## Known Issues

- `_serialize()` in `jobs.py` calls `Path.exists()` twice per job (resume_md_exists, cover_md_exists) on every `GET /api/jobs`. At current scale (<100 jobs) this is negligible. If job count grows, move to a per-job detail endpoint.
- Salary sort is lexicographic for non-numeric salary strings (e.g. "$120k–$150k"). Values without parseable numbers sort as 0.
