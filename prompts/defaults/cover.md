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
  open with the nature and stakes of their real work, not a generic statement or a
  technology list; (2) specific value tied to the job's responsibilities and tech stack,
  using the candidate's real work and projects as evidence; (3) a brief, confident close
  with a call to action.
- LENGTH IS A HARD CONSTRAINT. The letter must fit on one page above a decorative footer,
  so keep it tight: aim for ~225–275 words total, and never exceed 300. Each paragraph is
  2–4 sentences. Prefer one strong, concrete example over several thin ones. Do not pad.
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
- NEVER fabricate or inflate scale, volume, throughput, user counts, revenue, team size, or
  other metrics. Do not invent numbers like "thousands of X per day." If the resume states a
  concrete figure, you may use it verbatim; otherwise describe the work qualitatively (what
  was built and why it mattered) without attaching a made-up quantity.
- Describe personal/side projects honestly AS such — as things the candidate designed and
  built — not as production systems operating at commercial scale. Emphasize the engineering
  (what they architected, the problems solved, the technologies used), not imagined traffic.
- Write like a competent human, not marketing copy. Avoid grandiose, hype, or buzzword-laden
  phrasing that reads as AI-generated ("leveraging cutting-edge", "revolutionize", inflated
  superlatives). Plain, specific, confident language earns more credibility than boasting.
