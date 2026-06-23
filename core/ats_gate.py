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

from core.llm import call_llm
from core.schemas import AtsIssue, AtsReport, AtsParsedFields, PdfText, ResumeDocument, parse_llm_json


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


def _present(term: str, haystack_lower: str) -> bool:
    """Case-insensitive literal substring match."""
    t = term.strip().lower()
    return bool(t) and t in haystack_lower


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
    # Restrict to the header region. 300 chars ≈ name (~30) + up to 6 contact
    # fields (~40 each); index() finds the first occurrence, so a contact value
    # repeated in the body could otherwise scramble the order check.
    HEADER_REGION = 300
    header_low = low[:HEADER_REGION]
    order_fields = [f for f in (doc.header.email, doc.header.phone, doc.header.location)
                    if (f or "").strip() and (f or "").strip().lower() in header_low]
    positions = [header_low.index(f.strip().lower()) for f in order_fields]
    if positions != sorted(positions):
        issues.append(AtsIssue(layer="mechanical", severity="critical",
                               code="contact_order",
                               message="Contact fields extracted out of order (column-scramble risk)."))

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


def check_roundtrip(
    pt: PdfText,
    doc: ResumeDocument,
    prompt: str,
    client,
    model: str,
) -> list[AtsIssue]:
    """Advisory: ask the LLM to parse the extracted text, diff vs the document.

    Args:
        pt: Extracted PDF text.
        doc: The stored ResumeDocument (ground truth).
        prompt: ats_parse template containing a ``{extracted_text}`` placeholder.
        client: OpenAI-compatible client.
        model: Model identifier.

    Returns:
        Warning-only AtsIssue list. Never raises on a model mismatch — on any
        LLM/parse failure it returns an empty list (advisory layer must not break
        the gate).
    """
    sent = prompt.replace("{extracted_text}", pt.text)
    try:
        # Parsing-only task; AtsParsedFields is compact, so a small token budget suffices.
        raw = call_llm(sent, client, model, max_tokens=2048)
        parsed = parse_llm_json(raw or "", AtsParsedFields)
    except Exception:
        return []

    issues: list[AtsIssue] = []
    if doc.header.name and parsed.name and parsed.name.strip().lower() != doc.header.name.strip().lower():
        issues.append(AtsIssue(layer="semantic", severity="warning", code="roundtrip_name",
                               message=f"Parser read name as '{parsed.name}', expected '{doc.header.name}'."))
    if doc.header.email and parsed.email and parsed.email.strip().lower() != doc.header.email.strip().lower():
        issues.append(AtsIssue(layer="semantic", severity="warning", code="roundtrip_email",
                               message=f"Parser read email as '{parsed.email}', expected '{doc.header.email}'."))
    if doc.header.phone and parsed.phone and parsed.phone.strip().lower() != doc.header.phone.strip().lower():
        issues.append(AtsIssue(layer="semantic", severity="warning", code="roundtrip_phone",
                               message=f"Parser read phone as '{parsed.phone}', expected '{doc.header.phone}'."))
    return issues


def run_gate(
    pt: PdfText,
    doc: ResumeDocument,
    required_skills: list[str],
    preferred_skills: list[str],
    user_skills: list[str],
    roundtrip_prompt: str,
    client,
    model: str,
) -> AtsReport:
    """Run both ATS layers and assemble a report.

    Mechanical issues hard-block (critical). Semantic issues are advisory.
    Score = 1.0 − 0.25·(#critical) − 0.05·(#warning), clamped to [0, 1].
    """
    issues = check_mechanical(pt, doc, required_skills, preferred_skills, user_skills)
    issues += check_roundtrip(pt, doc, roundtrip_prompt, client, model)
    n_crit = sum(1 for i in issues if i.severity == "critical")
    n_warn = sum(1 for i in issues if i.severity == "warning")
    score = max(0.0, min(1.0, 1.0 - 0.25 * n_crit - 0.05 * n_warn))
    return AtsReport.build(score=score, issues=issues, extracted_text=pt.text)
