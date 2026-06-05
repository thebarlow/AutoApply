# core/ats_gate.py
"""ATS parseability gate.

Two layers over a rendered résumé PDF:
  * mechanical (deterministic) — hard-block; compares extracted text to the
    stored ResumeDocument (the source of truth).
  * semantic (LLM round-trip) — advisory; never blocks.

The mechanical layer is pure: it operates on an already-extracted ``PdfText``
and a ``ResumeDocument``, so it needs no PDF library or DB to test.
"""
from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from core.schemas import AtsIssue, AtsReport, AtsParsedFields, PdfText, ResumeDocument


def extract_text(pdf_path: str | Path) -> PdfText:
    """Extract the concatenated text layer of a PDF, plus per-line text.

    Args:
        pdf_path: Path to a rendered PDF.

    Returns:
        PdfText with the full text and a flat list of non-empty lines, in
        page-then-reading order as pdfplumber yields them.
    """
    parts: list[str] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    full = "\n".join(parts)
    lines = [ln.strip() for ln in full.splitlines() if ln.strip()]
    return PdfText(text=full, lines=lines)


# Minimal synonym map for skill-survival matching. Lowercased keys → variants.
_SKILL_SYNONYMS: dict[str, list[str]] = {
    "nlp": ["natural language processing"],
    "natural language processing": ["nlp"],
    "javascript": ["js"],
    "js": ["javascript"],
    "postgresql": ["postgres"],
    "postgres": ["postgresql"],
}


def _present(term: str, haystack_lower: str) -> bool:
    """Case-insensitive literal-or-synonym substring match."""
    t = term.strip().lower()
    if not t:
        return False
    if t in haystack_lower:
        return True
    return any(syn in haystack_lower for syn in _SKILL_SYNONYMS.get(t, []))


def check_mechanical(
    pt: PdfText,
    doc: ResumeDocument,
    required_skills: list[str],
    preferred_skills: list[str],
    user_skills: list[str],
) -> list[AtsIssue]:
    """Deterministic ATS checks comparing extracted PDF text to the document.

    Args:
        pt: Extracted PDF text.
        doc: The stored ResumeDocument (ground truth).
        required_skills: job.ext_required_skills, split to a list.
        preferred_skills: job.ext_preferred_skills, split to a list.
        user_skills: the candidate's skills (user.skills).

    Returns:
        A list of AtsIssue. Critical issues hard-block the applied transition.
    """
    issues: list[AtsIssue] = []
    text = pt.text
    low = text.lower()

    # no_text_layer — empty/near-empty text means an image-only/unselectable PDF.
    if len(text.strip()) < 10:
        issues.append(AtsIssue(layer="mechanical", severity="critical",
                               code="no_text_layer",
                               message="PDF has no usable text layer (image-only or unselectable)."))
        return issues  # nothing else is meaningful without text

    # contact_missing — each non-empty header field must appear verbatim.
    for label, value in (("name", doc.header.name), ("email", doc.header.email),
                         ("phone", doc.header.phone)):
        v = (value or "").strip()
        if v and v.lower() not in low:
            issues.append(AtsIssue(layer="mechanical", severity="critical",
                                   code="contact_missing",
                                   message=f"Header {label} '{v}' not found in extracted text."))

    # contact_order — email/phone/location must appear in document order.
    order_fields = [f for f in (doc.header.email, doc.header.phone, doc.header.location)
                    if (f or "").strip() and (f or "").strip().lower() in low]
    positions = [low.index(f.strip().lower()) for f in order_fields]
    if positions != sorted(positions):
        issues.append(AtsIssue(layer="mechanical", severity="critical",
                               code="contact_order",
                               message="Contact fields extracted out of order (column-scramble risk)."))

    # section_missing — every section header in section_order must be present.
    for section in doc.section_order:
        if section.lower() not in low:
            issues.append(AtsIssue(layer="mechanical", severity="critical",
                                   code="section_missing",
                                   message=f"Section '{section}' header missing from extracted text."))

    # present_skill_dropped — skills the candidate has AND the job wants,
    # but which did not survive into the text layer.
    user_low = {s.strip().lower() for s in user_skills if s.strip()}
    wanted = [s for s in (required_skills + preferred_skills)
              if s.strip().lower() in user_low]
    for skill in wanted:
        if not _present(skill, low):
            issues.append(AtsIssue(layer="mechanical", severity="warning",
                                   code="present_skill_dropped",
                                   message=f"Relevant skill '{skill}' missing from rendered text."))

    # glyph_junk — private-use-area / icon-font glyphs leaking into the text.
    if re.search(r"[-]", text):
        issues.append(AtsIssue(layer="mechanical", severity="warning",
                               code="glyph_junk",
                               message="Icon-font/private-use glyphs found in text layer."))

    return issues
