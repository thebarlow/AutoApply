"""Input-size caps for anything that can reach an LLM prompt or a render.

Prices are fixed per action (``core/pricing.py``), so an unbounded input lets one
action cost the platform more than it charges (audit H3). Every free-text field
a tenant controls is capped here, in one place, so the limits are easy to tune.

String fields use Pydantic ``Field(max_length=...)`` (FastAPI answers 422);
whole JSON payloads are measured with :func:`ensure_json_within`, which raises
:class:`InputTooLarge` (mapped to HTTP 413 in ``web/main.py``).
"""
from __future__ import annotations

import json
from typing import Any

# ── Job postings ────────────────────────────────────────────────────────────
MAX_JOB_DESCRIPTION = 50_000
MAX_JOB_SHORT_FIELD = 500        # title, company, location, salary, source, ...
MAX_URL = 2_048

# ── Prompts / LLM-bound free text ───────────────────────────────────────────
MAX_PROMPT_CONTENT = 20_000
MAX_MODEL_ID = 200
MAX_FEEDBACK_NOTE = 5_000
MAX_FEEDBACK_NOTES = 50          # notes per feedback request
MAX_SECTION_PROMPT_FIELD = 5_000  # section-prompt draft purpose / tailoring
MAX_LABEL = 500                   # section names, feedback labels, skill names
MAX_ESSAY_LABEL = 2_000           # application-form question text
MAX_ESSAY_OPTIONS = 200           # options per enumerated form field
MAX_ENUMERATED_FIELDS = 300       # fields per application-plan request
MAX_SKILLS_PER_REQUEST = 200

# ── Whole JSON payloads (serialized characters) ─────────────────────────────
MAX_PROFILE_JSON = 200_000        # profile data / profile tree / parse-apply
MAX_DOCUMENT_JSON = 200_000       # edited résumé / cover document

# ── Raw request bodies (bytes; enforced by web/middleware_body_limit.py) ────
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_REQUEST_BODY_BYTES = 2 * 1024 * 1024
# Multipart framing (boundaries, part headers) on top of the file itself.
MULTIPART_OVERHEAD_BYTES = 64 * 1024


class InputTooLarge(Exception):
    """A tenant-supplied payload exceeds its cap (HTTP 413)."""

    def __init__(self, what: str, size: int, limit: int) -> None:
        self.what, self.size, self.limit = what, size, limit
        super().__init__(f"{what} is too large ({size:,} > {limit:,} characters).")


def ensure_json_within(obj: Any, limit: int, what: str) -> None:
    """Raise :class:`InputTooLarge` if ``obj`` serializes to more than ``limit`` chars.

    Args:
        obj: Any JSON-serializable value (typically a request body dict).
        limit: Maximum serialized length in characters.
        what: Human-readable name used in the error message.
    """
    size = len(json.dumps(obj, ensure_ascii=False, default=str))
    if size > limit:
        raise InputTooLarge(what, size, limit)
