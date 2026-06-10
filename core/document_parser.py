"""Inverse of ``core/document_assembler``: parse canonical résumé/cover Markdown
back into structured documents. Used to backfill ``documents`` rows for jobs
generated before structured storage existed (or where it was never persisted).

The Markdown format is the one ``document_assembler`` emits, so parsing is
deterministic. Header and education are taken from the YAML front matter (more
reliable than re-parsing the body). Best-effort: malformed input yields an empty
document rather than raising.
"""
from __future__ import annotations

import re

import yaml

from core.document_assembler import resume_section_order
from core.schemas import (
    CoverDocument,
    EducationItem,
    ResumeDocument,
    ResumeExperience,
    ResumeHeader,
    ResumeProject,
    ResumeSkillGroup,
    SignOff,
)


def _split_frontmatter(md: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body). Empty dict if no/invalid front matter."""
    if not md.startswith("---"):
        return {}, md
    end = md.find("\n---", 3)
    if end == -1:
        return {}, md
    fm_text = md[3:end]
    body_start = end + 4
    if body_start < len(md) and md[body_start] == "\n":
        body_start += 1
    try:
        data = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    return data, md[body_start:]


def _header_from_frontmatter(fm: dict) -> ResumeHeader:
    return ResumeHeader(
        name=str(fm.get("name", "") or ""),
        email=str(fm.get("email", "") or ""),
        phone=str(fm.get("phone", "") or ""),
        location=str(fm.get("location", "") or ""),
        github=str(fm.get("github", "") or ""),
        linkedin=str(fm.get("linkedin", "") or ""),
        website=str(fm.get("website", "") or ""),
    )


def _education_from_frontmatter(fm: dict) -> list[EducationItem]:
    out: list[EducationItem] = []
    for ed in fm.get("education", []) or []:
        if not isinstance(ed, dict):
            continue
        gpa = ed.get("gpa", 0)
        try:
            gpa = float(gpa)
        except (TypeError, ValueError):
            gpa = 0
        out.append(EducationItem(
            institution=str(ed.get("institution", "") or ""),
            degree=str(ed.get("degree", "") or ""),
            field=str(ed.get("field", "") or ""),
            graduated=str(ed.get("graduated", "") or ""),
            gpa=gpa,
        ))
    return out


def _sections(body: str) -> dict[str, str]:
    """Split a body into {section_title: section_text} keyed by ``## Title``."""
    out: dict[str, str] = {}
    current = None
    buf: list[str] = []
    for line in body.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            if current is not None:
                out[current] = "\n".join(buf).strip()
            current = m.group(1).strip()
            buf = []
        elif current is not None:
            buf.append(line)
    if current is not None:
        out[current] = "\n".join(buf).strip()
    return out


_DATE_SEP = re.compile(r"\s*[–—-]\s*")
# A line that starts a new experience entry: either a '### ' heading (assembler
# format) or a standalone fully-bold line (legacy LLM format wraps each entry's
# heading in ** ** instead of using ###). Hard-break trailing spaces are tolerated.
_EXP_HEADING_HASH = re.compile(r"^###\s+(?P<head>.+?)\s*$")
_EXP_HEADING_BOLD = re.compile(r"^\*\*(?P<head>.+?)\*\*\s*$")


def _parse_experience_heading(head: str) -> tuple[str, str, str, str]:
    """Split an experience heading into (title, company, start, end).

    Handles both the canonical assembler format ``Title, Company (dates)`` and the
    legacy ``Title at Company (dates)`` form. Surrounding bold markers are stripped.
    The title/company split prefers the first comma (titles don't contain commas,
    companies can); falling back to the first `` at `` token when no comma exists.
    """
    head = head.strip()
    # Strip surrounding bold markers, e.g. "**Instructor at Mathnasium (2023)**".
    bold = re.match(r"^\*\*(.+?)\*\*$", head)
    if bold:
        head = bold.group(1).strip()
    m_dates = re.search(r"\s*\(([^)]*)\)\s*$", head)
    dates = m_dates.group(1).strip() if m_dates else ""
    base = head[: m_dates.start()] if m_dates else head
    base = base.strip()
    idx = base.find(",")
    if idx != -1:
        title, company = base[:idx].strip(), base[idx + 1:].strip()
    else:
        at = re.search(r"\s+at\s+", base)
        if at:
            title, company = base[: at.start()].strip(), base[at.end():].strip()
        else:
            title, company = base, ""
    start = end = ""
    if dates:
        parts = _DATE_SEP.split(dates, maxsplit=1)
        start = parts[0].strip()
        end = parts[1].strip() if len(parts) > 1 else ""
    return title, company, start, end


def _parse_experience(text: str) -> list[ResumeExperience]:
    """Parse the Experience section body into a list of ResumeExperience entries.

    Each entry begins at a heading line — either ``### ...`` or a standalone bold
    line — and runs until the next heading. This tolerates the legacy LLM format
    where only the first entry used ``###`` and the rest used bold-only headings.

    Args:
        text: The raw text content of the Experience section (below ``## Experience``).

    Returns:
        Parsed list of experience entries.
    """
    out: list[ResumeExperience] = []
    cur_head: str | None = None
    desc_lines: list[str] = []

    def flush() -> None:
        if cur_head is None:
            return
        title, company, start, end = _parse_experience_heading(cur_head)
        out.append(ResumeExperience(
            title=title, company=company, start=start, end=end,
            description="\n".join(desc_lines).strip(),
        ))

    for line in text.splitlines():
        stripped = line.strip()
        m = _EXP_HEADING_HASH.match(stripped) or _EXP_HEADING_BOLD.match(stripped)
        if m:
            flush()
            cur_head = m.group("head").strip()
            desc_lines = []
        elif cur_head is not None:
            desc_lines.append(line)
    flush()
    return out


def _parse_projects(text: str) -> list[ResumeProject]:
    """Parse the Projects section body into a list of ResumeProject entries.

    Each project is a single line. Both the canonical ``**Name**: desc`` and the
    legacy ``**Name:** desc`` (colon inside the bold) forms are accepted; trailing
    hard-break spaces are ignored. Lines with no bold name become description-only.

    Args:
        text: The raw text content of the Projects section.

    Returns:
        Parsed list of project entries.
    """
    out: list[ResumeProject] = []
    for line in [ln.strip() for ln in text.splitlines() if ln.strip()]:
        # Try colon-inside-bold first (**Name:** desc), then colon-outside (**Name**: desc).
        m = (re.match(r"^\*\*(?P<name>.+?):\*\*\s*(?P<desc>.*)$", line)
             or re.match(r"^\*\*(?P<name>.+?)\*\*:?\s*(?P<desc>.*)$", line))
        if m:
            out.append(ResumeProject(name=m.group("name").strip(), description=m.group("desc").strip()))
        else:
            out.append(ResumeProject(name="", description=line))
    return out


def _parse_skills(text: str) -> list[ResumeSkillGroup]:
    """Parse the Skills section body into a list of ResumeSkillGroup entries.

    Args:
        text: The raw text content of the Skills section.

    Returns:
        Parsed list of skill groups.
    """
    out: list[ResumeSkillGroup] = []
    # Each line is a single skill group — one line per group, no wrapping.
    for line in [ln.strip() for ln in text.splitlines() if ln.strip()]:
        # Assembler emits: **category:** item1, item2
        m = re.match(r"^\*\*(?P<cat>.+?):\*\*\s*(?P<items>.*)$", line)
        if m:
            items = [s.strip() for s in m.group("items").split(",") if s.strip()]
            out.append(ResumeSkillGroup(category=m.group("cat").strip(), items=items))
    return out


def reconstruct_resume_document_from_markdown(md: str) -> ResumeDocument:
    """Best-effort reconstruction of a ResumeDocument from assembled Markdown.

    Args:
        md: Canonical Markdown string (with optional YAML front matter) as
            produced by ``assemble_resume_markdown``.

    Returns:
        A ``ResumeDocument`` populated from the parsed content. Malformed or
        missing sections yield empty/default values rather than raising.
    """
    fm, body = _split_frontmatter(md)
    sections = _sections(body)
    doc = ResumeDocument(
        header=_header_from_frontmatter(fm),
        education=_education_from_frontmatter(fm),
        profile_summary=sections.get("Profile", "").strip(),
        experience=_parse_experience(sections.get("Experience", "")),
        projects=_parse_projects(sections.get("Projects", "")),
        skills=_parse_skills(sections.get("Skills", "")),
    )
    doc.section_order = resume_section_order(doc)
    return doc


def reconstruct_cover_document_from_markdown(md: str) -> CoverDocument:
    """Reconstruct a CoverDocument: header from front matter, body = markdown body.

    Args:
        md: Canonical Markdown string (with optional YAML front matter) as
            produced by ``assemble_cover_markdown``.

    Returns:
        A ``CoverDocument`` with header snapshot and body prose.
    """
    fm, body = _split_frontmatter(md)
    header = _header_from_frontmatter(fm)
    return CoverDocument(header=header, body=body.strip(), signoff=SignOff(name=header.name))
