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
