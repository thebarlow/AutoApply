# Review Queue UI Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a job posting link, expandable description preview, and remote badge to review queue cards; remove dead `employment_type` reference.

**Architecture:** Three-layer change — API serializer exposes new fields, CSS adds new rules, JS card builder consumes new fields. No new files needed; all changes are additive except dropping `employment_type` from the card template.

**Tech Stack:** FastAPI, SQLAlchemy, vanilla JS, CSS `line-clamp`, pytest

---

## File Map

| File | Change |
|---|---|
| `web/routers/jobs.py` | Add `url`, `description`, `remote` to `_serialize()` |
| `tests/web/test_jobs_api.py` | Add tests verifying new fields are present in API response |
| `web/static/style.css` | Add `.description`, `.description.expanded`, `.description-toggle`, `.pill-remote` |
| `web/static/index.html` | Update `buildCard()` — link icon, description block + toggle, remote pill, remove `employment_type` |

---

### Task 1: Expose `url`, `description`, `remote` in the API

**Files:**
- Modify: `web/routers/jobs.py`
- Modify: `tests/web/test_jobs_api.py`

- [ ] **Step 1: Write failing tests**

Add to the bottom of `tests/web/test_jobs_api.py`:

```python
def test_get_jobs_includes_url(client, db_session):
    _make_job(db_session, "job_url", JobState.PENDING_REVIEW)
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    job = resp.json()[0]
    assert "url" in job
    assert job["url"] == "https://indeed.com/job/job_url"


def test_get_jobs_includes_description(client, db_session):
    job = Job(
        job_key="job_desc",
        source="indeed",
        title="Engineer",
        company="Acme",
        url="https://indeed.com/job/job_desc",
        state=JobState.PENDING_REVIEW.value,
        description="We are looking for a software engineer.",
        remote=True,
    )
    db_session.add(job)
    db_session.commit()

    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    job_data = resp.json()[0]
    assert job_data["description"] == "We are looking for a software engineer."
    assert job_data["remote"] is True


def test_get_jobs_remote_none_when_not_set(client, db_session):
    _make_job(db_session, "job_noremote", JobState.PENDING_REVIEW)
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    job_data = resp.json()[0]
    assert "remote" in job_data
    assert job_data["remote"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/web/test_jobs_api.py::test_get_jobs_includes_url tests/web/test_jobs_api.py::test_get_jobs_includes_description tests/web/test_jobs_api.py::test_get_jobs_remote_none_when_not_set -v
```

Expected: 3 FAILs — `url`, `description`, `remote` not in response.

- [ ] **Step 3: Update `_serialize()` in `web/routers/jobs.py`**

Replace the existing `_serialize` function body with:

```python
def _serialize(job: Job) -> dict[str, Any]:
    justification = job.score_justification
    if isinstance(justification, str):
        try:
            justification = json.loads(justification)
        except (json.JSONDecodeError, TypeError):
            justification = {}

    return {
        "job_key": job.job_key,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "salary": job.salary,
        "url": job.url,
        "description": job.description,
        "remote": job.remote,
        "state": job.state,
        "desirability_score": job.desirability_score,
        "fit_score": job.fit_score,
        "final_score": job.final_score,
        "score_justification": justification,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/web/test_jobs_api.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add web/routers/jobs.py tests/web/test_jobs_api.py
git commit -m "[feat] Expose url, description, remote in jobs API serializer"
```

---

### Task 2: Add CSS for description clamp, toggle, and remote badge

**Files:**
- Modify: `web/static/style.css`

- [ ] **Step 1: Append new rules to `web/static/style.css`**

Add at the bottom of the file:

```css
/* External link icon */
.job-link {
  margin-left: 0.5rem;
  color: #3a3a8c;
  text-decoration: none;
  font-size: 0.85rem;
  opacity: 0.7;
  flex-shrink: 0;
}

.job-link:hover { opacity: 1; }

/* Remote badge */
.pill-remote {
  background: #e0f0ff;
  color: #1a66cc;
}

/* Description block */
.description {
  font-size: 0.82rem;
  color: #444;
  line-height: 1.5;
  margin-bottom: 0.5rem;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
}

.description.expanded {
  display: block;
  -webkit-line-clamp: unset;
}

.description-toggle {
  background: none;
  border: none;
  padding: 0;
  font-size: 0.78rem;
  color: #3a3a8c;
  cursor: pointer;
  margin-bottom: 0.75rem;
  text-decoration: underline;
}

.description-toggle:hover { color: #1a1a2e; }
```

- [ ] **Step 2: Commit**

```bash
git add web/static/style.css
git commit -m "[feat] Add CSS for description clamp, expand toggle, remote badge"
```

---

### Task 3: Update card template in `index.html`

**Files:**
- Modify: `web/static/index.html`

- [ ] **Step 1: Replace `buildCard` in `web/static/index.html`**

Find and replace the entire `buildCard` function (lines 49–82 in the current file) with:

```javascript
  function buildCard(job) {
    const card = document.createElement('div');
    card.className = 'card';
    card.dataset.key = job.job_key;

    const just = job.score_justification || {};
    const linkHtml = job.url
      ? `<a class="job-link" href="${esc(job.url)}" target="_blank" rel="noopener noreferrer">&#x2197;</a>`
      : '';
    const remotePill = job.remote === true
      ? `<span class="pill pill-remote">Remote</span>`
      : '';
    const descHtml = job.description
      ? `<div class="description" id="desc-${esc(job.job_key)}">${esc(job.description)}</div>
         <button class="description-toggle" data-target="desc-${esc(job.job_key)}">Read more</button>`
      : '';

    card.innerHTML = `
      <div class="card-actions">
        <button class="btn btn-approve" data-action="approved">Approve</button>
        <button class="btn btn-reject"  data-action="rejected">Reject</button>
      </div>
      <div class="card-header">
        <span class="job-title">${esc(job.title || '(no title)')}</span>
        <span style="display:flex;align-items:baseline;gap:0.25rem">
          <span class="final-score ${scoreClass(job.final_score)}">${pct(job.final_score)}</span>
          ${linkHtml}
        </span>
      </div>
      <div class="card-meta">${esc(job.company || '')}${job.location ? ' · ' + esc(job.location) : ''}</div>
      <div class="card-detail">${esc(job.salary || '')}${job.posted_at ? ' · ' + esc(job.posted_at) : ''}</div>
      <div class="pills">
        <span class="pill">Desirability ${pct(job.desirability_score)}</span>
        <span class="pill">Fit ${pct(job.fit_score)}</span>
        ${remotePill}
      </div>
      ${descHtml}
      <div class="justification">
        ${just.desirability ? '<p><strong>Desirability:</strong> ' + esc(just.desirability) + '</p>' : ''}
        ${just.fit         ? '<p><strong>Fit:</strong> '         + esc(just.fit)         + '</p>' : ''}
      </div>
      <div class="card-feedback"></div>
    `;

    card.querySelectorAll('.btn[data-action]').forEach(btn => {
      btn.addEventListener('click', () => handleAction(card, btn.dataset.action));
    });

    card.querySelectorAll('.description-toggle').forEach(btn => {
      btn.addEventListener('click', () => {
        const desc = document.getElementById(btn.dataset.target);
        const expanded = desc.classList.toggle('expanded');
        btn.textContent = expanded ? 'Show less' : 'Read more';
      });
    });

    return card;
  }
```

- [ ] **Step 2: Verify the server starts and cards render**

```
uvicorn web.main:app --reload
```

Open `http://localhost:8000` in a browser. Confirm:
- Each card shows the `↗` link icon next to the score; clicking opens the job URL in a new tab
- Description shows truncated to ~3 lines with "Read more"; clicking expands and shows "Show less"
- Remote jobs show a blue "Remote" pill; non-remote jobs do not
- `employment_type` is gone

- [ ] **Step 3: Commit**

```bash
git add web/static/index.html
git commit -m "[feat] Update review queue cards with link, description preview, remote badge"
```
