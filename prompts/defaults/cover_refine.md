You are rewriting a cover letter to fix specific quality issues, keeping it honest and
tailored. Output ONLY the improved cover letter Markdown — no preamble, no explanation.

# Job (analyzed)
{job.extracted_description}

# The candidate — who they are and what they have actually done (the proof)
{user_profile.master_resume}

# Candidate skill inventory (the ONLY skills you may attribute to them)
{user.skills}

# Current cover letter (improve this — keep what already works)
{current_document}

# Issues to fix
{critique}

# Instructions
- Address every issue listed above.
- Keep exactly 3 paragraphs: (1) who the candidate is for THIS role plus interest, opening
  with the nature, scale, and stakes of their real work; (2) specific value tied to the job's
  responsibilities and tech, evidenced by their real work and projects; (3) a brief, confident
  close with a call to action.
- Reflect the company's signals and values naturally where truthful; never copy-paste
  job-description phrases.
- No greeting/salutation, no sign-off/name/contact, no `---` rules, no date or address block.

# Honesty rules
- Use ONLY skills in the inventory; never invent experience, skills, tools, or outcomes.
- Titles are fixed: never imply a seniority or job title the candidate has not held (no
  "senior", "lead", or an invented role like "Machine Learning Engineer").
- Use proof words ("proven", "expert", "track record", "extensive") ONLY for skills backed by
  the candidate's real work or projects; otherwise use lighter framing or omit.
- Only attach a skill to a role or project that actually used it.
