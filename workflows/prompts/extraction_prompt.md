You are analyzing a job description to extract structured information for resume tailoring and quick human review. Return ONLY valid JSON — no markdown fences, no explanation, just the raw JSON object.

# Job Posting
Job Title: {title}
Company: {company}
Job Description:
{description}

# Instructions

Return this exact schema:
{
"summary": "2-3 sentence plain-English summary of what this role is and does",
"education": "the JD's stated minimum education requirement, including any alternatives (e.g. years of experience in lieu of a degree), or null if not mentioned",
"clearance": {"level": "e.g. Secret, Top Secret, or 'unspecified' if required but no level named", "status": "must already hold | must be able to obtain | not specified"} or null if the JD says nothing about a security clearance,
"skills": [
  {"name": "atomic skill token", "category": "short group label or null", "requirement": "required | preferred", "expansion": "spelled-out form, or null if not an acronym", "source": "stated | inferred"}
],
"unmatched_requirements": ["qualifications from the JD that are too long or narrative to reduce to an atomic skill token — see rules below"],
"seniority": "junior | mid | senior | staff | not specified",
"role_type": "IC | manager | hybrid | not specified",
"domain": "1-2 word industry or domain",
"key_responsibilities": ["3-5 concise phrases describing what the role actually does"],
"company_signals": ["values, culture cues, or pain points mentioned in the JD"],
"work_arrangement": "remote | hybrid | onsite | not specified",
"employment_type": "full-time | contract | not specified",
"salary_min": null,
"salary_max": null,
"salary_currency": "USD"
}

## Summary

2-3 sentences, no more. State what the role actually is/does in plain English — not a restatement of the company's marketing copy. This is the first thing a human reads, so it should let them decide in a few seconds whether the rest of the listing is worth reading.

## Education

Capture the JD's actual minimum education bar, including stated alternatives. Examples:
- "Bachelor of Science degree in a STEM discipline and 2 years of experience OR a Master of Science degree in a STEM discipline" → keep this whole structure, don't collapse it to just "Bachelor's".
- "Bachelor's degree (technical preferred) with minimum of six years' experience. Graduate Degree and a minimum of 4 years... In lieu of a degree, minimum of 10 years..." → preserve all three paths, since which one applies changes whether the reader qualifies.
- If the JD says nothing about education, use `null`.

## Clearance

Distinguish clearly between a JD that requires the candidate to **already hold** a clearance versus one that only requires **eligibility to obtain** one — this materially changes whether someone without a clearance should bother applying. Cues like "ability to obtain", "eligible to obtain", "may be required to obtain" → `"status": "must be able to obtain"`. Cues like "must possess an active clearance", "current active clearance required" → `"status": "must already hold"`. If the JD only vaguely gestures at clearance requirements without either cue, use `"status": "not specified"`. If clearance is never mentioned at all, the whole `clearance` field is `null` (not an object with nulls inside).

## Skills

A "skill" is a concrete technology, tool, framework, language, methodology, or professional competency. Do NOT include:
- Job or role titles (e.g. "Software Engineer or Programmer", "Coder").
- Generic filler like "proficiency in one programming language" — instead list the specific language(s) the JD names, or omit if none are named.
- Education/degree requirements or security clearance — those belong in the dedicated `education`/`clearance` fields above, not here.

Each `name` MUST be an **atomic skill token** — the bare name of the skill, nothing else:
- Strip qualifier phrasing. "Strong proficiency in Python" → `"Python"`. "Experience with REST API development using FastAPI" → `"REST"`, `"FastAPI"`. "Understanding of NLP" → `"NLP"`.
- Never bundle multiple skills into one entry. Split conjunctions and parentheticals into separate entries: "Python (Pandas, NumPy)" → `"Python"`, `"Pandas"`, `"NumPy"`. "TensorFlow or PyTorch" → `"TensorFlow"`, `"PyTorch"`.
- Never put a comma inside a `name`.
- Prefer the shortest common name as the `name` value: "the Kubernetes container orchestration platform" → `"Kubernetes"`. Put any acronym expansion in the separate `expansion` field, not in `name` — see below.

`category` — group related skills under a short, natural label so the reader can scan by kind instead of a flat list. Categories are contextual to this JD, not a fixed taxonomy — invent whatever grouping actually fits:
- A suite of related tools shares one category: "Word", "Excel", "PowerPoint", "Visio" → all `"category": "MS Office Suite"`.
- Distinguish kinds of technology that are NOT interchangeable even if both are "tools": e.g. `"FEMAP"`/`"NASTRAN"` are `"category": "Industry Software"` (domain-specific engineering tools), while `"Python"`/`"MATLAB"` are `"category": "Programming Language"` — do not lump these together just because both are software.
- If a skill doesn't naturally belong to any group with another skill in this JD, set `"category": null` rather than forcing one.

`expansion` — if `name` is an acronym or initialism (FEM, NLP, IPS, LORA, etc.), spell it out in full here based on the JD's own context (or standard industry meaning if the JD doesn't define it). Example: `{"name": "FEM", "expansion": "Finite Element Modeling", ...}`. Set to `null` if `name` is not an acronym.

`requirement` — `"required"` if the JD lists it as a must-have/basic qualification, `"preferred"` if listed as nice-to-have/preferred qualification. For an `"inferred"` skill (see `source` below), set `requirement` based on how essential it genuinely is to doing this job in practice, not on anything the JD literally says — e.g. Git is `"required"` for essentially any software development role even though a JD listing "Python, FastAPI" and nothing else never says "Git."

`source` — `"stated"` if this skill is explicitly named somewhere in the JD text. `"inferred"` if it is NOT named in the JD, but is a standard, genuinely-expected tool/skill for this specific job title or the responsibilities actually described — e.g. version control (Git) for any software development role, SQL for a data-facing role, a security clearance's implied need for background-check eligibility. Rules for inferring:
- Only infer skills that are near-universal expectations for this exact kind of role — not every plausible skill a person in this field *might* have. When in doubt, leave it out; a false inference is worse than an omission.
- Never infer something that contradicts or is redundant with what's already stated — if the JD already names Git, that's `"stated"`, not a second `"inferred"` entry.
- Base the inference on the job title and the `key_responsibilities` you're extracting, not on generic industry stereotypes unrelated to what this specific posting actually describes.
- Inferred skills must be clearly separable downstream from what the employer actually asked for — this field exists specifically so nothing inferred is ever mistaken for a literal JD requirement.

## Unmatched requirements

Some qualifications in the JD are real requirements but do not reduce to a clean atomic skill token — e.g. "Experience with creating kill/fault trees to capture aircraft redundancy". Do NOT force these into the `skills` list by truncating them into something misleadingly short, and do NOT silently drop them. Instead, copy them (verbatim or lightly trimmed for readability) into `unmatched_requirements`. If a bullet in the JD contains both an extractable atomic skill AND a longer narrative requirement, do both: pull the atomic skill into `skills`, and also add the fuller requirement text to `unmatched_requirements` if it carries meaning beyond that atomic skill.

## Salary

For `salary_min`/`salary_max`: parse any stated pay range (annual base salary, hourly rate as-is, whatever unit the JD uses) into plain numbers, e.g. "$79,300.00 - $118,900.00" → `salary_min: 79300, salary_max: 118900`. If no range is stated, use `null` for both. If only one figure is given, set both min and max to it.

<!--
ITERATION NOTES (local prompt-tuning workflow — not the live app prompt):
- v3 -> v4 changes: added `source: "stated" | "inferred"` to each skill. Motivation:
  role-standard skills (e.g. Git for any dev role) weren't showing up anywhere in
  resume/cover-letter generation unless the JD happened to name them literally, even
  when the candidate genuinely has them and any reviewer would expect to see them.
  `source` lets downstream steps (compare, résumé/cover generation, résumé eval)
  surface these without ever conflating them with something the employer actually
  asked for — critical because the eval loop's `required_skills_covered` check must
  only treat literal JD-stated requirements as mandatory (see eval_prompt.md notes).
- v2 -> v3 changes, based on review of linkedin_4427586312 (L3Harris "Specialist,
  Engineering Services 1"):
  1. Added `summary` (2-3 sentence plain-English role summary), shown at the top
     of the processed column in the viewer.
  2. Added `education` field — v2 explicitly excluded degrees from `skills`
     ("Credentials or degrees... are not skills") but never gave them anywhere
     else to go, so a Bachelor's-required JD looked identical to one with no
     degree requirement at all. Preserves multi-path requirements (degree OR
     years-of-experience substitutions) rather than collapsing to one phrase.
  3. Added `clearance` field distinguishing "must already hold" vs "must be able
     to obtain" — v2's "Secret Clearance" skill entry (Northrop job) didn't
     capture this distinction, and the L3Harris job's "ability to obtain a
     security clearance" phrasing wasn't captured at all (too narrative for the
     old flat skill list, and clearance wasn't explicitly excluded from `skills`
     so results were inconsistent between jobs).
- v1 -> v2 changes (see extraction_prompt_v2.md for full v2 text):
  1. Skills restructured from three flat lists into a single `skills` list of
     {name, category, requirement, expansion} objects, for category grouping.
  2. Added `expansion` field for acronym spell-out.
  3. Added `unmatched_requirements` catch-all for narrative requirements that
     don't reduce to a skill token.
- Base: workflows/prompts/history/extraction_prompt_v1.md (== prompts/defaults/extraction.md
  plus salary parsing).
-->
