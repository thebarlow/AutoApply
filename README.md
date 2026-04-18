# auto_apply

Automated job scraping and application pipeline.

---

## Job Board API Reference

### Remotive

**Endpoint:** `GET https://remotive.com/api/remote-jobs`

| Parameter | Type | Description |
|---|---|---|
| `category` | String | Filter by category slug (e.g. `software-dev`). See `/api/remote-jobs/categories` |
| `company_name` | String | Case-insensitive partial match on company name |
| `search` | String | Free-text search on job title and description |
| `limit` | Integer | Max number of results (default: all) |

**Rate limit:** Max ~2 requests/minute; recommend querying a few times daily.

---

### Himalayas

**Endpoint:** `GET https://himalayas.app/jobs/api/search`

| Parameter | Type | Description |
|---|---|---|
| `q` | String | Free-text search query (e.g. `python developer`) |
| `country` | String | ISO alpha-2 code, country name, or slug |
| `worldwide` | Boolean | Filter to worldwide-friendly positions only |
| `exclude_worldwide` | Boolean | Exclude worldwide matches when filtering by country |
| `seniority` | String | `Entry-level`, `Mid-level`, `Senior`, `Manager`, `Director`, `Executive` |
| `employment_type` | String | `Full Time`, `Part Time`, `Contractor`, `Temporary`, `Intern`, `Volunteer`, `Other` |
| `company` | String | Comma-separated company slugs (e.g. `linear,vercel`) |
| `timezone` | String | e.g. `-5`, `UTC-5`, or `UTC+05:30` |
| `sort` | String | `relevant`, `recent`, `salaryAsc`, `salaryDesc`, `nameAToZ`, `nameZToA`, `jobs` |
| `page` | Integer | 1-based page number |
| `limit` | Integer | Max results per request (default: 20, max: 20) |
| `offset` | Integer | Number of jobs to skip (browse endpoint only) |

All parameters optional. Multiple values allowed for `seniority`, `employment_type`, and `company`.
