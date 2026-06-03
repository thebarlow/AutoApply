from __future__ import annotations

import json
import re
from typing import TypeVar

from pydantic import BaseModel, Field, field_validator

T = TypeVar("T", bound=BaseModel)

_PREVIEW_LEN = 300


def _clamp_unit(v: float) -> float:
    """Clamp a numeric score into the [0.0, 1.0] range."""
    return max(0.0, min(1.0, float(v)))


class Justification(BaseModel):
    """Positive/negative signal bullets for one scoring axis."""

    raised: list[str] = Field(default_factory=list)
    lowered: list[str] = Field(default_factory=list)


class ScoreResponse(BaseModel):
    """Parsed output of the `scoring` prompt."""

    fit_score: float
    desirability_score: float
    fit_justification: Justification
    desirability_justification: Justification

    @field_validator("fit_score", "desirability_score")
    @classmethod
    def _clamp(cls, v: float) -> float:
        return _clamp_unit(v)


class Issue(BaseModel):
    """A single resume/cover quality issue from an eval prompt."""

    category: str = ""
    description: str = ""


class EvalResponse(BaseModel):
    """Parsed output of the `resume_eval` / `cover_eval` prompts."""

    score: float
    issues: list[Issue] = Field(default_factory=list)

    @field_validator("score")
    @classmethod
    def _clamp(cls, v: float) -> float:
        return _clamp_unit(v)

    @field_validator("issues", mode="before")
    @classmethod
    def _coerce_issues(cls, v: object) -> object:
        # The evaluator occasionally emits a non-list; treat as "no issues".
        return v if isinstance(v, list) else []


class ExtractionResponse(BaseModel):
    """Parsed output of the `extraction` prompt."""

    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    key_responsibilities: list[str] = Field(default_factory=list)
    company_signals: list[str] = Field(default_factory=list)
    seniority: str = ""
    role_type: str = ""
    domain: str = ""
    work_arrangement: str = ""
    employment_type: str = ""
    salary_min: float | None = None
    salary_max: float | None = None


def parse_llm_json(raw: str, model: type[T]) -> T:
    """Parse and validate a JSON object out of a raw LLM response.

    Strips code fences, extracts the outermost ``{...}`` object, JSON-decodes it,
    and validates against ``model``.

    Args:
        raw: The raw text returned by the LLM.
        model: The Pydantic model class to validate against.

    Returns:
        A validated instance of ``model``.

    Raises:
        RuntimeError: If the text is empty, not valid JSON, or fails validation.
            The message includes a truncated preview of ``raw``.
    """
    from pydantic import ValidationError

    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text).strip()
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last > first:
        text = text[first : last + 1]

    if not text:
        raise RuntimeError("LLM returned empty content")

    try:
        data = json.loads(text)
        return model.model_validate(data)
    except (json.JSONDecodeError, ValueError, ValidationError) as exc:
        preview = (raw or "")[:_PREVIEW_LEN].replace("\n", " ")
        raise RuntimeError(
            f"Unparseable LLM response: {exc}. Preview: {preview!r}"
        ) from exc
