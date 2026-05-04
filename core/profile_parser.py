from __future__ import annotations

import io
import json
import re

import pdfplumber
from sqlalchemy.orm import Session

from core.llm import get_openai_client

_SYSTEM_PROMPT = """\
You are a resume parser. Extract structured data from the resume text the user provides.
Return ONLY a JSON object — no markdown fences, no prose, no explanation.

Use this exact schema:
{
  "name": "string",
  "email": "string",
  "phone": "string",
  "location": "string",
  "skills": ["string"],
  "work_history": [
    {"title": "string", "company": "string", "start": "string", "end": "string", "summary": "string"}
  ],
  "education": [
    {"institution": "string", "degree": "string", "field": "string", "graduated": "string", "gpa": number}
  ]
}

Rules:
- Use empty string "" for missing string fields.
- Use 0.0 for missing gpa.
- Use [] for missing list fields.
- For start/end dates use the format found in the resume (e.g. "2022-01" or "Jan 2022").
- "end" should be "Present" if the role is current.
"""

# resume_path and md_path are set by the caller after file upload, not by the LLM
_DEFAULTS: dict[str, object] = {
    "target_salary_min": None,
    "target_salary_max": None,
    "target_roles": [],
    "resume_path": "",
    "md_path": "",
}


def markdown_to_profile(md_text: str, db: Session) -> dict:
    """Parse resume text into a structured profile dict using the active LLM provider."""
    client, model = get_openai_client(db)

    response = client.chat.completions.create(
        model=model,
        temperature=0,
        timeout=30,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": md_text},
        ],
    )

    raw = response.choices[0].message.content or ""

    # Strip markdown fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw)

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM returned invalid JSON: {exc}") from exc

    return {**_DEFAULTS, **parsed}


def pdf_to_markdown(pdf_bytes: bytes) -> str:
    """Convert raw PDF bytes to a Markdown string."""
    if not pdf_bytes:
        return ""
    lines: list[str] = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                for line in text.splitlines():
                    stripped = line.strip()
                    if not stripped:
                        lines.append("")
                        continue
                    if stripped.isupper() and 2 <= len(stripped.split()) < 8:
                        lines.append(f"## {stripped.title()}")
                    elif stripped.startswith(("•", "·", "-", "*")):
                        lines.append(f"- {stripped.lstrip('•·-* ')}")
                    else:
                        lines.append(stripped)
    except Exception as exc:
        raise ValueError(f"Could not parse PDF: {exc}") from exc
    return "\n".join(lines)
