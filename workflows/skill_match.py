"""Pre-compute deterministic "direct" skill matches before the compare
subagent runs, so it only has to judge the genuinely ambiguous cases
(near vs. miss). A skill counts as direct when the candidate's profile
literally lists it (or a project explicitly names it in `technologies`) —
that's a case-insensitive lookup, no ambiguity, and a class of error an LLM
could in principle get wrong (misjudging an exact match as "near"/"miss")
that a deterministic check structurally cannot.
"""
from __future__ import annotations


def direct_match(skill_name: str, profile: dict) -> dict | None:
    """Case-insensitive lookup of skill_name against profile skills / project
    technologies. Returns a match dict on a hit, None on a miss (a miss here
    means "needs LLM judgment for near/miss", not "this skill is a miss")."""
    name_lower = skill_name.strip().lower()
    if not name_lower:
        return None

    for s in profile.get("skills", []):
        if s.strip().lower() == name_lower:
            return {"match": "direct", "evidence": f"profile skill '{s}'"}

    for proj in profile.get("projects", []):
        for tech in proj.get("technologies", []):
            if tech.strip().lower() == name_lower:
                return {"match": "direct", "evidence": f"used in project '{proj.get('name', '')}'"}

    return None


def precompute_direct_matches(job_skills: list[dict], profile: dict) -> tuple[list[dict], list[dict]]:
    """Split a job's `skills` list (from extracted.json) into (precomputed, remaining).

    `precomputed` entries are full skill_matches rows, ready to use as-is:
    {name, requirement, source, match: "direct", evidence}.
    `remaining` are the original job_skills entries still needing subagent
    judgment (near vs. miss) — skills with no direct hit.
    """
    precomputed: list[dict] = []
    remaining: list[dict] = []

    for skill in job_skills:
        name = skill.get("name", "")
        hit = direct_match(name, profile)
        if hit is None:
            remaining.append(skill)
        else:
            precomputed.append({
                "name": name,
                "requirement": skill.get("requirement", "required"),
                "source": skill.get("source", "stated"),
                "match": "direct",
                "evidence": hit["evidence"],
            })

    return precomputed, remaining
