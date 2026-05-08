# Modal Tabs Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat job-details modal with a tabbed layout (Overview / Resume / Cover Letter) using a vertical sidebar, context-sensitive action bar, split MD/PDF generation, and a prompt viewer overlay.

**Architecture:** All backend changes live in `web/routers/jobs.py`. The frontend is a single-file Alpine.js app in `web/static/index.html` — we rewrite the overlay section in-place, adding new state fields and methods to the existing `dashboard()` component. CSS additions go in `web/static/style.css`.

**Tech Stack:** FastAPI, Alpine.js (CDN), plain CSS, SQLite via SQLAlchemy

---

## File Map

| File | What changes |
|---|---|
| `web/routers/jobs.py` | New module-level `_GENERATOR_OUTPUTS` path; `_serialize()` gains `resume_md_exists` + `cover_md_exists`; new imports; 8 new endpoints |
| `web/static/style.css` | Replace `.overlay-panel` + `.overlay-description` styles; add `.overlay-top`, `.overlay-body`, `.overlay-tab-sidebar`, `.overlay-tab-btn`, `.overlay-tab-content`, `.view-toggle`, `.overlay-pdf-frame`, `.overlay-md-viewer`, `.prompt-overlay`, `.prompt-overlay-panel` |
| `web/static/index.html` | Replace everything inside `<div class="overlay-backdrop">` with new tabbed layout; extend `dashboard()` with new state fields and methods |

---

## Task 1: Add `_GENERATOR_OUTPUTS` and `resume_md_exists` / `cover_md_exists` to serializer

**Files:**
- Modify: `web/routers/jobs.py`

- [ ] **Step 1: Add module-level path constant and new imports**

  Open `web/routers/jobs.py`. After the existing imports, add:

  ```python
  from fastapi.responses import FileResponse, PlainTextResponse

  from core.types import UserProfile, WorkHistoryEntry, EducationEntry
  from db.models import Config, Job, UserProfileModel
  from generator.generator import generate_resume_md as _generate_resume_md
  from generator.generator import generate_resume_pdf as _generate_resume_pdf
  from generator.generator import generate_cover_md as _generate_cover_md
  from generator.generator import generate_cover_pdf as _generate_cover_pdf
  from generator.generator import build_resume_prompt, build_cover_prompt
  ```

  Replace the existing `from fastapi.responses import FileResponse` line (keep it, just add `PlainTextResponse`). Replace `from db.models import Job` with `from db.models import Config, Job, UserProfileModel`.

  After the imports block (before `router = APIRouter(...)`), add:

  ```python
  _GENERATOR_OUTPUTS = Path(__file__).parent.parent / "generator" / "outputs"
  ```

- [ ] **Step 2: Add `resume_md_exists` and `cover_md_exists` to `_serialize()`**

  In `_serialize()`, add two fields before the closing `}`:

  ```python
  "resume_md_exists": (_GENERATOR_OUTPUTS / f"{job.job_key}_resume.md").exists(),
  "cover_md_exists": (_GENERATOR_OUTPUTS / f"{job.job_key}_cover.md").exists(),
  ```

  The full return dict should now end with:

  ```python
      "resume_path": job.resume_path,
      "cover_path": job.cover_path,
      "resume_md_exists": (_GENERATOR_OUTPUTS / f"{job.job_key}_resume.md").exists(),
      "cover_md_exists": (_GENERATOR_OUTPUTS / f"{job.job_key}_cover.md").exists(),
  }
  ```

- [ ] **Step 3: Verify with curl**

  Start the server (or confirm it's running), then:

  ```bash
  curl -s http://localhost:8000/api/jobs | python -m json.tool | grep -E "md_exists|job_key" | head -20
  ```

  Expected: each job object has `"resume_md_exists": true/false` and `"cover_md_exists": true/false`.

- [ ] **Step 4: Commit**

  ```bash
  git add web/routers/jobs.py
  git commit -m "[feat] Add resume_md_exists/cover_md_exists to job serializer"
  ```

---

## Task 2: Add generate/md and generate/pdf endpoints for Resume

**Files:**
- Modify: `web/routers/jobs.py`

- [ ] **Step 1: Add `POST /{job_key}/generate/resume/md`**

  After the existing `generate_resume_endpoint` function, add:

  ```python
  @router.post("/{job_key}/generate/resume/md")
  def generate_resume_md_endpoint(job_key: str, db: Session = Depends(get_db)):
      job = db.query(Job).filter(Job.job_key == job_key).first()
      if job is None:
          raise HTTPException(status_code=404, detail="Job not found")
      client, model = get_openai_client(db)
      _generate_resume_md(job_key, db=db, client=client, model=model)
      md_path = _GENERATOR_OUTPUTS / f"{job_key}_resume.md"
      if not md_path.exists():
          raise HTTPException(status_code=500, detail="Resume markdown generation failed")
      db.refresh(job)
      return _serialize(job)
  ```

- [ ] **Step 2: Add `POST /{job_key}/generate/resume/pdf`**

  ```python
  @router.post("/{job_key}/generate/resume/pdf")
  def generate_resume_pdf_endpoint(job_key: str, db: Session = Depends(get_db)):
      job = db.query(Job).filter(Job.job_key == job_key).first()
      if job is None:
          raise HTTPException(status_code=404, detail="Job not found")
      md_path = _GENERATOR_OUTPUTS / f"{job_key}_resume.md"
      if not md_path.exists():
          raise HTTPException(status_code=400, detail="Resume markdown must be generated first")
      _generate_resume_pdf(job_key, db=db)
      db.refresh(job)
      if job.state == "failed":
          raise HTTPException(status_code=500, detail="Resume PDF rendering failed")
      return _serialize(job)
  ```

- [ ] **Step 3: Verify with curl (use a real job_key from your DB)**

  ```bash
  # Generate MD
  curl -s -X POST http://localhost:8000/api/jobs/linkedin_4397062452/generate/resume/md | python -m json.tool | grep md_exists
  # Expected: "resume_md_exists": true

  # Generate PDF
  curl -s -X POST http://localhost:8000/api/jobs/linkedin_4397062452/generate/resume/pdf | python -m json.tool | grep resume_path
  # Expected: "resume_path": "...resume.pdf"
  ```

- [ ] **Step 4: Commit**

  ```bash
  git add web/routers/jobs.py
  git commit -m "[feat] Add generate/resume/md and generate/resume/pdf endpoints"
  ```

---

## Task 3: Add generate/md and generate/pdf endpoints for Cover Letter

**Files:**
- Modify: `web/routers/jobs.py`

- [ ] **Step 1: Add `POST /{job_key}/generate/cover/md`**

  ```python
  @router.post("/{job_key}/generate/cover/md")
  def generate_cover_md_endpoint(job_key: str, db: Session = Depends(get_db)):
      job = db.query(Job).filter(Job.job_key == job_key).first()
      if job is None:
          raise HTTPException(status_code=404, detail="Job not found")
      client, model = get_openai_client(db)
      _generate_cover_md(job_key, db=db, client=client, model=model)
      md_path = _GENERATOR_OUTPUTS / f"{job_key}_cover.md"
      if not md_path.exists():
          raise HTTPException(status_code=500, detail="Cover letter markdown generation failed")
      db.refresh(job)
      return _serialize(job)
  ```

- [ ] **Step 2: Add `POST /{job_key}/generate/cover/pdf`**

  ```python
  @router.post("/{job_key}/generate/cover/pdf")
  def generate_cover_pdf_endpoint(job_key: str, db: Session = Depends(get_db)):
      job = db.query(Job).filter(Job.job_key == job_key).first()
      if job is None:
          raise HTTPException(status_code=404, detail="Job not found")
      if not job.resume_path:
          raise HTTPException(status_code=400, detail="Resume PDF must be generated before cover letter PDF")
      md_path = _GENERATOR_OUTPUTS / f"{job_key}_cover.md"
      if not md_path.exists():
          raise HTTPException(status_code=400, detail="Cover letter markdown must be generated first")
      _generate_cover_pdf(job_key, db=db)
      db.refresh(job)
      if job.cover_path is None:
          raise HTTPException(status_code=500, detail="Cover letter PDF rendering failed")
      return _serialize(job)
  ```

- [ ] **Step 3: Commit**

  ```bash
  git add web/routers/jobs.py
  git commit -m "[feat] Add generate/cover/md and generate/cover/pdf endpoints"
  ```

---

## Task 4: Add markdown-serving and prompt endpoints

**Files:**
- Modify: `web/routers/jobs.py`

- [ ] **Step 1: Add `GET /{job_key}/resume/markdown` and `GET /{job_key}/cover/markdown`**

  ```python
  @router.get("/{job_key}/resume/markdown", response_class=PlainTextResponse)
  def serve_resume_markdown(job_key: str, db: Session = Depends(get_db)):
      job = db.query(Job).filter(Job.job_key == job_key).first()
      if job is None:
          raise HTTPException(status_code=404, detail="Job not found")
      path = _GENERATOR_OUTPUTS / f"{job_key}_resume.md"
      if not path.exists():
          raise HTTPException(status_code=404, detail="Resume markdown not found")
      return path.read_text(encoding="utf-8")


  @router.get("/{job_key}/cover/markdown", response_class=PlainTextResponse)
  def serve_cover_markdown(job_key: str, db: Session = Depends(get_db)):
      job = db.query(Job).filter(Job.job_key == job_key).first()
      if job is None:
          raise HTTPException(status_code=404, detail="Job not found")
      path = _GENERATOR_OUTPUTS / f"{job_key}_cover.md"
      if not path.exists():
          raise HTTPException(status_code=404, detail="Cover letter markdown not found")
      return path.read_text(encoding="utf-8")
  ```

- [ ] **Step 2: Add a `_load_profile` helper to avoid repeating profile-loading logic**

  Add this helper function above the router endpoints:

  ```python
  def _load_profile(db: Session) -> UserProfile:
      row = db.query(UserProfileModel).first()
      if not row:
          raise HTTPException(status_code=500, detail="No user profile found")
      data = json.loads(row.data)
      data["work_history"] = [WorkHistoryEntry(**e) for e in data.get("work_history", [])]
      data["education"] = [EducationEntry(**e) for e in data.get("education", [])]
      return UserProfile(**data)
  ```

- [ ] **Step 3: Add `GET /{job_key}/resume/prompt` and `GET /{job_key}/cover/prompt`**

  ```python
  @router.get("/{job_key}/resume/prompt", response_class=PlainTextResponse)
  def get_resume_prompt(job_key: str, db: Session = Depends(get_db)):
      job = db.query(Job).filter(Job.job_key == job_key).first()
      if job is None:
          raise HTTPException(status_code=404, detail="Job not found")
      profile = _load_profile(db)
      tpl = db.query(Config).filter_by(key="resume_prompt_template").first()
      if not tpl:
          raise HTTPException(status_code=500, detail="Resume prompt template not configured")
      return build_resume_prompt(job, profile, tpl.value)


  @router.get("/{job_key}/cover/prompt", response_class=PlainTextResponse)
  def get_cover_prompt(job_key: str, db: Session = Depends(get_db)):
      job = db.query(Job).filter(Job.job_key == job_key).first()
      if job is None:
          raise HTTPException(status_code=404, detail="Job not found")
      profile = _load_profile(db)
      tpl = db.query(Config).filter_by(key="cover_prompt_template").first()
      if not tpl:
          raise HTTPException(status_code=500, detail="Cover prompt template not configured")
      return build_cover_prompt(job, profile, tpl.value)
  ```

- [ ] **Step 4: Verify**

  ```bash
  curl -s http://localhost:8000/api/jobs/linkedin_4397062452/resume/markdown | head -5
  # Expected: markdown content (frontmatter + resume sections)

  curl -s http://localhost:8000/api/jobs/linkedin_4397062452/resume/prompt | head -5
  # Expected: the prompt text sent to the LLM
  ```

- [ ] **Step 5: Commit**

  ```bash
  git add web/routers/jobs.py
  git commit -m "[feat] Add markdown-serving and prompt endpoints for resume and cover"
  ```

---

## Task 5: CSS — overlay layout, tab sidebar, toggle pill, prompt overlay

**Files:**
- Modify: `web/static/style.css`

- [ ] **Step 1: Replace the overlay panel and description styles**

  Find and replace the existing overlay CSS block (lines ~92–190 in style.css, covering `.overlay-backdrop`, `.overlay-panel`, `.overlay-header`, `.overlay-meta`, `.action-bar`, `.overlay-divider`, `.overlay-description`):

  ```css
  /* Overlay backdrop */
  .overlay-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.45);
    display: flex;
    align-items: flex-start;
    justify-content: center;
    padding-top: 60px;
    z-index: 100;
  }

  /* Overlay panel — flex column, no internal scroll (content area scrolls instead) */
  .overlay-panel {
    background: #fff;
    border-radius: 8px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.18);
    width: min(780px, 94vw);
    max-height: 82vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    position: relative;
  }

  /* Fixed top section: header, meta, action bar */
  .overlay-top {
    padding: 1.25rem 1.5rem 0.75rem;
    flex-shrink: 0;
    border-bottom: 1px solid #e9ecef;
  }

  .overlay-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: 0.4rem;
  }
  .overlay-header h2 { font-size: 17px; font-weight: 700; }

  .overlay-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
    align-items: center;
    font-size: 13px;
    color: #555;
    margin-bottom: 0.75rem;
  }

  /* Action bar */
  .action-bar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.5rem;
  }

  .action-bar-spacer { flex: 1; }

  /* Body: sidebar + content */
  .overlay-body {
    display: flex;
    flex: 1;
    min-height: 0;
  }

  /* Vertical tab sidebar */
  .overlay-tab-sidebar {
    width: 130px;
    flex-shrink: 0;
    border-right: 1px solid #e9ecef;
    padding: 0.5rem 0;
  }

  .overlay-tab-btn {
    display: block;
    width: 100%;
    padding: 0.55rem 1rem;
    text-align: left;
    background: none;
    border: none;
    border-left: 3px solid transparent;
    font-size: 13px;
    color: #555;
    cursor: pointer;
    transition: background 0.1s;
  }

  .overlay-tab-btn.active {
    color: #1a1a1a;
    font-weight: 600;
    border-left-color: #3a3a8c;
    background: #f0f0f8;
  }

  .overlay-tab-btn:hover:not(.active) { background: #f5f5f5; }

  /* Tab content area */
  .overlay-tab-content {
    flex: 1;
    padding: 1rem 1.25rem;
    overflow-y: auto;
    min-height: 0;
  }

  /* MD/PDF toggle pill */
  .view-toggle {
    display: inline-flex;
    border: 1px solid #ddd;
    border-radius: 4px;
    overflow: hidden;
    margin-bottom: 0.75rem;
  }

  .view-toggle button {
    padding: 4px 14px;
    border: none;
    background: #f5f5f5;
    cursor: pointer;
    font-size: 12px;
    font-weight: 600;
    color: #555;
    transition: background 0.1s, color 0.1s;
  }

  .view-toggle button + button { border-left: 1px solid #ddd; }

  .view-toggle button.active {
    background: #1a1a2e;
    color: #fff;
  }

  .view-toggle button:disabled { opacity: 0.4; cursor: not-allowed; }

  /* PDF iframe */
  .overlay-pdf-frame {
    width: 100%;
    height: 500px;
    border: 1px solid #ddd;
    border-radius: 4px;
  }

  /* Markdown viewer */
  .overlay-md-viewer {
    font-family: monospace;
    font-size: 0.8rem;
    white-space: pre-wrap;
    background: #f8f9fa;
    border: 1px solid #e9ecef;
    border-radius: 4px;
    padding: 0.75rem;
    max-height: 500px;
    overflow-y: auto;
    margin: 0;
  }

  /* Prompt overlay — absolute within .overlay-panel */
  .prompt-overlay {
    position: absolute;
    inset: 0;
    background: rgba(0,0,0,0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 200;
    border-radius: 8px;
  }

  .prompt-overlay-panel {
    background: #fff;
    border-radius: 6px;
    padding: 1.25rem;
    width: 90%;
    max-height: 80%;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    box-shadow: 0 4px 24px rgba(0,0,0,0.2);
  }

  .prompt-overlay-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .prompt-overlay-header strong { font-size: 14px; }

  .prompt-overlay-panel pre {
    overflow-y: auto;
    font-size: 12px;
    white-space: pre-wrap;
    background: #f8f9fa;
    border: 1px solid #e9ecef;
    border-radius: 4px;
    padding: 0.75rem;
    max-height: 400px;
    margin: 0;
    flex: 1;
  }

  /* Overview tab description */
  .overlay-description {
    font-size: 13px;
    line-height: 1.6;
    color: #333;
  }

  /* Empty state */
  .overlay-empty-state {
    color: #888;
    font-size: 13px;
    padding: 1rem 0;
  }
  ```

  Remove the old `.overlay-divider` rule entirely — the divider is replaced by the border on `.overlay-top`.

- [ ] **Step 2: Verify no obvious CSS syntax errors**

  Open the dashboard in a browser (`http://localhost:8000`). The page should load without visual breakage to the nav, table, or any existing UI outside the modal. (Modal itself will be broken until Task 6.)

- [ ] **Step 3: Commit**

  ```bash
  git add web/static/style.css
  git commit -m "[feat] Add tabbed modal CSS — sidebar, toggle pill, prompt overlay"
  ```

---

## Task 6: HTML — replace overlay markup with tabbed layout

**Files:**
- Modify: `web/static/index.html`

- [ ] **Step 1: Replace everything inside `<div class="overlay-backdrop" ...>` with the new structure**

  Find the entire `<div class="overlay-backdrop" ...>` block (currently lines 60–141) and replace it with:

  ```html
  <!-- Overlay backdrop -->
  <div class="overlay-backdrop" x-show="selectedJob !== null" @click.self="closeOverlay()">
    <div class="overlay-panel" @keydown.escape.window="closeOverlay()">
      <template x-if="selectedJob">
        <div style="display:flex;flex-direction:column;height:100%">

          <!-- Fixed top: header, meta, action bar -->
          <div class="overlay-top">
            <div class="overlay-header">
              <h2>
                <span x-text="selectedJob.title || '(no title)'"></span>
                <span x-show="generating" style="display:inline-flex;align-items:center;margin-left:0.5rem;font-size:0.85rem;color:#888;font-weight:400;vertical-align:middle">
                  <svg viewBox="0 0 20 20" width="14" height="14" style="margin-right:0.4em;flex-shrink:0;display:block">
                    <g>
                      <circle cx="10" cy="10" r="7" fill="none" stroke="#3a3a3a" stroke-width="2.5" stroke-dasharray="9.5 1.5"/>
                      <circle cx="10" cy="10" r="7" fill="none" stroke="#aaa" stroke-width="2.5" stroke-dasharray="9.5 34.5"/>
                      <animateTransform attributeName="transform" type="rotate"
                        values="-90 10 10;0 10 10;90 10 10;180 10 10"
                        dur="2s" calcMode="discrete" repeatCount="indefinite"/>
                    </g>
                  </svg>
                  <span x-text="generatingLabel"></span>
                </span>
              </h2>
              <span :class="'status-badge ' + statusClass(selectedJob.state)" x-text="selectedJob.state"></span>
            </div>

            <div class="overlay-meta">
              <span x-text="selectedJob.company || ''"></span>
              <span :class="'score-badge ' + scoreClass(selectedJob.final_score)" x-text="pct(selectedJob.final_score)"></span>
              <span x-text="selectedJob.location || ''"></span>
              <span x-text="selectedJob.salary || ''"></span>
            </div>

            <!-- Action bar -->
            <div class="action-bar">

              <!-- Tab-specific actions (left) -->

              <!-- Overview -->
              <template x-if="activeTab === 'overview'">
                <button class="btn" @click="calculateScore()">Calculate Score</button>
              </template>

              <!-- Resume -->
              <template x-if="activeTab === 'resume'">
                <div style="display:contents">
                  <button class="btn" @click="generateResumeMd()" :disabled="!!generating"
                    x-text="selectedJob.resume_md_exists ? 'Regenerate MD' : 'Generate MD'">
                  </button>
                  <button class="btn" @click="generateResumePdf()"
                    :disabled="!!generating || !selectedJob.resume_md_exists"
                    x-text="selectedJob.resume_path ? 'Regenerate PDF' : 'Generate PDF'">
                  </button>
                  <button class="btn" x-show="selectedJob.resume_md_exists"
                    @click="viewPrompt('resume')" :disabled="!!generating">
                    View Prompt
                  </button>
                </div>
              </template>

              <!-- Cover Letter -->
              <template x-if="activeTab === 'cover'">
                <div style="display:contents">
                  <button class="btn" @click="generateCoverMd()" :disabled="!!generating"
                    x-text="selectedJob.cover_md_exists ? 'Regenerate MD' : 'Generate MD'">
                  </button>
                  <button class="btn" @click="generateCoverPdf()"
                    :disabled="!!generating || !selectedJob.cover_md_exists || !selectedJob.resume_path"
                    :title="!selectedJob.resume_path ? 'Generate resume PDF first' : ''"
                    x-text="selectedJob.cover_path ? 'Regenerate PDF' : 'Generate PDF'">
                  </button>
                  <button class="btn" x-show="selectedJob.cover_md_exists"
                    @click="viewPrompt('cover')" :disabled="!!generating">
                    View Prompt
                  </button>
                </div>
              </template>

              <!-- Spacer -->
              <div class="action-bar-spacer"></div>

              <!-- Persistent actions (right) -->
              <a class="btn" :href="selectedJob.url" target="_blank" rel="noopener noreferrer">View Posting</a>

              <button class="btn" @click="markApplied()" :disabled="selectedJob.state === 'applied'">
                Mark as Applied
              </button>

              <template x-if="!deleteConfirm">
                <button class="btn btn-danger" @click="deleteConfirm = true">Delete</button>
              </template>
              <template x-if="deleteConfirm">
                <button class="btn btn-danger-confirm" @click="deleteJob()">Confirm Delete</button>
              </template>
            </div>
          </div>

          <!-- Body: sidebar + tab content -->
          <div class="overlay-body">

            <!-- Vertical tab sidebar -->
            <div class="overlay-tab-sidebar">
              <button class="overlay-tab-btn" :class="{ active: activeTab === 'overview' }"
                @click="switchTab('overview')">Overview</button>
              <button class="overlay-tab-btn" :class="{ active: activeTab === 'resume' }"
                @click="switchTab('resume')">Resume</button>
              <button class="overlay-tab-btn" :class="{ active: activeTab === 'cover' }"
                @click="switchTab('cover')">Cover Letter</button>
            </div>

            <!-- Tab content area -->
            <div class="overlay-tab-content">

              <!-- Overview tab -->
              <div x-show="activeTab === 'overview'">
                <div class="overlay-description" x-html="formatDesc(selectedJob.description)"></div>
              </div>

              <!-- Resume tab -->
              <div x-show="activeTab === 'resume'">
                <p class="overlay-empty-state"
                  x-show="!selectedJob.resume_md_exists && !selectedJob.resume_path">
                  No resume generated yet. Use "Generate MD" to create one.
                </p>
                <div x-show="selectedJob.resume_md_exists || !!selectedJob.resume_path">
                  <div class="view-toggle">
                    <button :class="{ active: resumeView === 'md' }" @click="resumeView = 'md'">MD</button>
                    <button :class="{ active: resumeView === 'pdf' }" @click="resumeView = 'pdf'"
                      :disabled="!selectedJob.resume_path">PDF</button>
                  </div>
                  <div x-show="resumeView === 'md'">
                    <p class="overlay-empty-state" x-show="!resumeMarkdown">Loading…</p>
                    <pre class="overlay-md-viewer" x-show="resumeMarkdown" x-text="resumeMarkdown"></pre>
                  </div>
                  <template x-if="resumeView === 'pdf' && !!selectedJob.resume_path">
                    <iframe class="overlay-pdf-frame"
                      :src="`/api/jobs/${encodeURIComponent(selectedJob.job_key)}/resume`">
                    </iframe>
                  </template>
                </div>
              </div>

              <!-- Cover Letter tab -->
              <div x-show="activeTab === 'cover'">
                <p class="overlay-empty-state"
                  x-show="!selectedJob.cover_md_exists && !selectedJob.cover_path">
                  No cover letter generated yet. Use "Generate MD" to create one.
                </p>
                <div x-show="selectedJob.cover_md_exists || !!selectedJob.cover_path">
                  <div class="view-toggle">
                    <button :class="{ active: coverView === 'md' }" @click="coverView = 'md'">MD</button>
                    <button :class="{ active: coverView === 'pdf' }" @click="coverView = 'pdf'"
                      :disabled="!selectedJob.cover_path">PDF</button>
                  </div>
                  <div x-show="coverView === 'md'">
                    <p class="overlay-empty-state" x-show="!coverMarkdown">Loading…</p>
                    <pre class="overlay-md-viewer" x-show="coverMarkdown" x-text="coverMarkdown"></pre>
                  </div>
                  <template x-if="coverView === 'pdf' && !!selectedJob.cover_path">
                    <iframe class="overlay-pdf-frame"
                      :src="`/api/jobs/${encodeURIComponent(selectedJob.job_key)}/cover`">
                    </iframe>
                  </template>
                </div>
              </div>

            </div><!-- end overlay-tab-content -->
          </div><!-- end overlay-body -->

          <!-- Prompt overlay (absolute within panel) -->
          <div class="prompt-overlay" x-show="promptOverlay !== null" @click.self="promptOverlay = null">
            <div class="prompt-overlay-panel">
              <div class="prompt-overlay-header">
                <strong x-text="promptOverlay && promptOverlay.type === 'resume' ? 'Resume Prompt' : 'Cover Letter Prompt'"></strong>
                <button class="btn" @click="promptOverlay = null">Close</button>
              </div>
              <pre x-text="promptOverlay ? promptOverlay.text : ''"></pre>
            </div>
          </div>

        </div>
      </template>
    </div>
  </div>
  ```

- [ ] **Step 2: Commit**

  ```bash
  git add web/static/index.html
  git commit -m "[feat] Replace overlay HTML with tabbed layout — sidebar, action bar, content area"
  ```

---

## Task 7: JS — extend Alpine.js `dashboard()` with new state and methods

**Files:**
- Modify: `web/static/index.html`

- [ ] **Step 1: Replace the `dashboard()` state object and all methods**

  Find the `<script>` block (starts at `function dashboard() {`) and replace it entirely with:

  ```html
  <script>
  function dashboard() {
    return {
      jobs: [],
      selectedJob: null,
      sortField: 'final_score',
      sortDir: 'desc',
      deleteConfirm: false,
      loadError: null,
      generating: null,
      activeTab: 'overview',
      resumeView: 'md',
      coverView: 'md',
      resumeMarkdown: null,
      coverMarkdown: null,
      promptOverlay: null,

      async init() {
        await this.loadJobs();
        document.addEventListener('click', (e) => {
          if (this.deleteConfirm && !e.target.closest('.action-bar')) {
            this.deleteConfirm = false;
          }
        });
      },

      async loadJobs() {
        try {
          const resp = await fetch('/api/jobs');
          if (!resp.ok) throw new Error('Server error');
          this.jobs = await resp.json();
        } catch {
          this.loadError = 'Failed to load jobs. Is the server running?';
        }
      },

      get sortedJobs() {
        return [...this.jobs].sort((a, b) => {
          let av = a[this.sortField];
          let bv = b[this.sortField];

          if (this.sortField === 'salary') {
            av = parseFloat(String(av || '').replace(/[^0-9.]/g, '')) || 0;
            bv = parseFloat(String(bv || '').replace(/[^0-9.]/g, '')) || 0;
          }

          const nullLast = this.sortDir === 'asc' ? Infinity : -Infinity;
          if (av == null) av = nullLast;
          if (bv == null) bv = nullLast;

          if (av < bv) return this.sortDir === 'asc' ? -1 : 1;
          if (av > bv) return this.sortDir === 'asc' ? 1 : -1;
          return 0;
        });
      },

      setSort(field) {
        if (this.sortField === field) {
          this.sortDir = this.sortDir === 'asc' ? 'desc' : 'asc';
        } else {
          this.sortField = field;
          this.sortDir = field === 'state' ? 'asc' : 'desc';
        }
      },

      selectJob(job) {
        this.selectedJob = { ...job };
        this.deleteConfirm = false;
        this.activeTab = 'overview';
        this.resumeView = 'md';
        this.coverView = 'md';
        this.resumeMarkdown = null;
        this.coverMarkdown = null;
        this.promptOverlay = null;
      },

      closeOverlay() {
        this.selectedJob = null;
        this.deleteConfirm = false;
        this.activeTab = 'overview';
        this.resumeMarkdown = null;
        this.coverMarkdown = null;
        this.promptOverlay = null;
        this.generating = null;
      },

      switchTab(tab) {
        this.activeTab = tab;
        if (tab === 'resume') {
          this.resumeView = 'md';
          if (this.selectedJob.resume_md_exists && this.resumeMarkdown === null) {
            this.fetchResumeMarkdown();
          }
        } else if (tab === 'cover') {
          this.coverView = 'md';
          if (this.selectedJob.cover_md_exists && this.coverMarkdown === null) {
            this.fetchCoverMarkdown();
          }
        }
      },

      get generatingLabel() {
        const map = {
          resume_md: 'Generating resume…',
          resume_pdf: 'Rendering resume PDF…',
          cover_md: 'Generating cover letter…',
          cover_pdf: 'Rendering cover PDF…',
        };
        return this.generating ? (map[this.generating] || 'Working…') : '';
      },

      scoreClass(s) {
        if (s == null) return 'score-none';
        if (s >= 0.8) return 'score-green';
        if (s >= 0.5) return 'score-amber';
        return 'score-red';
      },

      statusClass(state) {
        const map = { pending: 'status-pending', applied: 'status-applied', rejected: 'status-rejected', failed: 'status-failed' };
        return map[state] || 'status-pending';
      },

      pct(v) {
        return v != null ? Math.round(v * 100) + '%' : '—';
      },

      formatDesc(desc) {
        if (!desc) return '<em>No description available.</em>';
        return String(desc)
          .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
          .replace(/\n/g, '<br>');
      },

      _updateJob(updated) {
        const idx = this.jobs.findIndex(j => j.job_key === updated.job_key);
        if (idx !== -1) this.jobs[idx] = updated;
        this.selectedJob = { ...updated };
      },

      async _post(url) {
        const resp = await fetch(url, { method: 'POST' });
        if (!resp.ok) throw new Error(await resp.text());
        return resp.json();
      },

      async fetchResumeMarkdown() {
        try {
          const resp = await fetch(`/api/jobs/${encodeURIComponent(this.selectedJob.job_key)}/resume/markdown`);
          if (!resp.ok) return;
          this.resumeMarkdown = await resp.text();
        } catch { /* silent — user sees "Loading…" */ }
      },

      async fetchCoverMarkdown() {
        try {
          const resp = await fetch(`/api/jobs/${encodeURIComponent(this.selectedJob.job_key)}/cover/markdown`);
          if (!resp.ok) return;
          this.coverMarkdown = await resp.text();
        } catch { /* silent */ }
      },

      async viewPrompt(type) {
        const url = `/api/jobs/${encodeURIComponent(this.selectedJob.job_key)}/${type === 'resume' ? 'resume' : 'cover'}/prompt`;
        try {
          const resp = await fetch(url);
          if (!resp.ok) throw new Error();
          this.promptOverlay = { type, text: await resp.text() };
        } catch { alert('Failed to load prompt.'); }
      },

      async calculateScore() {
        try {
          this._updateJob(await this._post(`/api/jobs/${encodeURIComponent(this.selectedJob.job_key)}/score`));
        } catch { alert('Failed to calculate score.'); }
      },

      async generateResumeMd() {
        this.generating = 'resume_md';
        try {
          this._updateJob(await this._post(`/api/jobs/${encodeURIComponent(this.selectedJob.job_key)}/generate/resume/md`));
          this.resumeMarkdown = null;
          if (this.activeTab === 'resume') await this.fetchResumeMarkdown();
        } catch { alert('Failed to generate resume markdown.'); }
        finally { this.generating = null; }
      },

      async generateResumePdf() {
        this.generating = 'resume_pdf';
        try {
          this._updateJob(await this._post(`/api/jobs/${encodeURIComponent(this.selectedJob.job_key)}/generate/resume/pdf`));
        } catch { alert('Failed to render resume PDF.'); }
        finally { this.generating = null; }
      },

      async generateCoverMd() {
        this.generating = 'cover_md';
        try {
          this._updateJob(await this._post(`/api/jobs/${encodeURIComponent(this.selectedJob.job_key)}/generate/cover/md`));
          this.coverMarkdown = null;
          if (this.activeTab === 'cover') await this.fetchCoverMarkdown();
        } catch { alert('Failed to generate cover letter markdown.'); }
        finally { this.generating = null; }
      },

      async generateCoverPdf() {
        this.generating = 'cover_pdf';
        try {
          this._updateJob(await this._post(`/api/jobs/${encodeURIComponent(this.selectedJob.job_key)}/generate/cover/pdf`));
        } catch { alert('Failed to render cover letter PDF.'); }
        finally { this.generating = null; }
      },

      async markApplied() {
        try {
          const resp = await fetch(`/api/jobs/${encodeURIComponent(this.selectedJob.job_key)}/state`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ state: 'applied' }),
          });
          if (!resp.ok) throw new Error();
          this._updateJob(await resp.json());
        } catch { alert('Failed to mark as applied.'); }
      },

      async deleteJob() {
        const key = this.selectedJob.job_key;
        try {
          const resp = await fetch(`/api/jobs/${encodeURIComponent(key)}`, { method: 'DELETE' });
          if (!resp.ok) throw new Error();
          this.jobs = this.jobs.filter(j => j.job_key !== key);
          this.closeOverlay();
        } catch { alert('Failed to delete job.'); }
      },
    };
  }
  </script>
  ```

- [ ] **Step 2: Commit**

  ```bash
  git add web/static/index.html
  git commit -m "[feat] Add tabbed modal Alpine.js state and methods"
  ```

---

## Task 8: Manual verification

- [ ] **Step 1: Start the server and open the dashboard**

  ```bash
  # From project root:
  python -m uvicorn web.app:app --reload
  ```

  Open `http://localhost:8000`.

- [ ] **Step 2: Verify Overview tab**

  - Click any job row → modal opens
  - Overview tab is selected by default (left sidebar shows "Overview" highlighted)
  - Job description is visible in the content area
  - Action bar shows: Calculate Score | (spacer) | View Posting · Mark as Applied · Delete

- [ ] **Step 3: Verify Resume tab — no MD**

  - Click "Resume" in the sidebar
  - If no MD exists: empty state message shown, action bar shows "Generate MD" (enabled) + "Generate PDF" (disabled)
  - Click "Generate MD" → spinner appears, button label changes to "Regenerate MD" after completion, markdown appears in content area

- [ ] **Step 4: Verify Resume tab — MD exists, no PDF**

  - Toggle pill shows MD (active) | PDF (disabled)
  - Markdown content is visible in the MD viewer
  - Action bar shows "Regenerate MD" · "Generate PDF" (enabled) · "View Prompt"
  - Click "View Prompt" → prompt overlay appears over the modal, scrollable, Close button works

- [ ] **Step 5: Verify Resume tab — MD and PDF exist**

  - Click "Generate PDF" → PDF renders, toggle pill PDF button becomes enabled
  - Click PDF in toggle → iframe loads the PDF

- [ ] **Step 6: Verify Cover Letter tab follows the same pattern**

  - "Generate PDF" remains disabled until resume PDF exists
  - After resume PDF exists, cover MD + PDF generation works correctly

- [ ] **Step 7: Verify persistent actions always visible**

  - Switching between all three tabs keeps View Posting, Mark as Applied, Delete visible on the right

- [ ] **Step 8: Verify modal close / reopen resets state**

  - Close modal (Escape or click backdrop)
  - Reopen same job → lands on Overview tab, no stale markdown cached

- [ ] **Step 9: Final commit**

  ```bash
  git add .
  git commit -m "[chore] Verified tabbed modal — all flows working"
  ```
