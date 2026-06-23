from __future__ import annotations

import json
from typing import TypeVar

from pydantic import BaseModel, Field, ValidationError, field_validator

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


class SectionScore(BaseModel):
    """One section's evaluation: name (matches a tree SectionNode.name), score, issues."""

    section: str = ""
    score: float = 0.0
    issues: list[Issue] = Field(default_factory=list)

    @field_validator("score")
    @classmethod
    def _clamp_score(cls, v: float) -> float:
        return _clamp_unit(v)


class SectionEvalResponse(BaseModel):
    """Per-section résumé evaluation: one SectionScore per scored section."""

    sections: list[SectionScore] = Field(default_factory=list)


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


class WorkHistoryItem(BaseModel):
    company: str = ""
    title: str = ""
    start: str = ""
    end: str = ""
    summary: str = ""


class EducationItem(BaseModel):
    institution: str = ""
    degree: str = ""
    field: str = ""
    graduated: str = ""
    gpa: float = 0


class ProjectItem(BaseModel):
    name: str = ""
    description: str = ""
    url: str = ""
    technologies: list[str] = Field(default_factory=list)


class ParseResponse(BaseModel):
    """Parsed output of the `resume_parse` prompt (a structured profile)."""

    first_name: str = ""
    last_name: str = ""
    hero: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    linkedin: str = ""
    github: str = ""
    website: str = ""
    skills: list[str] = Field(default_factory=list)
    work_history: list[WorkHistoryItem] = Field(default_factory=list)
    education: list[EducationItem] = Field(default_factory=list)
    projects: list[ProjectItem] = Field(default_factory=list)
    target_roles: list[str] = Field(default_factory=list)
    target_salary_min: float | None = None
    target_salary_max: float | None = None


# ── Structured résumé/cover documents (Phase 3a) ─────────────────────────────


class ResumeHeader(BaseModel):
    """Snapshot of profile contact info captured at generation time."""

    name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    github: str = ""
    linkedin: str = ""
    website: str = ""


class ResumeExperience(BaseModel):
    """One work-history entry: structural fields from profile, prose from LLM."""

    company: str = ""
    title: str = ""
    start: str = ""
    end: str = ""
    description: str = ""  # Markdown bullets — LLM-authored


class ResumeProject(BaseModel):
    """One project: name/url from profile, prose from LLM."""

    name: str = ""
    url: str = ""
    description: str = ""  # Markdown — LLM-authored


class ResumeSkillGroup(BaseModel):
    """An LLM-chosen skill category and its items."""

    category: str = ""
    items: list[str] = Field(default_factory=list)


class ResumeDocument(BaseModel):
    """The stored, assembled résumé artifact (source of truth)."""

    header: ResumeHeader = Field(default_factory=ResumeHeader)
    education: list[EducationItem] = Field(default_factory=list)
    profile_summary: str = ""
    experience: list[ResumeExperience] = Field(default_factory=list)
    projects: list[ResumeProject] = Field(default_factory=list)
    skills: list[ResumeSkillGroup] = Field(default_factory=list)
    section_order: list[str] = Field(default_factory=list)


class SignOff(BaseModel):
    """Cover-letter sign-off snapshot."""

    name: str = ""


class CoverDocument(BaseModel):
    """The stored cover-letter artifact."""

    header: ResumeHeader = Field(default_factory=ResumeHeader)
    body: str = ""  # Markdown — LLM-authored
    signoff: SignOff = Field(default_factory=SignOff)


# ── LLM résumé output contract (prose-only, keyed by profile ref) ────────────


class ExperienceRef(BaseModel):
    """LLM prose for one work-history entry, keyed by its profile index."""

    ref: int
    description: str = ""


class ProjectRef(BaseModel):
    """LLM prose for one selected project, keyed by its profile index."""

    ref: int
    description: str = ""


class ResumeGeneration(BaseModel):
    """Parsed output of the rewritten `resume` prompt (prose-only, keyed)."""

    profile_summary: str = ""
    experience: list[ExperienceRef] = Field(default_factory=list)
    projects: list[ProjectRef] = Field(default_factory=list)
    skills: list[ResumeSkillGroup] = Field(default_factory=list)


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
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text.rsplit("\n", 1)[0] if "\n" in text else text[:-3]
    text = text.strip()

    if not text:
        raise RuntimeError("LLM returned empty content")

    first = text.find("{")
    last = text.rfind("}")
    if first == -1 or last <= first:
        preview = (raw or "")[:_PREVIEW_LEN].replace("\n", " ")
        raise RuntimeError(
            f"LLM response contains no JSON object. Preview: {preview!r}"
        )
    text = text[first : last + 1]

    preview = (raw or "")[:_PREVIEW_LEN].replace("\n", " ")
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(
            f"LLM response is not valid JSON: {exc}. Preview: {preview!r}"
        ) from exc
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise RuntimeError(
            f"LLM response failed schema validation: {exc}. Preview: {preview!r}"
        ) from exc


# ── ATS gate (PDF parseability) ──────────────────────────────────────────────


class PdfText(BaseModel):
    """Text extracted from a rendered PDF for ATS analysis."""

    text: str = ""
    lines: list[str] = Field(default_factory=list)


class AtsIssue(BaseModel):
    """One ATS finding. `critical` issues hard-block; `warning` issues are advisory."""

    layer: str  # "mechanical" | "semantic"
    severity: str  # "critical" | "warning"
    code: str
    message: str


class AtsReport(BaseModel):
    """Result of running the ATS gate over a rendered résumé PDF."""

    passed: bool = True
    score: float = 1.0
    issues: list[AtsIssue] = Field(default_factory=list)
    extracted_text: str = ""

    @classmethod
    def build(cls, score: float, issues: list[AtsIssue], extracted_text: str) -> "AtsReport":
        passed = not any(i.severity == "critical" for i in issues)
        return cls(passed=passed, score=score, issues=issues, extracted_text=extracted_text)


class AtsParsedFields(BaseModel):
    """Semantic round-trip contract: what a parser extracted from the PDF text."""

    name: str = ""
    email: str = ""
    phone: str = ""
    sections: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    experience_dates: list[str] = Field(default_factory=list)
