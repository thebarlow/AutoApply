You are writing a tailored one-page resume in Markdown for a job application.

# Applicant Details
Hero: {user.hero}
Skills: {user.skills}
Work Experience: {user.work_history}
Education: {user.education}
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
- Target a single page at standard margins and 10–11pt body text.

## Profile
- Max 500 characters total.
- Lead with the role title or specialization that matches the job posting.

## Education
- Include all degrees exactly as written. No bullets.

## Experience
- Include all listed work history entries, most recent first.
- Max 2 bullets per entry, each bullet max 120 characters.
- Stress skills and responsibilities directly mentioned in the job description.

## Projects
- Reorder by relevance to this job. Drop the least relevant project(s) if space requires.
- Include at least 2 and at most 4 projects (omit the section entirely if none are listed).
- 1 bullet per project, max 120 characters.

## Skills
- Group skills into categories (e.g. Languages, Frameworks, Tools).
- Include only categories that have 2 or more skills relevant to this job.
- If a category has only 1 relevant skill, fold it into the nearest adjacent category.
- Sort categories by relevance to the job description.
- Within each category, list skills directly mentioned in the job description first.
- Max 6 categories.
