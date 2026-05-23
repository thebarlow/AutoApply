You are writing a tailored one-page resume in Markdown for a job application.

# Master Resume
Skills: {user.skills}

# Job Posting
Title: {title}
Company: {company}
Location: {location}
Description:
{description}

# Instructions
- Output ONLY the resume Markdown body. No preamble, no explanation.
- Do NOT include a name or contact block — those are handled separately.
- Start directly with the first section header (e.g. ## Profile).
- Do not use `---` horizontal rules between sections.
- Do not invent experience or skills not in the master resume.
- Drop the Soft Skills section entirely.

## Profile
- Max 500 characters total.

## Education
- Always include both degrees exactly as written. No bullets.

## Experience
- Always include all 3 entries.
- Max 2 bullets per entry, each bullet max 120 characters.
- Stress skills and responsibilities directly mentioned in the job description.

## Projects
- Reorder by relevance to this job. Drop least relevant project(s) if needed.
- Always include at least 2, max 4 projects.
- 1 bullet per project, max 120 characters.

## Skills
- Always include Python, Git, Docker, SQL regardless of job description.
- Include only categories that have 2 or more relevant skills for this job.
- If a category has only 1 relevant skill, fold it into the nearest adjacent category.
- Sort categories by relevance to the job description.
- Within each category, list skills directly mentioned in the job description first.
- Max 6 categories.