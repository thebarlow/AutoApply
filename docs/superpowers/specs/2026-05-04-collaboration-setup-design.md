---
title: Collaboration Setup — README + Setup Script
date: 2026-05-04
status: approved
---

# Collaboration Setup Design

## Scope

Prepare the project for developer collaborators by:
1. Writing a comprehensive quick-start `README.md`
2. Writing a cross-platform `setup.py` setup script
3. Adding error handling to `db/init_db.py`

No .xpi packaging — collaborators load the browser extension manually.

---

## `setup.py`

Cross-platform Python script at the project root. Runs without any dependencies beyond the standard library.

**Steps:**
1. Assert Python >= 3.10; exit with a clear message if not
2. Create `.venv/` using `venv`
3. Run `pip install -r requirements.txt` inside the venv (uses the venv's pip binary)
4. Copy `.env.example` → `.env` if `.env` does not already exist; print a note that the user must add their API key via the Config tab after starting the server
5. Run `python -m db.init_db` using the venv's Python to create tables and seed default config
6. Print next steps (start server command)

**Cross-platform note:** Use `sys.executable` to find the current Python, construct venv pip/python paths using `pathlib.Path` with OS-appropriate suffixes (`Scripts/` on Windows, `bin/` on Linux/macOS).

---

## `db/init_db.py` — Error Handling

Wrap `init_db()` and `seed_default_config()` in try/except. On failure:
- Print a descriptive error message to stderr
- Exit with code 1

Errors to handle explicitly:
- `OperationalError` from SQLAlchemy (DB creation failure, permissions)
- Generic `Exception` as a catch-all with the original message surfaced

---

## `README.md`

**Sections:**

### Prerequisites
- Python 3.10+
- pandoc + xelatex (for PDF generation — pandoc.org/installing.html; xelatex is part of TeX Live on Linux/macOS and MiKTeX on Windows)
- Firefox or Chrome

### Setup
```
git clone <repo>
cd auto_apply
python setup.py
```
Opens with: "This creates a virtual environment, installs dependencies, and initialises the database."

### Starting the Server
```
source .venv/bin/activate   # Linux/macOS
.venv\Scripts\activate      # Windows
uvicorn web.main:app --reload
```
Navigate to `http://127.0.0.1:8000/`

### API Key & LLM Config
Brief paragraph: go to the Config tab → LLM section, enter your API key for Anthropic, OpenAI, OpenRouter, or Gemini, and select the active provider.

### Browser Extension
**Firefox:**
1. Open `about:debugging` → This Firefox → Load Temporary Add-on
2. Select `browser-extension/manifest.json`

**Chrome:**
1. Open `chrome://extensions` → Enable Developer Mode
2. Click "Load unpacked" → select the `browser-extension/` directory

Note: the extension POSTs to `http://localhost:8000` by default. Change this in the extension popup if running the server on a different port.

### Running the Scraper
```
python -m scraper
```
Scrapes Remotive and RemoteOK based on your search config (set in the Config tab). Results appear in the dashboard.

### Config Options
Brief table:

| Section | What it controls |
|---|---|
| Sources | Which API scrapers are enabled (Remotive, RemoteOK) |
| Search | Keyword whitelist/blacklist, max jobs per source |
| LLM | API provider, model, and API key |
| Templates | LaTeX template paths, resume/cover letter prompt templates, social links |
| Scoring | Desirability/fit score weights, auto-reject/approve thresholds |
| Profile | User profile for tailored resume generation |

### Running Tests
```
pytest
```
