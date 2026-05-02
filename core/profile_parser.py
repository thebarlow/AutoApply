from __future__ import annotations

import re


def markdown_to_profile(md_text: str) -> dict:
    profile = {
        "name": "",
        "email": "",
        "phone": "",
        "location": "",
        "skills": [],
        "work_history": [],
        "education": [],
        "target_salary_min": None,
        "target_salary_max": None,
        "target_roles": [],
        "resume_path": "",
    }

    email_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", md_text)
    if email_match:
        profile["email"] = email_match.group()

    phone_match = re.search(r"(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}", md_text)
    if phone_match:
        profile["phone"] = phone_match.group().strip()

    for line in md_text.splitlines():
        stripped = line.strip()
        if (
            stripped
            and not stripped.startswith("#")
            and not re.search(r"[@\d|]", stripped)
            and len(stripped.split()) <= 5
        ):
            profile["name"] = stripped
            break

    sections = _split_sections(md_text)

    for key in ("skills", "technical skills", "core competencies"):
        if key in sections:
            profile["skills"] = _extract_list_items(sections[key])
            break

    for key in ("experience", "work history", "work experience", "employment"):
        if key in sections:
            profile["work_history"] = _extract_work_history(sections[key])
            break

    if "education" in sections:
        profile["education"] = _extract_education(sections["education"])

    return profile


def _split_sections(md_text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current_key: str | None = None
    current_lines: list[str] = []

    for line in md_text.splitlines():
        heading = re.match(r"^#{1,3}\s+(.+)", line)
        if heading:
            if current_key is not None:
                sections[current_key] = "\n".join(current_lines)
            current_key = heading.group(1).strip().lower()
            current_lines = []
        elif current_key is not None:
            current_lines.append(line)

    if current_key is not None:
        sections[current_key] = "\n".join(current_lines)

    return sections


def _extract_list_items(text: str) -> list[str]:
    items: list[str] = []
    for line in text.splitlines():
        line = line.strip().lstrip("-•·* ")
        if not line:
            continue
        if "," in line:
            items.extend(p.strip() for p in line.split(",") if p.strip())
        else:
            items.append(line)
    return items


def _extract_work_history(text: str) -> list[dict]:
    entries: list[dict] = []
    pattern = re.compile(
        r"^(?P<title>[^|@\n]+?)\s+at\s+(?P<company>[^(\n]+?)\s*"
        r"\((?P<start>[\w-]+)\s*[–\-]\s*(?P<end>[\w-]+)\)",
        re.MULTILINE,
    )
    matches = list(pattern.finditer(text))
    for i, m in enumerate(matches):
        summary_start = m.end()
        summary_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        summary_lines = [
            ln.strip().lstrip("-•·* ")
            for ln in text[summary_start:summary_end].splitlines()
            if ln.strip()
        ]
        entries.append({
            "title": m.group("title").strip(),
            "company": m.group("company").strip(),
            "start": m.group("start").strip(),
            "end": m.group("end").strip(),
            "summary": " ".join(summary_lines),
        })
    return entries


def _extract_education(text: str) -> list[dict]:
    entries: list[dict] = []
    degree_pattern = re.compile(
        r"(?P<degree>B\.?S\.?|B\.?A\.?|M\.?S\.?|M\.?A\.?|Ph\.?D\.?|Bachelor|Master|Associate)"
        r"[^\n,]*?(?:\s+in\s+(?P<field>[^,\n]+?))?\s*,\s*"
        r"(?P<institution>[^(\n,]+?)\s*\(?(?P<graduated>\d{4})\)?",
        re.IGNORECASE,
    )
    gpa_pattern = re.compile(r"GPA[:\s]+(\d+\.\d+)", re.IGNORECASE)
    for m in degree_pattern.finditer(text):
        window = text[m.start(): m.start() + 200]
        gpa_match = gpa_pattern.search(window)
        entries.append({
            "institution": m.group("institution").strip().rstrip(","),
            "degree": m.group("degree").strip(),
            "field": (m.group("field") or "").strip(),
            "graduated": m.group("graduated"),
            "gpa": float(gpa_match.group(1)) if gpa_match else 0.0,
        })
    return entries


def pdf_to_markdown(pdf_bytes: bytes) -> str:
    raise NotImplementedError
