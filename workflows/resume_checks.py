"""Mechanical (deterministic, no-LLM) résumé eval checks.

Two of eval_prompt.md's six checks were being done by an LLM despite being
mechanical: required_skills_covered is a substring search, no_continuity_errors
is a diff. Both are exactly the category of thing that produced a real bug
(the eval conflating "near" and "direct" matches) — a deterministic check
can't make that kind of judgment error, is free, and is instant. The other
four checks (no_fabrication, no_keyword_stuffing, no_irrelevant_content,
summary_specific) genuinely require semantic judgment and stay subagent-driven
(see prompts/eval_prompt.md).
"""
from __future__ import annotations


def _present(term: str, haystack_lower: str) -> bool:
    """Case-insensitive literal substring match (same pattern as core.ats_gate._present)."""
    t = term.strip().lower()
    return bool(t) and t in haystack_lower


def _resume_haystack(resume: dict) -> str:
    """One lowercased string covering everywhere a skill could plausibly appear."""
    parts: list[str] = [resume.get("summary", "")]
    for group in resume.get("skills", []):
        parts.extend(group.get("items", []))
    for entry in resume.get("work_history", []):
        parts.extend(entry.get("bullets", []))
    for proj in resume.get("projects", []):
        if proj.get("include", True):
            parts.extend(proj.get("bullets", []))
    return "\n".join(parts).lower()


def required_direct_skills(compared: dict) -> list[str]:
    """Extract the mandatory-coverage skill names from a compared.json entry:
    requirement=="required" AND source=="stated" AND match=="direct".

    Near matches and inferred skills are never mandatory (see eval_prompt.md's
    required_skills_covered rules) — this filter matches that definition exactly.
    """
    return [
        m["name"]
        for m in compared.get("skill_matches", [])
        if m.get("requirement") == "required"
        and (m.get("source") or "stated") == "stated"
        and m.get("match") == "direct"
    ]


def check_required_skills_covered(resume: dict, required_skills: list[str]) -> dict:
    """Every mandatory (stated+direct+required) skill must appear somewhere in the résumé."""
    haystack = _resume_haystack(resume)
    missing = [s for s in required_skills if not _present(s, haystack)]
    return {
        "pass": not missing,
        "issues": [f"'{s}' (required, stated, direct match) does not appear anywhere in the résumé." for s in missing],
    }


def check_continuity(resume: dict, profile: dict) -> dict:
    """The résumé must contain every profile work-history entry, in order, with
    company/title/start/end unchanged."""
    profile_wh = profile.get("work_history", [])
    resume_wh = resume.get("work_history", [])
    issues: list[str] = []

    if len(resume_wh) != len(profile_wh):
        issues.append(
            f"Résumé has {len(resume_wh)} work-history entries, profile has {len(profile_wh)} — "
            "an entry was dropped or added."
        )

    for i, p_entry in enumerate(profile_wh):
        if i >= len(resume_wh):
            issues.append(f"Missing profile entry #{i + 1}: {p_entry.get('company', '')} / {p_entry.get('title', '')}.")
            continue
        r_entry = resume_wh[i]
        for field in ("company", "title", "start", "end"):
            p_val = (p_entry.get(field) or "").strip()
            r_val = (r_entry.get(field) or "").strip()
            if p_val != r_val:
                issues.append(
                    f"Entry #{i + 1} field '{field}' changed: profile has '{p_val}', résumé has '{r_val}'."
                )

    return {"pass": not issues, "issues": issues}
