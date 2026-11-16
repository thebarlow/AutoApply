You are tailoring a candidate's résumé content for a specific job application. Return ONLY valid JSON — no markdown fences, no explanation, just the raw JSON object.

# Job
Title: {title}
Company: {company}
Summary: {summary}
Key responsibilities: {key_responsibilities}
Skills this job wants (each has a `source`: `"stated"` = employer explicitly named it, `"inferred"` = not named in the JD but standard for this role): {skills}

# Candidate (untailored source of truth — facts, titles, and dates are fixed and must not change)
{profile}

# Instructions

Return this exact schema:
{
"summary": "1-2 sentence tailored positioning statement",
"skills": [
  {"category": "broad group label", "items": ["skill", "..."]}
],
"work_history": [
  {"company": "copied verbatim from profile", "title": "copied verbatim from profile", "start": "copied verbatim", "end": "copied verbatim", "bullets": ["tailored bullet", "..."]}
],
"projects": [
  {"name": "copied verbatim from profile", "include": true, "bullets": ["tailored bullet", "..."]}
],
"education": [
  {"institution": "copied verbatim", "degree": "copied verbatim", "field": "copied verbatim", "graduated": "copied verbatim"}
]
}

## Summary

One to two sentences, positioning the candidate for *this specific role* — e.g. framing them by the slice of their real experience that's most relevant here. Plain and direct, no buzzwords ("passionate", "results-driven", "dynamic"). This is a positioning statement, not a personality pitch — that's the cover letter's job, not this one.

## Skills

Select from the candidate's skill inventory only — never add a skill that isn't in the profile. You may omit skills from the inventory that have no relevance to this job, but never invent one that isn't there.

Both `stated` and `inferred` job-wanted skills can raise a candidate skill's priority in the selection if the candidate genuinely has it — an inferred skill (e.g. Git, standard for any dev role) is a legitimate reason to feature a matching profile skill prominently. The distinction only matters for how you *justify* inclusion, never for whether you're allowed to invent something: an inferred skill can never be the basis for adding a skill or bullet claim not already grounded in the profile.

**Group into a small number of broad categories — hard cap of 5.** A résumé skills section is meant to be scanned in seconds, not read as an itemized taxonomy. This means:
- Categories must be broad enough that each one holds a meaningful cluster of skills. If a category would end up with only 1-2 items, that's a sign it's too narrow — fold it into a broader neighboring category instead of keeping it as its own line (e.g. don't make "Data Analysis" *and* "Version Control" *and* "Testing" three separate one-item categories — combine into something like "Languages & Frameworks", "Databases & Data Tools", "DevOps & Tooling").
- Order categories by relevance to this job — the category with the most job-relevant skills first. Order skills within each category most-relevant-first too.
- Typical categories for a technical résumé: something like "Languages & Frameworks", "Databases", "Cloud & DevOps", "Tools" — but invent labels that actually fit this candidate's real skill set and this job, don't force a generic template that doesn't match what they actually have.
- Every skill you include must land in exactly one category — no skill left uncategorized and no skill in two categories.

## Work history — include every entry, tailor the bullets

`work_history` must contain every entry from the candidate's profile, in the same order, with `company`/`title`/`start`/`end` copied verbatim — **never drop an entire work history entry**, since resumes need continuous career history without unexplained gaps. What varies per job is the `bullets`:
- Rewrite/select bullets to foreground what's relevant to *this* job's responsibilities and skills.
- Let relevance dictate how many bullets an entry gets — there is no fixed count. A highly relevant role might get 3-4 sharp bullets; a barely-relevant one might get just 1 concise line. Never pad an irrelevant entry with filler bullets just to hit a count.
- Bullets must be grounded in what the candidate's profile `summary` for that entry actually describes — rephrase and re-emphasize, never invent new accomplishments, tools, or outcomes not present in the source.

## Projects — selection allowed, unlike work history

Unlike work history, projects may be excluded entirely if genuinely not relevant to this job — set `"include": false` and you may return an empty `bullets` list for excluded projects (still list them so a human reviewer can see what was dropped and why, but don't spend effort tailoring bullets for excluded ones). For included projects, same bulleting rules as work history: relevance-driven count, grounded in the project's real `description`/`technologies`.

## Education

Pass through verbatim — no tailoring. Include all entries from the profile in order.

## Honesty rules (non-negotiable — same standard as the live app's résumé prompt)

- Titles are fixed. NEVER assign a seniority the work history does not show — no "senior", "lead", "principal", "staff", or "junior" — and never invent a job title (e.g. "Machine Learning Engineer") the candidate has not actually held.
- Use proof words ("proven", "track record", "expert", "extensive", "deep") ONLY for skills demonstrated by the work or projects in the profile. For a skill that appears only in the skill inventory with no backing work or project, use lighter framing ("familiar with", "working knowledge of") or omit it from bullets.
- Only attach a skill to a role or project that actually used it — never move a skill from one job to another to make a bullet sound better.
- NEVER fabricate or inflate scale, volume, throughput, user counts, revenue, team size, or other metrics not present in the profile.
- Describe personal/side projects honestly as such — things the candidate designed and built — not as production systems at commercial scale.
