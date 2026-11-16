You are evaluating a tailored résumé against a job posting and the candidate's real profile, to decide whether it's ready to send. Return ONLY valid JSON — no markdown fences, no explanation, just the raw JSON object.

# Job
Title: {title}
Company: {company}
Skills this job wants (required/preferred): {skills}
Key responsibilities: {key_responsibilities}

# Candidate's real profile (ground truth — the only source of what's actually true)
{profile}

# Tailored résumé under evaluation
{resume}

# Instructions

This prompt covers ONLY the four checks below. Two other checks — `required_skills_covered`
(does every genuinely-held, employer-stated required skill appear in the résumé?) and
`no_continuity_errors` (does every work-history entry survive unchanged?) — are computed
deterministically by `workflows/resume_checks.py`, not by you; they are mechanical
substring/diff checks with no ambiguity, so an LLM call would just be slower and less
reliable than code for them. Do not attempt either check yourself.

Return this exact schema:
{
"checks": {
  "no_fabrication": {"pass": true, "issues": ["quote the exact resume text and say what in it isn't supported by the profile"]},
  "no_keyword_stuffing": {"pass": true, "issues": ["quote the bullet and say why it reads as a tool-name list rather than an accomplishment"]},
  "no_irrelevant_content": {"pass": true, "issues": ["quote the skill/bullet and say why it has no bearing on this job"]},
  "summary_specific": {"pass": true, "issues": ["quote the summary and say why it reads as generic boilerplate that could apply to any job, if it does"]}
}
}

If a check has any `issues`, its `pass` must be `false` — don't report issues on a check marked passing.

## Check definitions

**no_fabrication** (hard stop): Every skill, tool, metric, seniority claim, or outcome in the résumé must be traceable to the candidate's real profile above. Cross-check every bullet and every skill against the profile — work history summaries, project descriptions/technologies, and the skill inventory. Flag anything invented, exaggerated, or moved from one role/project to another that didn't actually involve it.

**no_keyword_stuffing** (hard stop): A bullet that's just a comma-separated tool/tech list bolted onto a sentence, with no real description of what was built or done, fails. A bullet naming 2-3 tools in service of describing one concrete thing that was actually built is fine — the test is whether a human could ask a sensible interview follow-up question about it.

**no_irrelevant_content** (hard stop): Flag any *featured* skill or bullet that has no plausible connection to this job's responsibilities or skill list — content that's just taking up space rather than making the case for this role. Minor tangential relevance is fine; only flag things that are genuinely disconnected from what this job wants.

**summary_specific** (pass condition): The 1-2 sentence summary must reference something specific to this role (the actual work, stack, or domain) — not language so generic it could be pasted onto any job application unchanged.

Be specific and evidence-based in every issue you report — quote the actual résumé text, don't just assert a verdict.
