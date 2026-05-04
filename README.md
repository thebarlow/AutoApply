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
