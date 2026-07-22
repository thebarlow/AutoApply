"""Classify enumerated form-field labels into EEO / eligibility / essay buckets.

Pure string heuristics. The EEO guard is deliberately broad and runs first so a
demographic question can never be routed to the LLM essay pass. Eligibility
matching maps a small set of objective questions to canonical keys; everything
else is treated as a free-text essay question.
"""

from __future__ import annotations

import re
from typing import Literal

# Demographic terms. Broad on purpose: a false positive (an eligibility/essay
# field mislabeled EEO) merely leaves that field blank for manual entry, whereas
# a false negative could let the LLM fabricate a demographic answer.
_EEO_RE = re.compile(
    r"\b(race|ethnicit|gender|transgender|sex\b|male\b|female\b|veteran|disab|"
    r"hispanic|latino|sexual orientation|national origin|protected class|"
    r"self[- ]?identif)\w*",
    re.IGNORECASE,
)

_ELIGIBILITY_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "work_authorized",
        re.compile(
            r"authoriz\w*\s+to\s+work|work\s+authoriz|legally\s+(?:able|entitled)\s+to\s+work",
            re.I,
        ),
    ),
    ("requires_sponsorship", re.compile(r"sponsor", re.I)),
    ("willing_to_relocate", re.compile(r"relocat", re.I)),
    (
        "start_date",
        re.compile(
            r"start\s+date|available.*start|earliest.*start|notice\s+period", re.I
        ),
    ),
    (
        "years_experience",
        re.compile(r"years?\s+of\s+experience|how\s+many\s+years", re.I),
    ),
]


def is_eeo_label(label: str) -> bool:
    """True if the label looks like a demographic / EEO self-ID question."""
    return bool(_EEO_RE.search(label or ""))


def match_eligibility(label: str) -> str | None:
    """Return the canonical eligibility key for an objective question, or None.

    The EEO guard takes precedence at the call site (``classify_custom``); this
    function alone does not exclude demographic labels.
    """
    text = label or ""
    for key, pat in _ELIGIBILITY_PATTERNS:
        if pat.search(text):
            return key
    return None


def classify_custom(label: str) -> Literal["eeo", "eligibility", "essay"]:
    """Route a custom (non-static-schema) field. EEO guard wins first."""
    if is_eeo_label(label):
        return "eeo"
    if match_eligibility(label) is not None:
        return "eligibility"
    return "essay"
