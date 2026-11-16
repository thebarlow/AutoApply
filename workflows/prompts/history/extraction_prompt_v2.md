You are analyzing a job description to extract structured information for resume tailoring and quick human review. Return ONLY valid JSON — no markdown fences, no explanation, just the raw JSON object.

# Job Posting
Job Title: {title}
Company: {company}
Job Description:
{description}

# Instructions

Return this exact schema:
{
"skills": [
  {"name": "atomic skill token", "category": "short group label or null", "requirement": "required | preferred", "expansion": "spelled-out form, or null if not an acronym"}
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

## Skills

A "skill" is a concrete technology, tool, framework, language, methodology, or professional competency. Do NOT include:
- Credentials or degrees (e.g. "Bachelor's degree") — these are not skills.
- Job or role titles (e.g. "Software Engineer or Programmer", "Coder").
- Generic filler like "proficiency in one programming language" — instead list the specific language(s) the JD names, or omit if none are named.

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

`requirement` — `"required"` if the JD lists it as a must-have/basic qualification, `"preferred"` if listed as nice-to-have/preferred qualification.

## Unmatched requirements

Some qualifications in the JD are real requirements but do not reduce to a clean atomic skill token — e.g. "Experience with creating kill/fault trees to capture aircraft redundancy". Do NOT force these into the `skills` list by truncating them into something misleadingly short, and do NOT silently drop them. Instead, copy them (verbatim or lightly trimmed for readability) into `unmatched_requirements`. If a bullet in the JD contains both an extractable atomic skill AND a longer narrative requirement, do both: pull the atomic skill into `skills`, and also add the fuller requirement text to `unmatched_requirements` if it carries meaning beyond that atomic skill.

## Salary

For `salary_min`/`salary_max`: parse any stated pay range (annual base salary, hourly rate as-is, whatever unit the JD uses) into plain numbers, e.g. "$79,300.00 - $118,900.00" → `salary_min: 79300, salary_max: 118900`. If no range is stated, use `null` for both. If only one figure is given, set both min and max to it.

<!--
ITERATION NOTES (local prompt-tuning workflow — not the live app prompt):
- v1 -> v2 changes, based on review of linkedin_4439590156 / linkedin_4427586312:
  1. Skills restructured from three flat lists (required_skills/preferred_skills/tech_stack)
     into a single `skills` list of {name, category, requirement, expansion} objects.
     Reason: flat lists gave no sense of grouping (MS Office Suite items scattered,
     FEMAP/NASTRAN industry tools indistinguishable from Python/MATLAB languages).
  2. Added `expansion` field for acronym spell-out (FEM -> Finite Element Modeling)
     instead of baking the expansion into `name` (which would break atomic-token rules).
  3. Added `unmatched_requirements` catch-all — v1 silently dropped "Experience with
     creating kill/fault trees to capture aircraft redundancy" because it doesn't
     reduce to a short skill token. v1's prompt had no escape valve for this.
- Base: workflows/prompts/history/extraction_prompt_v1.md (== prompts/defaults/extraction.md
  plus salary parsing).
-->
