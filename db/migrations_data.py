"""Idempotent data migrations for editable, DB-backed content (prompts)."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

_DEFAULTS_DIR = Path(__file__).resolve().parent.parent / "prompts" / "defaults"

# Exact v1 shipped content of resume_parse.md — the upgrade-eligibility key.
# Profiles whose resume_parse prompt equals this (whitespace-normalized) are on
# the stock prompt and safe to upgrade; anything else is user-customized.
_V1_BASELINE = """\
You parse a Master Resume into a structured JSON profile.

The user message contains the full resume text (Markdown or extracted PDF text). Extract all available information and emit it as a single JSON object matching the schema below.

# Output Rules
- Output ONLY raw JSON. No preamble, no explanation, no code fences.
- Every key in the schema MUST be present. Use `""` for missing strings, `[]` for missing lists, `null` for missing numbers.
- Do not invent facts. If a field is not in the resume, leave it empty/null.
- Preserve the resume's wording for summaries and bullets — do not rewrite or embellish.
- Normalize dates to `YYYY-MM` where possible. Use `"Present"` for current roles. Use `YYYY` if only year is given.
- URLs: strip `https://` and `http://` prefixes only if the source did; otherwise keep as-is.
- Phone: keep the format used in the resume.
- `gpa`: number (e.g. `3.85`), or `0` if not listed.

# Schema
```json
{
  "first_name": "",
  "last_name": "",
  "hero": "",
  "email": "",
  "phone": "",
  "location": "",
  "linkedin": "",
  "github": "",
  "website": "",
  "skills": ["string", "..."],
  "work_history": [
    {
      "company": "",
      "title": "",
      "start": "",
      "end": "",
      "summary": ""
    }
  ],
  "education": [
    {
      "institution": "",
      "degree": "",
      "field": "",
      "graduated": "",
      "gpa": 0
    }
  ],
  "projects": [
    {
      "name": "",
      "description": "",
      "url": "",
      "technologies": ["string", "..."]
    }
  ],
  "target_roles": ["string", "..."],
  "target_salary_min": null,
  "target_salary_max": null
}
```

# Field Guidance
- **hero**: A 1-line tagline / headline / professional summary opener (e.g. "Backend Engineer specializing in distributed systems"). If the resume has a multi-sentence summary, use only the first sentence or a tight condensation. Leave `""` if no clear tagline exists.
- **skills**: Flat list of individual skills/tools/technologies. Split grouped lines like "Languages: Python, Go, Rust" into `["Python", "Go", "Rust"]`. Deduplicate.
- **work_history**: Order most-recent first. `summary` should concatenate the role's bullets/description into a single string, preserving bullet markers (`- `) and newlines.
- **education**: Order most-recent first. `degree` = short form ("B.S.", "M.S.", "Ph.D."). `field` = field of study only ("Computer Science"), no degree prefix.
- **projects**: Personal/side projects, not work projects. `technologies` is a flat list of tools used. If the resume doesn't separate projects from work, leave `[]`.
- **target_roles** / **target_salary_min** / **target_salary_max**: Only populate if the resume explicitly states target roles or salary expectations. Otherwise `[]` and `null`.\
"""


def _norm(s: str) -> str:
    return "\n".join(line.rstrip() for line in (s or "").strip().splitlines())


def upgrade_resume_parse_prompt(db: Session) -> int:
    """Reseed the resume_parse prompt to v2 for stock (non-customized) profiles.

    Updates the PromptDefault row to the current file content, then upgrades
    every profile Prompt of type ``resume_parse`` whose content matches the v1
    baseline. User-edited prompts are left untouched. Idempotent.

    Returns:
        Number of profile prompt rows upgraded.
    """
    from db.database import Prompt, PromptDefault

    v2 = (_DEFAULTS_DIR / "resume_parse.md").read_text(encoding="utf-8")
    default = db.query(PromptDefault).filter_by(type_key="resume_parse").first()
    if default is not None:
        default.content = v2
    upgraded = 0
    baseline = _norm(_V1_BASELINE)
    for row in db.query(Prompt).filter_by(type_key="resume_parse").all():
        if _norm(row.content) == baseline:
            row.content = v2
            upgraded += 1
    db.commit()
    return upgraded
