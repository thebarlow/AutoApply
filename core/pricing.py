"""Fixed-unit price card for billable LLM actions.

One unit is worth ``unit_usd()`` dollars to buyers. Prices are integers in
units; each is env-overridable (``PRICE_<ACTION>``) so tuning needs no deploy.
See docs/superpowers/specs/2026-07-15-fixed-unit-pricing-design.md.
"""
from __future__ import annotations

import os
from typing import Any

DEFAULT_PRICES: dict[str, int] = {
    "intake": 2,          # pipeline bundle: score + extract + skill-match
    "generate_fresh": 4,  # first generation of a doc_type for a job
    "regenerate": 2,      # re-generate / feedback refine of an existing doc
    "score": 1,
    "extract": 1,
    "resume_parse": 1,
    "ats": 1,
    "rematch": 1,
    "draft": 1,
}


def price_for(action: str) -> int:
    """Units charged for one action. Raises KeyError for unknown actions —
    a call site naming a nonexistent action is a bug, not a free ride."""
    default = DEFAULT_PRICES[action]
    raw = os.getenv(f"PRICE_{action.upper()}", "").strip()
    return int(raw) if raw else default


def unit_usd() -> float:
    """Dollar value of one unit (what buyers pay)."""
    return float(os.getenv("CREDIT_UNIT_USD", "0.02"))


def resolve_generate_action(db: Any, job: Any, doc_type: str) -> str:
    """'generate_fresh' if this doc_type was never generated for the job,
    else 'regenerate'. Server-derived only: a Documents row or a stored
    output path counts as previously generated."""
    from db.database import Document

    if Document.fetch(db, job.job_key, doc_type, job.profile_id) is not None:
        return "regenerate"
    path = job.resume_path if doc_type == "resume" else job.cover_path
    return "regenerate" if path else "generate_fresh"
