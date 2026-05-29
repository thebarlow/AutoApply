You are rewriting a resume to address specific quality issues. Produce an improved resume.

# Applicant Details
Hero: {user.hero}
Skills: {user.skills}
Work Experience: {user.work_history}
Projects: {user.projects}

# Job Posting
Title: {job.title}
Company: {job.company}
{job.extracted_description}

# Current Resume (improve this)
{current_resume}

# Issues to Fix
{critique}

# Instructions
- Address every issue listed above.
- Do NOT invent experience, skills, or credentials not present in the applicant details.
- Output ONLY the resume Markdown body. No preamble, no explanation.
- Do NOT include a name or contact block.
- Start directly with the first section header (e.g. ## Profile).
- Do not use `---` horizontal rules between sections.
- Target a single page at standard margins and 10–11pt body text.
