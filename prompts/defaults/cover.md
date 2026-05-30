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
- Before writing, identify the nature, scale, and stakes of the candidate's actual work that map to this role. Paragraph 1 should open with that framing — who the candidate is for THIS role — rather than a generic statement of interest or a technology list.
- Exactly 3 paragraphs: (1) fit and interest, (2) specific value-add tied to the job description, (3) close.
- Do not include a greeting, salutation, or "Dear..." line at the top — it is prepended automatically.
- Do not include a sign-off, name, or contact information at the end — those are added automatically.
- Do not invent experience or skills not in the master resume.
- Role-claiming test: using the job's vocabulary is fine, but never phrase anything such that a hiring manager could conclude the candidate held a title, level, or ownership — or produced an outcome — they did not. Describe only what the master resume actually supports.