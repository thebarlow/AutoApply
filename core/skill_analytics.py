"""Lightweight, framework-free skill-frequency analytics.

Normalizes raw skill tokens (no LLM) and aggregates how many distinct job
postings mention each skill, separated by extraction field.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Iterable, TypedDict

# Curated alias map: lowercased raw token -> canonical display name.
_ALIASES: dict[str, str] = {
    "js": "JavaScript",
    "javascript": "JavaScript",
    "ts": "TypeScript",
    "typescript": "TypeScript",
    "react.js": "React",
    "reactjs": "React",
    "react": "React",
    "node": "Node.js",
    "node.js": "Node.js",
    "nodejs": "Node.js",
    "k8s": "Kubernetes",
    "kubernetes": "Kubernetes",
    "py": "Python",
    "python": "Python",
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "golang": "Go",
    "go": "Go",
    "c#": "C#",
    "csharp": "C#",
    # Mixed-case tokens that word.capitalize() would mangle.
    "grpc": "gRPC",
    "ios": "iOS",
    "graphql": "GraphQL",
}

# Trailing version tokens like "3.11", "v2", "17", "3.x".
_VERSION_TAIL = re.compile(r"\s+v?\d+(\.\d+|\.x)*$", re.IGNORECASE)
# Surrounding punctuation/whitespace to strip from each end.
_EDGE_PUNCT = re.compile(r"^[\s.,;:/|()\[\]-]+|[\s.,;:/|()\[\]-]+$")


def normalize_skill(raw: str) -> str | None:
    """Normalize a raw skill token to a canonical display name.

    Returns ``None`` for empty/junk tokens. Applies, in order: lowercase +
    trim for alias lookup; strip trailing version tokens; strip surrounding
    punctuation; alias map; title-case fallback for unknown skills.

    Args:
        raw: Raw skill string from a job posting or resume extraction.

    Returns:
        Canonical display name, or None if the token is empty or junk.
    """
    if not raw:
        return None

    stripped = _EDGE_PUNCT.sub("", raw.strip())
    if not stripped:
        return None

    # Drop a trailing version token (e.g. "Python 3.11" -> "Python").
    versionless = _VERSION_TAIL.sub("", stripped).strip()
    candidate = versionless or stripped

    key = candidate.lower()
    if key in _ALIASES:
        return _ALIASES[key]

    # Reject tokens that are nothing but digits/punctuation, or version-like
    # strings that lead with a digit (e.g. "3.x", "17", "2.0").
    if not re.search(r"[a-zA-Z]", candidate):
        return None
    if re.match(r"^\d", candidate):
        return None

    # Title-case unknown skills, preserving all-caps acronyms (e.g. "AWS").
    words = []
    for word in candidate.split():
        words.append(word if word.isupper() else word.capitalize())
    return " ".join(words)


class SkillRow(TypedDict):
    skill: str
    count: int


class CombinedSkillRow(TypedDict):
    skill: str
    required: int
    preferred: int


class SkillFrequencyResult(TypedDict):
    skills: list[CombinedSkillRow]
    tech_stack: list[SkillRow]
    total_jobs: int


def _normalized_skills(raw: str | None) -> set[str]:
    """Split a comma-separated field and return distinct normalized skills."""
    skills: set[str] = set()
    for token in (raw or "").split(","):
        canonical = normalize_skill(token)
        if canonical:
            skills.add(canonical)
    return skills


def job_has_skill(job: object, canonical_skill: str) -> bool:
    """True if the normalized skill appears in any extraction field of the job.

    Args:
        job: A job object with ``ext_required_skills``, ``ext_preferred_skills``,
            and ``ext_tech_stack`` string attributes.
        canonical_skill: The canonical display name to match (e.g. "Python"),
            as produced by ``normalize_skill``.

    Returns:
        True if the skill is listed in required, preferred, or tech-stack fields.
    """
    return canonical_skill in (
        _normalized_skills(getattr(job, "ext_required_skills", None))
        | _normalized_skills(getattr(job, "ext_preferred_skills", None))
        | _normalized_skills(getattr(job, "ext_tech_stack", None))
    )


def aggregate_skill_frequency(jobs: Iterable[object]) -> SkillFrequencyResult:
    """Count distinct postings mentioning each skill.

    ``skills`` combines required and preferred into one row per skill, where
    ``required`` counts jobs listing the skill in ``ext_required_skills`` and
    ``preferred`` counts jobs listing it in ``ext_preferred_skills`` but NOT in
    required ("required wins"), so ``required + preferred`` is the distinct-job
    total. ``tech_stack`` counts distinct jobs per skill in ``ext_tech_stack``.
    ``total_jobs`` is the count of all jobs passed in (caller filters to
    extracted jobs) and is the denominator for "% of postings".

    Args:
        jobs: Iterable of job objects with ``ext_required_skills``,
            ``ext_preferred_skills``, and ``ext_tech_stack`` string attributes.

    Returns:
        ``SkillFrequencyResult`` with ``skills`` (sorted by required+preferred
        descending, then skill name ascending), ``tech_stack`` (sorted by count
        descending, then name ascending), and ``total_jobs``.
    """
    required_counts: dict[str, int] = defaultdict(int)
    preferred_counts: dict[str, int] = defaultdict(int)
    tech_counts: dict[str, int] = defaultdict(int)
    total_jobs = 0

    for job in jobs:
        total_jobs += 1
        req = _normalized_skills(getattr(job, "ext_required_skills", None))
        pref = _normalized_skills(getattr(job, "ext_preferred_skills", None))
        tech = _normalized_skills(getattr(job, "ext_tech_stack", None))
        for skill in req:
            required_counts[skill] += 1
        for skill in pref - req:  # required wins: skip skills already required
            preferred_counts[skill] += 1
        for skill in tech:
            tech_counts[skill] += 1

    skills = [
        {"skill": skill, "required": required_counts.get(skill, 0),
         "preferred": preferred_counts.get(skill, 0)}
        for skill in sorted(
            set(required_counts) | set(preferred_counts),
            key=lambda s: (-(required_counts.get(s, 0) + preferred_counts.get(s, 0)), s),
        )
    ]
    tech_stack = [
        {"skill": skill, "count": count}
        for skill, count in sorted(tech_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    return {"skills": skills, "tech_stack": tech_stack, "total_jobs": total_jobs}
