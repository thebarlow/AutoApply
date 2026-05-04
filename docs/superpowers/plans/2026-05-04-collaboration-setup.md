# Collaboration Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prepare the project for developer collaborators with a comprehensive README, a cross-platform setup script, and error handling in the DB init script.

**Architecture:** Three independent file changes — `db/init_db.py` gets error handling, `setup.py` is created at the project root, and `README.md` is rewritten. No new modules or dependencies needed.

**Tech Stack:** Python standard library only (`venv`, `subprocess`, `shutil`, `sys`, `pathlib`), SQLAlchemy `OperationalError`.

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Modify | `db/init_db.py` | Wrap setup calls in try/except; exit 1 on failure |
| Create | `setup.py` | Cross-platform dev environment bootstrap |
| Modify | `README.md` | Full quick-start documentation |

---

### Task 1: Add error handling to `db/init_db.py`

**Files:**
- Modify: `db/init_db.py`

- [ ] **Step 1: Open `db/init_db.py` and replace its contents**

```python
"""One-time setup script: create tables and seed default config."""
import sys

from sqlalchemy.exc import OperationalError

from db.database import init_db, SessionLocal
from db.seed import seed_default_config

if __name__ == "__main__":
    try:
        init_db()
    except OperationalError as e:
        print(f"[init_db] Failed to create tables: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[init_db] Unexpected error during table creation: {e}", file=sys.stderr)
        sys.exit(1)

    db = SessionLocal()
    try:
        seed_default_config(db)
        print("Database initialised and default config seeded.")
    except OperationalError as e:
        print(f"[init_db] Failed to seed config: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[init_db] Unexpected error during config seeding: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()
```

- [ ] **Step 2: Verify it still runs without error**

```
python -m db.init_db
```

Expected output:
```
Database initialised and default config seeded.
```

(If the DB already exists, SQLAlchemy's `create_all` is idempotent — it won't error.)

- [ ] **Step 3: Commit**

```bash
git add db/init_db.py
git commit -m "[fix] Add error handling to db/init_db.py"
```

---

### Task 2: Create `setup.py`

**Files:**
- Create: `setup.py`

- [ ] **Step 1: Create `setup.py` at the project root**

```python
"""Cross-platform developer setup script."""
import shutil
import subprocess
import sys
from pathlib import Path

MIN_PYTHON = (3, 10)
ROOT = Path(__file__).parent
VENV = ROOT / ".venv"


def _venv_python() -> Path:
    if sys.platform == "win32":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def _venv_pip() -> Path:
    if sys.platform == "win32":
        return VENV / "Scripts" / "pip.exe"
    return VENV / "bin" / "pip"


def _run(*args: str) -> None:
    result = subprocess.run(args)
    if result.returncode != 0:
        print(f"\n[setup] Command failed: {' '.join(args)}", file=sys.stderr)
        sys.exit(result.returncode)


def main() -> None:
    if sys.version_info < MIN_PYTHON:
        print(
            f"[setup] Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ required "
            f"(you have {sys.version_info.major}.{sys.version_info.minor})",
            file=sys.stderr,
        )
        sys.exit(1)

    print("[setup] Creating virtual environment...")
    _run(sys.executable, "-m", "venv", str(VENV))

    print("[setup] Installing dependencies...")
    _run(str(_venv_pip()), "install", "-r", "requirements.txt")

    env_file = ROOT / ".env"
    env_example = ROOT / ".env.example"
    if not env_file.exists() and env_example.exists():
        shutil.copy(env_example, env_file)
        print("[setup] Created .env from .env.example")
        print("[setup] NOTE: Add your LLM API key via the Config tab after starting the server.")

    print("[setup] Initialising database...")
    _run(str(_venv_python()), "-m", "db.init_db")

    activate = (
        r".venv\Scripts\activate" if sys.platform == "win32" else "source .venv/bin/activate"
    )
    print("\n[setup] Done. Next steps:")
    print(f"  {activate}")
    print("  uvicorn web.main:app --reload")
    print("  Open http://127.0.0.1:8000/")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the setup script to verify it works end-to-end**

```
python setup.py
```

Expected output (approximate):
```
[setup] Creating virtual environment...
[setup] Installing dependencies...
[setup] Initialising database...
Database initialised and default config seeded.

[setup] Done. Next steps:
  ...activate command...
  uvicorn web.main:app --reload
  Open http://127.0.0.1:8000/
```

If `.venv` already exists, delete it first to test from scratch: `rm -rf .venv` (Linux/macOS) or `Remove-Item -Recurse -Force .venv` (Windows).

- [ ] **Step 3: Commit**

```bash
git add setup.py
git commit -m "[feat] Add cross-platform setup.py"
```

---

### Task 3: Rewrite `README.md`

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace the contents of `README.md`**

```markdown
# auto_apply

Semi-automated job scraping, tailored resume generation, and application management.

---

## Prerequisites

- **Python 3.10+**
- **pandoc** — [pandoc.org/installing.html](https://pandoc.org/installing.html)
- **xelatex** — part of [TeX Live](https://tug.org/texlive/) (Linux/macOS) or [MiKTeX](https://miktex.org/) (Windows). Required for PDF generation.
- **Firefox or Chrome**

---

## Setup

```bash
git clone <repo-url>
cd auto_apply
python setup.py
```

This creates a virtual environment at `.venv/`, installs dependencies, and initialises the SQLite database.

---

## Starting the Server

```bash
# Linux/macOS
source .venv/bin/activate

# Windows
.venv\Scripts\activate

uvicorn web.main:app --reload
```

Navigate to [http://127.0.0.1:8000/](http://127.0.0.1:8000/)

---

## API Key & LLM Config

Open the **Config** tab in the dashboard and go to the **LLM** section. Enter your API key for your chosen provider (Anthropic, OpenAI, OpenRouter, or Gemini) and select it as the active provider.

---

## Browser Extension

The extension scrapes job listings from LinkedIn and Indeed and sends them to the dashboard.

**Firefox:**
1. Open `about:debugging` → This Firefox → Load Temporary Add-on
2. Select `browser-extension/manifest.json`

**Chrome:**
1. Open `chrome://extensions` → enable **Developer Mode**
2. Click **Load unpacked** → select the `browser-extension/` directory

The extension POSTs to `http://localhost:8000` by default. If you run the server on a different port, update the base URL in the extension popup.

---

## Running the Scraper

```bash
python -m scraper
```

Scrapes Remotive and RemoteOK based on your search config. Results appear in the dashboard. To run a specific source:

```bash
python -m scraper --source remotive
python -m scraper --source remoteok
```

---

## Config Options

| Section | What it controls |
|---|---|
| Sources | Which API scrapers are enabled (Remotive, RemoteOK) |
| Search | Keyword whitelist/blacklist, max jobs per source |
| LLM | API provider, model, and API key |
| Templates | LaTeX template paths, resume/cover letter prompt templates, social links |
| Scoring | Desirability/fit score weights, auto-reject/approve thresholds |
| Profile | User profile used for tailored resume and cover letter generation |

---

## Running Tests

```bash
pytest
```
```

- [ ] **Step 2: Verify the README renders correctly**

Open `README.md` in your editor or GitHub preview and confirm all sections appear, code blocks are properly fenced, and the table renders.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "[docs] Rewrite README with quick-start guide for collaborators"
```
