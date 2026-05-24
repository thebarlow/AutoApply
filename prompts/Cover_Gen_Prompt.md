You are writing a concise cover letter in Markdown for a job application.

# Master Resume
{user_profile.master_resume}

# Job Posting
Title: {job.title}
Company: {job.company}
Location: {job.location}
Description:
{job.description}

# Instructions
- Output ONLY the cover letter Markdown. No preamble, no explanation.
- Do not use `---` horizontal rules anywhere in the output.
- Exactly 3 paragraphs: (1) fit and interest, (2) specific value-add tied to the job description, (3) close.
- Address it to the hiring team at {job.company}.
- Do not include a sign-off, name, or contact information at the end — those are added automatically.
- Do not invent experience or skills not in the master resume.