You are writing a concise, tailored cover letter in Markdown for a job application.

# Job (analyzed)
{job.extracted_description}

# The candidate — who they are and what they have actually done (the proof)
{user_profile.master_resume}

# Candidate skill inventory (the ONLY skills you may attribute to them)
{user.skills}

# Instructions
- Output ONLY the cover letter Markdown. No preamble, no explanation, no `---` rules.
- Exactly 3 paragraphs: (1) who the candidate is for THIS role plus genuine interest —
  open with the nature, scale, and stakes of their real work, not a generic statement or
  a technology list; (2) specific value tied to the job's responsibilities and tech stack,
  using the candidate's real work and projects as evidence; (3) a brief, confident close
  with a call to action.
- Naturally reflect the company's signals and values where it fits truthfully — show
  alignment; never copy-paste job-description phrases.
- No greeting/salutation and no sign-off/name/contact — both are added automatically.

# Honesty rules
- Use ONLY skills in the inventory; never invent experience, skills, tools, or outcomes.
- Titles are fixed: never imply a seniority or job title the candidate has not held (no
  "senior", "lead", or an invented role like "Machine Learning Engineer").
- Use proof words ("proven", "expert", "track record", "extensive") ONLY for skills backed
  by the candidate's real work or projects; otherwise use lighter framing or omit.
- Only attach a skill to a role or project that actually used it.
