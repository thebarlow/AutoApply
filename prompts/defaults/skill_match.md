You are assessing which of a job's listed skills a specific candidate already satisfies, based on their FULL profile — not just their skills list, but also their education, work history, and projects.

A skill counts as SATISFIED if any of these is true:
- It appears in, or is an obvious synonym of, the candidate's skills.
- The candidate's work history or projects demonstrate it.
- It is a credential (e.g. a degree) the candidate's education meets.
- It is a broad or generic requirement the candidate clearly meets (e.g. "a programming language" when they know Python; "fluency in English" when their profile is written in fluent English; a job-title-style requirement like "Software Engineer" when their history holds that role).

Be generous with generic/implied requirements the candidate plainly meets, but do NOT credit a concrete technology they have no evidence for.

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
