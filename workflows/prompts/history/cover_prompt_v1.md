You are writing a short, honest cover letter for a job application. Output ONLY the cover letter text — no preamble, no explanation, no markdown headers, no `---` rules, no greeting/salutation, no sign-off/name/contact (those are added separately).

# Job
Title: {title}
Company: {company}
Summary: {summary}
Key responsibilities: {key_responsibilities}
Company signals (culture/values/pain-points already found in the JD): {company_signals}
Skills this job wants: {skills}

# Candidate
{profile}

# Instructions

## Length

There is no fixed paragraph count or target word count to fill. Write only what is genuinely supportable by the candidate's real experience — say less if there is less to say. **Hard ceiling: never exceed 150 words, no matter what.** A strong 60-word letter beats a padded 150-word one.

## Structure and content

Say, in whatever length that actually takes (within the ceiling):
1. What makes this candidate a fit for *this specific role* — grounded in one concrete, real thing they've built or done, not a skills list.
2. Optionally, if there's a second genuinely relevant proof point, one more — but only if it earns its word count. Do not pad to hit a paragraph count.

Do not explicitly state enthusiasm or interest ("I'm excited about...", "I would love to..."). Let the relevance of the proof point itself carry the signal that this candidate cares about this specific role. The one exception is the company-research fallback below, where a brief, specific, earned line of interest is allowed.

## When the job description gives you little to work with

If `Company signals` above is thin/generic (empty, or just boilerplate like "great benefits", "fast-paced environment") and the job description itself doesn't give you enough specific material to write a grounded first paragraph, do this before writing:

1. Use web search to look up {company} — find one concrete, current thing about it: a specific product, a recent headline, a stated mission, something they've actually shipped or said. Not vague "we're innovative" corporate copy — something you could not have guessed without looking.
2. Reference that one concrete thing briefly and naturally, and it's fine here to state a specific reason for interest tied to it (e.g. "the shift toward X you've been building" — not "I'm excited about your mission"). This is the one place a stated-interest line is allowed, because it's earned by actual research rather than generic enthusiasm.
3. Still ground the rest of the letter in the candidate's real proof points as usual.

If the JD *does* give you enough material (company_signals has something specific, or the responsibilities/summary connect clearly to the candidate's real work), skip the research step — don't manufacture research findings when the JD already gives you something concrete to work with.

## Tone

Plain and direct. Matter-of-fact and confident, no flourishes, no marketing language, no buzzwords ("leveraging", "passionate", "revolutionize", "cutting-edge"). Write like a competent person describing their own work out loud, not like ad copy.

## Honesty rules (non-negotiable, same as the live app's cover-letter prompt)

- Use ONLY skills/experience actually present in the candidate profile above; never invent experience, skills, tools, or outcomes.
- Never imply a seniority or job title the candidate has not held.
- Use proof words ("proven", "expert", "track record", "extensive") ONLY for things backed by the candidate's real work; otherwise use lighter framing or omit.
- Only attach a skill to a role/project that actually used it.
- NEVER fabricate or inflate scale, volume, throughput, user counts, revenue, team size, or other metrics. If the profile states a concrete figure, use it verbatim; otherwise describe the work qualitatively.
- Describe personal/side projects honestly as such (things the candidate designed and built), not as production systems at commercial scale.
