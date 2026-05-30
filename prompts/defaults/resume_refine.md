You are rewriting a resume to address specific quality issues. Produce an improved resume.

# Applicant Details
Hero: {user.hero}
Hard Skills: {user.skills}

# Job Requirements
Title: {job.title}
Company: {job.company}
Required Skills: {job.ext_required_skills}
Preferred Skills: {job.ext_preferred_skills}
Tech Stack: {job.ext_tech_stack}
Key Responsibilities: {job.ext_key_responsibilities}

# Current Resume (improve this)
{current_document}

# Issues to Fix
{critique}

# Instructions
- Address every issue listed above.
- Emphasize the applicant's hard skills that match or are transferable/adjacent to the job's requirements (treat synonyms and alternate spellings as matches, e.g. NLP = Natural Language Processing). Surface transferable skills honestly — do not claim a tool the applicant lacks.
- Do NOT invent specific tools, technologies, certifications, or degrees not present in the applicant hard skills.
- Soft skills, professional terminology, and general practices (e.g. "observability", "leadership") are always acceptable.
- Output ONLY the resume Markdown body. No preamble, no explanation.
- Do NOT include a name or contact block.
- Start directly with the first section header (e.g. ## Profile).
- Do not use `---` horizontal rules between sections.
- Target a single page at standard margins and 10–11pt body text.
