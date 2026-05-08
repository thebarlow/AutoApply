# Web Context

FastAPI backend + Alpine.js v3 frontend. Single-page dashboard at `/`.

## Architecture

```
web/
├── main.py              # FastAPI app; mounts static files; includes routers
├── routers/
│   ├── jobs.py          # All job endpoints (see API below)
│   └── scraper.py       # POST /api/scraper/stage-job (called by browser extension + API scrapers)
└── static/
    ├── index.html       # Alpine.js dashboard; all UI state in dashboard() component
    └── style.css        # Table, overlay, badges, dropdowns
```

## Running

```
uvicorn web.main:app --reload
```

## API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/jobs` | All jobs, ordered by final_score desc |
| `PATCH` | `/api/jobs/{job_key}/state` | Transition to `applied` (only valid value) |
| `DELETE` | `/api/jobs/{job_key}` | Hard delete |
| `POST` | `/api/jobs/{job_key}/score` | Run scorer; updates score fields, state unchanged |
| `POST` | `/api/jobs/{job_key}/generate/resume` | Generate resume PDF; updates resume_path |
| `POST` | `/api/jobs/{job_key}/generate/cover` | Generate cover letter PDF; updates cover_path |
| `GET` | `/api/jobs/{job_key}/resume` | Serve resume PDF |
| `GET` | `/api/jobs/{job_key}/cover` | Serve cover letter PDF |
| `POST` | `/api/scraper/stage-job` | Ingest a job from browser extension or scraper |

## Known Issues

- Generation endpoints are synchronous — resume/cover generation blocks the request for 30–60 seconds while Claude and pandoc run. Acceptable for a single-user local tool.
- Salary sort is lexicographic when salary contains non-numeric characters (e.g., "$120k–$150k"). Values without parseable numbers sort as 0.
- Alpine.js loaded from CDN — requires internet access.

## Web Router Limitations

### resume_md_exists / cover_md_exists in _serialize()
`_serialize()` in `jobs.py` calls `Path.exists()` twice per job to derive `resume_md_exists` and `cover_md_exists`. These filesystem checks run on every call to `GET /api/jobs`, meaning a list of N jobs triggers 2N stat calls. At the current scale (<100 jobs, local filesystem) this is negligible (<5ms). If the job count grows or the API is called frequently, move these checks out of `_serialize` into a per-job endpoint and have the frontend fetch job details on modal open.

## Future Work

- Config page (`/config`) for editing scoring weights, thresholds, and user profile
- Polling or WebSocket feedback during long-running generation requests
- Filter by status in addition to sorting
- Grouping rows by job title
- Clustering by location
- Browser extension auto-marks job as applied on form submission (see browser-extension/CONTEXT.md)
