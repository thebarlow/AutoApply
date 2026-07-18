You are analyzing a job description to extract structured information for resume tailoring. Return ONLY valid JSON —
no markdown fences, no explanation, just the raw JSON object.

# Job Posting
Job Title: {job.title}
Company: {job.company}
Job Description:
{job.description}

# Instructions

Return this exact schema:
{
"required_skills": ["required SKILLS ranked by emphasis in the JD"],
"preferred_skills": ["nice-to-have SKILLS explicitly mentioned"],
"tech_stack": ["specific tools, frameworks, and languages named"],
"seniority": "junior | mid | senior | staff | not specified",
"role_type": "IC | manager | hybrid | not specified",
"domain": "1-2 word industry or domain",
"key_responsibilities": ["3-5 concise phrases describing what the role actually does"],
"company_signals": ["values, culture cues, or pain points mentioned in the JD"],
"work_arrangement": "remote | hybrid | onsite | not specified",
"employment_type": "full-time | contract | not specified"
}

A "skill" is a concrete technology, tool, framework, language, methodology, or professional competency. For `required_skills`, `preferred_skills`, and `tech_stack`, do NOT include:
- Credentials or degrees (e.g. "Bachelor's degree") — these are not skills.
- Job or role titles (e.g. "Software Engineer or Programmer", "Coder").
- Generic filler like "proficiency in one programming language" — instead list the specific language(s) the JD names, or omit if none are named.

Each entry MUST be an **atomic skill token** — the bare name of the skill, nothing else:
- Strip qualifier phrasing. "Strong proficiency in Python" → `"Python"`. "Experience with REST API development using FastAPI" → `"REST"`, `"FastAPI"`. "Understanding of NLP" → `"NLP"`.
- Never bundle multiple skills into one entry. Split conjunctions and parentheticals into separate entries: "Python (Pandas, NumPy)" → `"Python"`, `"Pandas"`, `"NumPy"`. "TensorFlow or PyTorch" → `"TensorFlow"`, `"PyTorch"`.
- Never put a comma inside an entry.
- Prefer the shortest common name: "the Kubernetes container orchestration platform" → `"Kubernetes"`.