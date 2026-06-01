"""Lightweight, framework-free skill-frequency analytics.

Normalizes raw skill tokens (no LLM) and aggregates how many distinct job
postings mention each skill, separated by extraction field.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Iterable

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


# Maps the output key to the Job attribute holding that field's raw string.
_FIELDS: tuple[tuple[str, str], ...] = (
    ("required", "ext_required_skills"),
    ("preferred", "ext_preferred_skills"),
    ("tech_stack", "ext_tech_stack"),
)


def _normalized_skills(raw: str | None) -> set[str]:
    """Split a comma-separated field and return distinct normalized skills."""
    skills: set[str] = set()
    for token in (raw or "").split(","):
        canonical = normalize_skill(token)
        if canonical:
            skills.add(canonical)
    return skills


def aggregate_skill_frequency(jobs: Iterable[object]) -> dict:
    """Count distinct postings mentioning each skill, per extraction field.

    Each posting contributes at most one to a skill's count per field (deduped
    within the job). ``total_jobs`` is the count of all jobs passed in (the
    caller is responsible for filtering to extracted jobs) and serves as the
    denominator for "% of postings".

    Args:
        jobs: Iterable of job objects with ``ext_required_skills``,
            ``ext_preferred_skills``, and ``ext_tech_stack`` string attributes.

    Returns:
        Dict with keys ``required``, ``preferred``, ``tech_stack`` (each a list
        of ``{"skill": str, "count": int}`` sorted by count desc then name asc),
        and ``total_jobs`` (int).
    """
    counters: dict[str, dict[str, int]] = {
        key: defaultdict(int) for key, _ in _FIELDS
    }
    total_jobs = 0

    for job in jobs:
        total_jobs += 1
        for key, attr in _FIELDS:
            for skill in _normalized_skills(getattr(job, attr, None)):
                counters[key][skill] += 1

    def _sorted(counter: dict[str, int]) -> list[dict]:
        return [
            {"skill": skill, "count": count}
            for skill, count in sorted(
                counter.items(), key=lambda kv: (-kv[1], kv[0])
            )
        ]

    return {
        "required": _sorted(counters["required"]),
        "preferred": _sorted(counters["preferred"]),
        "tech_stack": _sorted(counters["tech_stack"]),
        "total_jobs": total_jobs,
    }
