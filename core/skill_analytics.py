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

# Curated tech/skill -> category map. Keys are lowercased canonical names
# (as produced by normalize_skill, then .lower()). Unmapped -> "Other".
_TECH_CATEGORIES: dict[str, str] = {
    # Languages
    "python": "Languages", "java": "Languages", "javascript": "Languages",
    "typescript": "Languages", "c#": "Languages", "c++": "Languages", "c": "Languages",
    "go": "Languages", "rust": "Languages", "ruby": "Languages", "php": "Languages",
    "swift": "Languages", "kotlin": "Languages", "scala": "Languages", "r": "Languages",
    "perl": "Languages", "objective-c": "Languages", "dart": "Languages",
    "elixir": "Languages", "haskell": "Languages", "lua": "Languages", "bash": "Languages",
    # Frontend
    "react": "Frontend", "angular": "Frontend", "vue": "Frontend", "svelte": "Frontend",
    "next.js": "Frontend", "nuxt": "Frontend", "redux": "Frontend", "tailwind": "Frontend",
    "css": "Frontend", "html": "Frontend", "sass": "Frontend", "less": "Frontend",
    "webpack": "Frontend", "vite": "Frontend", "jquery": "Frontend", "ember": "Frontend",
    "bootstrap": "Frontend", "storybook": "Frontend",
    # Backend
    "node.js": "Backend", "express": "Backend", "django": "Backend", "flask": "Backend",
    "fastapi": "Backend", "spring": "Backend", "spring boot": "Backend", "rails": "Backend",
    "ruby on rails": "Backend", "laravel": "Backend", ".net": "Backend",
    "asp.net": "Backend", "nestjs": "Backend", "graphql": "Backend", "rest": "Backend",
    "grpc": "Backend", "symfony": "Backend", "phoenix": "Backend",
    # Cloud
    "aws": "Cloud", "azure": "Cloud", "gcp": "Cloud", "google cloud": "Cloud",
    "heroku": "Cloud", "digitalocean": "Cloud", "cloudflare": "Cloud", "lambda": "Cloud",
    "s3": "Cloud", "ec2": "Cloud", "cloudformation": "Cloud", "serverless": "Cloud",
    # DevOps
    "docker": "DevOps", "kubernetes": "DevOps", "terraform": "DevOps", "ansible": "DevOps",
    "jenkins": "DevOps", "github actions": "DevOps", "gitlab ci": "DevOps",
    "circleci": "DevOps", "ci/cd": "DevOps", "helm": "DevOps", "prometheus": "DevOps",
    "grafana": "DevOps", "nginx": "DevOps", "puppet": "DevOps", "chef": "DevOps",
    "datadog": "DevOps", "splunk": "DevOps",
    # Databases
    "postgresql": "Databases", "mysql": "Databases", "mongodb": "Databases",
    "redis": "Databases", "sqlite": "Databases", "elasticsearch": "Databases",
    "cassandra": "Databases", "dynamodb": "Databases", "oracle": "Databases",
    "sql server": "Databases", "mariadb": "Databases", "neo4j": "Databases",
    "sql": "Databases", "snowflake": "Databases", "bigquery": "Databases",
    # Data/ML
    "pandas": "Data/ML", "numpy": "Data/ML", "tensorflow": "Data/ML", "pytorch": "Data/ML",
    "scikit-learn": "Data/ML", "spark": "Data/ML", "hadoop": "Data/ML", "kafka": "Data/ML",
    "airflow": "Data/ML", "tableau": "Data/ML", "power bi": "Data/ML",
    "machine learning": "Data/ML", "deep learning": "Data/ML", "nlp": "Data/ML",
    "keras": "Data/ML", "spacy": "Data/ML", "opencv": "Data/ML", "dbt": "Data/ML",
    "databricks": "Data/ML",
    # Mobile
    "android": "Mobile", "ios": "Mobile", "react native": "Mobile", "flutter": "Mobile",
    "swiftui": "Mobile", "xamarin": "Mobile", "ionic": "Mobile",
}


def tech_category(skill: str) -> str:
    """Return the curated category for a canonical skill name, or 'Other'.

    Args:
        skill: A canonical skill display name (as produced by normalize_skill).

    Returns:
        The category label, or "Other" if the skill is not in the curated map.
    """
    return _TECH_CATEGORIES.get(skill.lower(), "Other")


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
    high: int
    med: int
    low: int
    category: str


class CategoryRow(TypedDict):
    category: str
    count: int


class SkillFrequencyResult(TypedDict):
    skills: list[SkillRow]
    categories: list[CategoryRow]
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
    """Aggregate skills into one importance-tiered space, plus category counts.

    For each job, a skill's tier is the strongest field it appears in:
    High (``ext_required_skills``) > Med (``ext_preferred_skills``) >
    Low (``ext_tech_stack`` only). A skill counts once per job at its strongest
    tier, so ``high + med + low`` for a skill is the number of distinct jobs
    mentioning it in any field. ``categories`` counts distinct jobs per
    category (via ``tech_category``). ``total_jobs`` is all jobs passed in.

    Args:
        jobs: Iterable of job objects with ``ext_required_skills``,
            ``ext_preferred_skills``, and ``ext_tech_stack`` string attributes.

    Returns:
        ``SkillFrequencyResult`` with ``skills`` (sorted by total desc, then
        name asc), ``categories`` (count desc, then name asc), and ``total_jobs``.
    """
    high: dict[str, int] = defaultdict(int)
    med: dict[str, int] = defaultdict(int)
    low: dict[str, int] = defaultdict(int)
    category_counts: dict[str, int] = defaultdict(int)
    total_jobs = 0

    for job in jobs:
        total_jobs += 1
        req = _normalized_skills(getattr(job, "ext_required_skills", None))
        pref = _normalized_skills(getattr(job, "ext_preferred_skills", None))
        tech = _normalized_skills(getattr(job, "ext_tech_stack", None))
        all_skills = req | pref | tech
        for skill in all_skills:
            # Mutually exclusive by the elif chain: each skill is counted once
            # per job at its strongest tier, so high+med+low == distinct jobs.
            if skill in req:
                high[skill] += 1
            elif skill in pref:
                med[skill] += 1
            else:
                low[skill] += 1
        for category in {tech_category(s) for s in all_skills}:
            category_counts[category] += 1

    skills = [
        {
            "skill": skill,
            "high": high.get(skill, 0),
            "med": med.get(skill, 0),
            "low": low.get(skill, 0),
            "category": tech_category(skill),
        }
        for skill in sorted(
            set(high) | set(med) | set(low),
            key=lambda s: (-(high.get(s, 0) + med.get(s, 0) + low.get(s, 0)), s),
        )
    ]
    categories = [
        {"category": category, "count": count}
        for category, count in sorted(
            category_counts.items(), key=lambda kv: (-kv[1], kv[0])
        )
    ]
    return {"skills": skills, "categories": categories, "total_jobs": total_jobs}


def seed_alias_pairs() -> list[tuple[str, str]]:
    """Return (alias_key, canonical) pairs to seed the skill_aliases table.

    Includes each curated alias plus a self-row for every distinct canonical
    (so canonicals are themselves matchable and groups are never empty).
    """
    pairs = {k: v for k, v in _ALIASES.items()}
    for canonical in set(_ALIASES.values()):
        pairs.setdefault(canonical.lower(), canonical)
    return sorted(pairs.items())
