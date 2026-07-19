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
    "docker": "Docker",
    "docker compose": "Docker",
    "docker-compose": "Docker",
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


def skill_key(raw: str, aliases: dict[str, str] | None = None) -> str | None:
    """Return the case-folded grouping key for a raw token, or None for junk.

    Strips a trailing version token and edge punctuation, lowercases, then maps
    through ``aliases`` (defaulting to the built-in ``_ALIASES`` map when not
    provided). For an aliased token the key is the canonical's lowercase, so all
    members of a group share one key; otherwise the key is the cleaned token's
    lowercase.
    """
    if not raw:
        return None
    stripped = _EDGE_PUNCT.sub("", raw.strip())
    if not stripped:
        return None
    versionless = _VERSION_TAIL.sub("", stripped).strip()
    candidate = versionless or stripped
    if not re.search(r"[a-zA-Z]", candidate) or re.match(r"^\d", candidate):
        return None
    key = candidate.lower()
    effective_aliases = _ALIASES if aliases is None else aliases
    if key in effective_aliases:
        return effective_aliases[key].lower()
    return key


def normalize_skill(raw: str, aliases: dict[str, str] | None = None) -> str | None:
    """Normalize a raw skill token to a canonical display name, or None.

    Case-insensitive: tokens differing only by case resolve to one display.
    When ``aliases`` maps the token (directly or via its group canonical) the
    canonical display is returned; otherwise the cleaned token is title-cased
    (all-caps acronyms preserved). Corpus-frequency display selection happens in
    ``aggregate_skill_frequency``, not here.
    """
    if not raw:
        return None
    stripped = _EDGE_PUNCT.sub("", raw.strip())
    if not stripped:
        return None
    versionless = _VERSION_TAIL.sub("", stripped).strip()
    candidate = versionless or stripped
    if not re.search(r"[a-zA-Z]", candidate) or re.match(r"^\d", candidate):
        return None
    key = candidate.lower()
    effective_aliases = _ALIASES if aliases is None else aliases
    if key in effective_aliases:
        return effective_aliases[key]
    # Title-case unknown skills, preserving all-caps acronyms (e.g. "AWS").
    words = []
    for word in candidate.split():
        words.append(word if word.isupper() else word.capitalize())
    return " ".join(words)


class SkillRow(TypedDict):
    key: str
    skill: str
    high: int
    med: int
    low: int
    category: str


class CategoryRow(TypedDict):
    category: str
    count: int


def split_skill_tokens(raw: str | None) -> list[str]:
    """Split a comma-joined skill field into clean chips, paren-aware.

    ``Category (a, b)`` yields ``["Category", "a", "b"]`` instead of the
    malformed ``["Category (a", "b)"]`` a naive comma split produces. Chips
    are stripped and case-insensitively deduped preserving order. Unbalanced
    parentheses fall back to a plain comma split.
    """
    text = raw or ""
    if not text.strip():
        return []

    if text.count("(") != text.count(")"):
        parts = text.split(",")
    else:
        parts, depth, buf = [], 0, []
        for ch in text:
            if ch == "," and depth == 0:
                parts.append("".join(buf))
                buf = []
                continue
            depth += 1 if ch == "(" else -1 if ch == ")" else 0
            buf.append(ch)
        parts.append("".join(buf))
        # Expand "Name (a, b)" into the name plus each parenthesized item.
        expanded: list[str] = []
        for p in parts:
            m = re.fullmatch(r"\s*(?P<name>[^()]*?)\s*\((?P<inner>[^()]+)\)\s*", p)
            if m:
                expanded.append(m.group("name"))
                expanded.extend(m.group("inner").split(","))
            else:
                expanded.append(p)
        parts = expanded

    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        t = p.strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out


class SkillFrequencyResult(TypedDict):
    skills: list[SkillRow]
    categories: list[CategoryRow]
    total_jobs: int


def job_has_skill(job: object, canonical_skill: str, aliases: dict[str, str] | None = None) -> bool:
    """True if the skill (matched case-insensitively) appears in any extraction field."""
    # None means "use built-in _ALIASES"; an explicit dict (even {}) overrides.
    effective_aliases: dict[str, str] = _ALIASES if aliases is None else aliases
    target = skill_key(canonical_skill, effective_aliases)
    if target is None:
        return False
    keys: set[str] = set()
    for attr in ("ext_required_skills", "ext_preferred_skills", "ext_tech_stack"):
        for token in split_skill_tokens(getattr(job, attr, None)):
            k = skill_key(token, effective_aliases)
            if k:
                keys.add(k)
    return target in keys


def aggregate_skill_frequency(
    jobs: Iterable[object], aliases: dict[str, str] | None = None
) -> SkillFrequencyResult:
    """Aggregate skills into one importance-tiered space, plus category counts.

    Skills are grouped by case-folded key (see ``skill_key``). A skill's tier per
    job is the strongest field it appears in (required > preferred > tech-stack),
    so ``high + med + low`` equals the number of distinct jobs mentioning it.
    Display name is the alias canonical if the key is aliased, else the most
    frequent original casing across jobs (tie-break alphabetical).
    """
    # None means "use built-in _ALIASES"; an explicit dict (even {}) overrides.
    effective_aliases: dict[str, str] = _ALIASES if aliases is None else aliases
    canonical_by_lower = {c.lower(): c for c in effective_aliases.values()}
    high: dict[str, int] = defaultdict(int)
    med: dict[str, int] = defaultdict(int)
    low: dict[str, int] = defaultdict(int)
    casing: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    category_counts: dict[str, int] = defaultdict(int)
    total_jobs = 0

    def keyed(raw: str | None) -> dict[str, str]:
        """Map of key -> original cleaned spelling for one comma-separated field.

        Also accumulates casing counts for all tokens so display can pick the
        most-frequent original casing across the whole corpus.
        """
        out: dict[str, str] = {}
        for t in split_skill_tokens(raw):
            k = skill_key(t, effective_aliases)
            if k:
                casing[k][t] += 1
                out[k] = t  # last-wins for tier counting; casing tracked above
        return out

    def display(k: str) -> str:
        if k in canonical_by_lower:
            return canonical_by_lower[k]
        # Return the most-frequent original casing from the corpus (tie-break
        # alphabetical). This preserves e.g. "FastAPI" over "FASTAPI".
        best = sorted(casing[k].items(), key=lambda kv: (-kv[1], kv[0]))
        return best[0][0] if best else k

    for job in jobs:
        total_jobs += 1
        req = keyed(getattr(job, "ext_required_skills", None))
        pref = keyed(getattr(job, "ext_preferred_skills", None))
        tech = keyed(getattr(job, "ext_tech_stack", None))
        all_keys = {**tech, **pref, **req}  # later wins for tier counting
        for k in all_keys:
            if k in req:
                high[k] += 1
            elif k in pref:
                med[k] += 1
            else:
                low[k] += 1
        for category in {tech_category(display(k)) for k in all_keys}:
            category_counts[category] += 1

    all_skill_keys = set(high) | set(med) | set(low)
    skills: list[SkillRow] = [
        {
            "key": k,
            "skill": display(k),
            "high": high.get(k, 0),
            "med": med.get(k, 0),
            "low": low.get(k, 0),
            "category": tech_category(display(k)),
        }
        for k in sorted(
            all_skill_keys,
            key=lambda k: (-(high.get(k, 0) + med.get(k, 0) + low.get(k, 0)), display(k)),
        )
    ]
    categories: list[CategoryRow] = [
        {"category": c, "count": n}
        for c, n in sorted(category_counts.items(), key=lambda kv: (-kv[1], kv[0]))
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
