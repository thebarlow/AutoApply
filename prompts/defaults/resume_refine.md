You are refining a resume to address specific quality issues. You return ONLY tailored prose as a JSON patch; job titles, companies, dates, education, contact info, and project names are fixed facts and must never be changed or invented.

# Applicant Details
Hero: {user.hero}
Skills: {user.skills}

# Job Requirements
Title: {job.title}
Company: {job.company}
Required Skills: {job.ext_required_skills}
Preferred Skills: {job.ext_preferred_skills}
Tech Stack: {job.ext_tech_stack}
Key Responsibilities: {job.ext_key_responsibilities}

# Current Resume Content (refine the prose of these entries)
Profile Summary:
{current_profile_summary}

Experience (each line is `[index] title at company (dates)` — refine by index):
{current_experience_indexed}

Projects (each line is `[index] name` — refine by index):
{current_projects_indexed}

# Issues to Fix
{critique}

# Output contract
Return ONLY a single JSON object (no code fences, no commentary) with exactly these keys:

{
  "profile_summary": "<markdown, max 500 chars>",
  "experience": [ {"ref": <experience index>, "description": "<markdown bullets>"} ],
  "projects":   [ {"ref": <project index>, "description": "<markdown>"} ],
  "skills":     [ {"category": "<name>", "items": ["<skill>", ...]} ]
}

Rules:
- Address every issue listed above.
- `experience`/`projects`: reference each entry ONLY by its `[index]` above. You may not add, remove, reorder, or rename entries — only rewrite each entry's description prose. Max 2 bullets per experience entry, each max 120 chars. Each project description: one sentence, max 120 chars.
- `profile_summary`: lead with the candidate's identity for THIS role, then weave in the role's keywords.
- `skills`: regroup into at most 6 categories; list job-mentioned skills first. Return the full skills set you want (it replaces the existing groups).
- Emphasize hard skills that match or are transferable/adjacent (synonyms count, e.g. NLP = Natural Language Processing). Surface transferable skills honestly — do not claim a tool the applicant lacks.
- Never imply a title, level, ownership, or outcome the applicant details do not support. Borrowing the job's vocabulary is fine; implying a role or result is not.
- Use ONLY the supplied indices. Do not invent a `ref` that is not listed above.
