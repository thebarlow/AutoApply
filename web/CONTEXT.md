# Web Context

FastAPI backend + Alpine.js v3 frontend. Single-page dashboard at `/`.

## Architecture

- `main.py` — FastAPI app; mounts static files; includes routers
- `routers/jobs.py` — all job endpoints (GET, DELETE, PATCH state, POST score, POST generate/resume, POST generate/cover, GET resume, GET cover)
- `static/index.html` — Alpine.js dashboard; all state managed client-side in `dashboard()` component
- `static/style.css` — table, overlay, badges, dropdowns

## Running

```
uvicorn web.main:app --reload
```

## Known Issues

- Generation endpoints are synchronous — resume/cover generation blocks the request for 30–60 seconds while Claude and pandoc run. For a single-user local tool this is acceptable.
- Salary sort is lexicographic when salary contains non-numeric characters (e.g., "$120k–$150k"). Values without parseable numbers sort as 0.
- Alpine.js loaded from CDN — requires internet access.

## Future Work

- Config page (`/config`) for editing weights, thresholds, and user profile
- Polling or WebSocket feedback during long-running generation requests
- Filter by status in addition to sorting
- Grouping rows by job title
- Clustering by location
