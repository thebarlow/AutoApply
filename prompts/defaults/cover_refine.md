You are rewriting a cover letter to address specific quality issues. Produce an improved cover letter.

# Applicant Details
Hero: {user.hero}
Skills: {user.skills}
Work Experience: {user.work_history}

# Job Posting
Title: {job.title}
Company: {job.company}
{job.extracted_description}

# Current Cover Letter (improve this)
{current_resume}

# Issues to Fix
{critique}

# Instructions
- Address every issue listed above.
- Do NOT invent experience, skills, or credentials not present in the applicant details.
- Output ONLY the cover letter body. No preamble, no explanation.
- Three to four paragraphs: opening hook, relevant experience, company fit, call to action.
- Do not include a date or address block.
