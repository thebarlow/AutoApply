You are comparing a job posting's extracted requirements against a candidate's profile, to help the candidate quickly judge fit. Return ONLY valid JSON — no markdown fences, no explanation, just the raw JSON object.

# Candidate Profile
{profile}

# Job Requirements (already extracted from the job description)
Skills: {skills}
Other requirements (narrative, not atomic skills): {unmatched_requirements}

# Instructions

Return this exact schema:
{
"skill_matches": [
  {"name": "skill name, copied exactly from the input skill list", "requirement": "required | preferred (copied from input)", "source": "stated | inferred (copied from input)", "match": "direct | near | miss", "evidence": "one short phrase citing what in the profile supports this call, or null if match is 'miss'"}
],
"requirement_matches": [
  {"text": "requirement text, copied exactly from the input list", "match": "direct | near | miss", "evidence": "one short phrase citing what in the profile supports this call, or null if match is 'miss'"}
],
"fit_summary": "2 sentences max, plain English, on whether this job is a good fit for the candidate"
}

Every entry in the input `Skills` list must appear exactly once in `skill_matches`, and every entry in `Other requirements` must appear exactly once in `requirement_matches` — do not drop, merge, or reorder any.

## Match levels

- `"direct"` — the candidate's profile shows this exact skill/technology, or unambiguous hands-on equivalent experience (e.g. job wants "PostgreSQL", profile lists "PostgreSQL" or a project that explicitly uses it).
- `"near"` — the candidate doesn't have this specific thing but has clearly transferable/adjacent experience (e.g. job wants "NASTRAN", candidate has other FEM/CAE tool experience; job wants 5 years and candidate has 3 in a closely related role; job wants a specific framework and candidate has deep experience in a near-identical one).
- `"miss"` — no reasonable evidence of this skill or its close equivalent anywhere in the profile (skills list, work history, education, or projects).

Be honest and specific — do not inflate matches to be encouraging. A generic "I know some programming" is not evidence for a specific named tool. Base every call on concrete profile content, and name what you found in `evidence`.

## Fit summary

Two sentences, maximum. Weigh **stated** required-skill misses heavily (the employer explicitly asked for it and the candidate doesn't have it — a real gap). Weigh **inferred** required-skill misses more lightly and phrase them differently if mentioned at all — the employer never actually asked for these, they're just standard for the role, so a miss here is a minor caveat, not a stated disqualifier. Never phrase an inferred-skill miss as if the employer rejected the candidate for lacking something they never asked for. Say plainly whether this looks worth the candidate's time to apply to, and why — not a generic "there are pros and cons" hedge.
