You are assessing which of a job's listed skills a specific candidate already satisfies, based on their FULL profile — not just their skills list, but also their education, work history, and projects.

A skill counts as SATISFIED if any of these is true:
- It appears in, or is an obvious synonym of, the candidate's skills.
- The candidate's work history or projects EXPLICITLY name it (the tech/tool/language appears in that entry's text) or unambiguously entail it (e.g. "built a REST API with Django" entails Python).
- It is a credential (e.g. a degree) the candidate's education meets.
- It is a broad or generic requirement — NOT a specific named technology — that the candidate plainly meets from context (e.g. "a programming language" when they know Python; "fluency in English" when their profile is written in fluent English; a job-title-style requirement like "Software Engineer" when their history holds that role).

Be generous ONLY with broad/generic requirements as described above. For any concrete, specific technology, language, framework, tool, or platform (e.g. "React", "AWS", "PostgreSQL"), you MUST find it explicitly named or unambiguously entailed somewhere in the candidate's profile — skills, work history, projects, or education. If the candidate's skills list is empty or thin, do not compensate by inferring concrete technologies from vague or unrelated experience. When in doubt about a concrete technology, do NOT credit it.

# Candidate profile
- Skills: {user.skills}
- Work history:
{user.work_history}
- Education:
{user.education}
- Projects:
{user.projects}

# Skills to assess
{skills_to_match}

# Output
Return ONLY a JSON object, no prose, no code fences. Echo back the exact input strings that are satisfied:
{"matched": ["<verbatim satisfied skill>", "..."]}
Return an empty array if none are satisfied.
