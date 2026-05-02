# Config Tab Design (v2)

**Date:** 2026-05-02
**Supersedes:** `2026-04-29-config-tab-design.md`

## Overview

Add a Config page at `/config` with five collapsible sections. Each section has its own Save button. All sections load their data independently on page open via separate API calls.

## File Structure

```
web/
├── static/
│   ├── index.html          (existing — fix Config nav link)
│   ├── config.html         (new)
│   └── style.css           (existing — add active nav, form, section, slider styles)
└── routers/
    ├── jobs.py             (existing)
    ├── scraper.py          (existing)
    └── config.py           (new)

core/
└── scorer.py               (existing — swap anthropic client for openai)

generator/
└── generator.py            (existing — swap anthropic client for openai)
```

## Routing

Add to `web/main.py`:
- `app.include_router(config.router)`
- `GET /config` → serves `config.html`

Nav links in both `index.html` and `config.html` get an `.active` CSS class hardcoded on the current page's link.

## Sections

Sections use native `<details>`/`<summary>` elements. Each has its own Save button and inline status message.

---

### Section 1: API Config

Two sub-groups inside one collapsible section.

**Sources**
Two checkboxes: Remotive, RemoteOK.
- Config table key: `scraper_sources` (comma-separated string of enabled IDs)
- Endpoint: `GET/PUT /api/config/sources` → `{ "remotive": bool, "remoteok": bool }`

**Search**
Three fields:
- Keywords whitelist — text input, comma-separated, split to `list[str]` on save
- Keywords blacklist — text input, comma-separated, split to `list[str]` on save
- Max jobs per source — number input

Config table keys: `keywords_whitelist` (JSON array), `keywords_blacklist` (JSON array), `max_jobs_per_source` (int string).

Endpoint: `GET/PUT /api/config/search` → `{ "keywords_whitelist": list[str], "keywords_blacklist": list[str], "max_jobs_per_source": int }`

Note: `location`, `remote_only`, `full_time_only`, `target_salary_min`, and `benefits_priorities` exist in the Config table and `SearchConfig` dataclass but are not exposed in the UI — they are not wired to any API.

---

### Section 2: Templates

Three sub-groups.

**LaTeX Templates**
Two text inputs: path to resume `.tex` file, path to cover `.tex` file.
- Default values: `generator/resume_template.tex`, `generator/cover_template.tex`
- `generator.py` currently hardcodes these paths — move to Config table lookup with hardcoded path as fallback default.
- Config table keys: `resume_template_path`, `cover_template_path`

**Prompt Templates**
Two textareas: resume prompt, cover prompt.
- Already stored in Config table as `resume_prompt_template`, `cover_prompt_template`.

**Social Links**
Three text inputs: GitHub, LinkedIn, website.
- Config table keys: `resume_github`, `resume_linkedin`, `resume_website`

Endpoint: `GET/PUT /api/config/templates` → `{ "resume_template_path": str, "cover_template_path": str, "resume_prompt_template": str, "cover_prompt_template": str, "github": str, "linkedin": str, "website": str }`

---

### Section 3: User Profile

Collapsed, fully disabled/grayed out. Single static note:

> "Coming soon — will accept a PDF or Markdown file and convert it to a structured user profile."

No inputs. No API endpoint. No backend work.

---

### Section 4: Scoring

**Weight control**

A single linked widget for desirability weight (`w1`) and fitness weight (`w2`):

```
Desirability [0.50] [————|————] [0.50] Fitness
```

- Any of the three controls (either textbox or the slider) drives the other two
- Adjustments maintain `w1 + w2 = 1.0` automatically
- Textboxes: number input, step 0.01, range 0.0–1.0
- Slider: range 0.0–1.0, represents `w2` (fitness); `w1 = 1 - slider_value`. Moving right increases fitness weight; moving left increases desirability weight.
- Block save if `w1 + w2 ≠ 1.0` (failsafe — should not trigger from normal interaction)

**Threshold inputs**

Two number inputs (step 0.01, range 0.0–1.0):
- Auto-reject threshold — jobs scoring below this → `REJECTED`
- Auto-approve threshold — jobs scoring at or above this → `APPROVED`

Block save if reject threshold ≥ approve threshold.

Config table keys: `w1`, `w2`, `auto_reject_threshold`, `auto_approve_threshold` (all float strings, default `"0.5"`).

Endpoint: `GET/PUT /api/config/scoring` → `{ "w1": float, "w2": float, "auto_reject_threshold": float, "auto_approve_threshold": float }`

---

### Section 5: LLM Providers

A list of provider configurations. Multiple providers can be declared; exactly one is active at a time.

**Provider row layout:**
```
(●) [Provider ▾] [Model text input] [API Key ••••••] [✕]
```

- Radio button — selects the active provider (only one can be selected)
- Provider dropdown — options: OpenRouter, Anthropic, OpenAI, Gemini. Selection determines `base_url` (stored internally, not shown):
  - OpenRouter: `https://openrouter.ai/api/v1`
  - Anthropic: `https://api.anthropic.com/v1`
  - OpenAI: `https://api.openai.com/v1`
  - Gemini: `https://generativelanguage.googleapis.com/v1beta/openai`
- Model — free text input (e.g. `anthropic/claude-sonnet-4-6`, `gpt-4o`)
- API key — password input. Placeholder `***` if a key exists for this provider; blank if not. Leave blank to preserve the existing key.
- Remove button (✕) — removes the row. Does NOT delete the corresponding key from `.env`; the key is left in place in case the provider is re-added later.

**"Add LLM Provider" button** appends a new blank row.

**Storage:**
- Provider configs (name, base_url, model) stored in Config table as JSON array under key `llm_providers`
- Active provider name stored in Config table under key `llm_active_provider`
- API keys stored in `.env` as `LLM_KEY_<PROVIDER_NAME>` (e.g. `LLM_KEY_OPENROUTER`, `LLM_KEY_ANTHROPIC`)

**Endpoints:**
- `GET /api/config/llm` → `{ "providers": [{ "name": str, "base_url": str, "model": str, "has_key": bool }], "active": str }`
- `PUT /api/config/llm` → `{ "providers": [{ "name": str, "model": str, "api_key": str | "" }], "active": str }`. Non-empty `api_key` values are written to `.env`; empty strings leave the existing key untouched.

---

## Backend Core Changes

**`scorer.py` and `generator.py`**

Replace `anthropic.Anthropic()` with `openai.OpenAI(api_key=..., base_url=...)`. At runtime both modules load the active provider config from the DB and read the corresponding key from the environment:

```python
provider = get_active_provider(db)         # reads llm_providers + llm_active_provider
api_key = os.getenv(f"LLM_KEY_{provider.name.upper()}")
client = openai.OpenAI(api_key=api_key, base_url=provider.base_url)
```

Response parsing changes from `message.content[0].text` (Anthropic SDK) to `response.choices[0].message.content` (OpenAI SDK).

Model name is read from the active provider's `model` field — no longer hardcoded.

Add `openai` to project dependencies.

---

## CSS Additions

- `.active` nav link style (white + underline indicator)
- `<details>`/`<summary>` section styling (border, spacing, cursor)
- Form layout: label/input pairs, section headings (`h2`), textarea sizing
- Linked slider widget layout (flexbox row with labels on each end)
- Disabled section overlay (grayed out, `pointer-events: none`)
