You are writing a tailored one-page resume in Markdown for a job application.

# Applicant Details
Hero: {user.hero}
Skills: {user.skills}
Work Experience: {user.work_history}
Projects: {user.projects}


# Job Posting
Title: {job.title}
Company: {job.company}
Location: {job.location}
Description:
{job.description}

# Instructions
- Output ONLY the resume Markdown body. No preamble, no explanation.
- Do NOT include a name or contact block — those are handled separately.
- Start directly with the first section header (e.g. ## Profile).
- Do not use `---` horizontal rules between sections.
- Do not invent experience, skills, or credentials not present in the applicant details.
- Role-claiming test: borrowing the job's vocabulary is fine, but never phrase anything such that a hiring manager could conclude the candidate held a title, level, or ownership — or produced an outcome — they did not. If a phrasing implies a role/result not supported by the applicant details, rewrite it to describe only what they actually did.
- Target a single page at standard margins and 10–11pt body text.

## Profile
- Max 500 characters total.
- Before writing, identify the *nature, scale, and stakes* of this candidate's actual work that map to this role (e.g. "owns a production data platform serving X", "ships ML into live workflows"). Lead the Profile with that framing — the candidate's identity for THIS role — not with a list of technologies.
- Only after the framing is set, weave in the role title/specialization and the keywords the job emphasizes. Keywords support the frame; they do not replace it.

## Experience
- Include all listed work history entries, most recent first.
- Max 2 bullets per entry, each bullet max 120 characters.
- Stress skills and responsibilities directly mentioned in the job description.

## Projects
- Reorder by relevance to this job. Drop the least relevant project(s) if space requires.
- Include at least 2 and at most 4 projects (omit the section entirely if none are listed).
- Do NOT use bullet points. Write each project as a paragraph: bold the project name, then a colon, then a one-sentence description. Max 120 characters per project.

## Skills
- Group skills into categories (e.g. Languages, Frameworks, Tools).
- Include only categories that have 2 or more skills relevant to this job.
- If a category has only 1 relevant skill, fold it into the nearest adjacent category.
- Sort categories by relevance to the job description.
- Within each category, list skills directly mentioned in the job description first.
- Max 6 categories.
