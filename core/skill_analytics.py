"""Lightweight, framework-free skill-frequency analytics.

Normalizes raw skill tokens (no LLM) and aggregates how many distinct job
postings mention each skill, separated by extraction field.
"""

from __future__ import annotations

import re
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


def aggregate_skill_frequency(jobs: Iterable) -> dict:
    """Aggregate skill mention counts across job postings by extraction field.

    Args:
        jobs: Iterable of job objects with extracted skill fields.

    Returns:
        Dict mapping field name -> skill -> count of distinct jobs mentioning it.

    Raises:
        NotImplementedError: Task 2 implements this.
    """
    raise NotImplementedError("aggregate_skill_frequency is implemented in Task 2")
