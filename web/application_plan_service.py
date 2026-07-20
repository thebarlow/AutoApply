"""Wiring between the pure mapping engine and the LLM + persistence layers."""

from __future__ import annotations

import logging
from typing import Any

from core.application_mapper import EssayDrafter

logger = logging.getLogger(__name__)


def make_essay_drafter(user: Any, job: Any) -> EssayDrafter:
    """Return a drafter that answers free-text questions grounded in the profile.

    Reuses the existing generation LLM path. Each question is answered honestly
    from profile facts; answers are always marked 'drafted' (needs review) by the
    engine, never auto-submitted.
    """
    from core.job import draft_application_answers

    def drafter(pairs: list[tuple[str, str]]) -> dict[str, str]:
        try:
            return draft_application_answers(user, job, pairs)
        except Exception:
            logger.exception(
                "[application-plan] essay drafting failed for %s",
                getattr(job, "job_key", "?"),
            )
            return {}

    return drafter
