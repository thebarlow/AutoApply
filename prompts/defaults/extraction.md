You are analyzing a job description to extract structured information for resume tailoring. Return ONLY valid JSON —
no markdown fences, no explanation, just the raw JSON object.

# Job Posting
Job Title: {title}
Company: {company}
Job Description:
{description}

# Instructions

Return this exact schema:
{
"required_skills": ["required skills ranked by emphasis in the JD"],
"preferred_skills": ["nice-to-have skills explicitly mentioned"],
"tech_stack": ["specific tools, frameworks, and languages named"],
"seniority": "junior | mid | senior | staff | not specified",
"role_type": "IC | manager | hybrid | not specified",
"domain": "1-2 word industry or domain",
"key_responsibilities": ["3-5 concise phrases describing what the role actually does"],
"company_signals": ["values, culture cues, or pain points mentioned in the JD"],
"work_arrangement": "remote | hybrid | onsite | not specified",
"employment_type": "full-time | contract | not specified"
}