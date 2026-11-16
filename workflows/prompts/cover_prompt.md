You are writing a short, honest cover letter for a job application. Output ONLY the cover letter text — no preamble, no explanation, no markdown headers, no `---` rules, no greeting/salutation, no sign-off/name/contact (those are added separately).

# Job
Title: {title}
Company: {company}
Summary: {summary}
Key responsibilities: {key_responsibilities}
Company signals (culture/values/pain-points already found in the JD): {company_signals}
Skills this job wants (each has a `source`: `"stated"` = employer explicitly named it, `"inferred"` = not named in the JD but standard for this role): {skills}

# Candidate
{profile}

# Instructions

## Length

**Hard ceiling: never exceed 150 words, no matter what.** Within that ceiling, write only what is genuinely supportable — a strong short letter beats a padded one. There is no target to fill.

## Structure — exactly two paragraphs, each with a distinct job

Do not blend these into one skills-recap. Each paragraph has ONE job; don't let paragraph 2's material bleed into paragraph 1 or vice versa.

**Paragraph 1 — personality and connection, not skills.** This paragraph's only job is to make the candidate read as a specific person who'd fit here, not a stack of keywords. Ground it in ONE of:
- A real trait or working style visible in the candidate's actual project/work choices (e.g. builds things solo end-to-end, picks unusual side-projects out of curiosity, ships rather than over-plans) — pull this from what the profile actually shows, never invent a trait.
- A brief, honest personal-interest line, if it plausibly and truthfully connects to this role/domain — low-key, not performed enthusiasm.
- A specific, true thing about the company (product, mission, recent work) — but only pull this in when it *actually strengthens* the letter, i.e. there's a genuine, non-generic connection to draw. Don't force a company mention if it would just be filler; it's optional, not a checklist item. When the JD's `Company signals` are too thin/generic to supply this, and a company angle would be worth having, use web search to find one concrete, current fact about {company} (a specific product, a recent headline, something they've actually shipped or said — not vague "innovative culture" copy) before writing.

This paragraph must NOT read as a skills or tech-stack list. If it starts turning into "I have experience with X, Y, Z," that belongs in paragraph 2, not here.

A skill's `source` never changes what you can honestly claim about the candidate — it only affects how you talk about the job's wants. Don't write as if the employer explicitly asked for an `inferred` skill; it's fine to demonstrate the candidate has it, just don't frame it as answering a stated requirement that was never stated.

**Paragraph 2 — one concrete proof point.** Pick the SINGLE most relevant thing the candidate has actually built or done for this specific role, and unpack it briefly with real detail (what it does, what was involved) — not a list of technologies bolted onto a sentence. Naming 2-3 tools in service of describing one real thing is fine; reciting a tool inventory is not. If a second proof point is truly load-bearing, one more short sentence is acceptable — but do not pad to hit a paragraph size.

## Enthusiasm

Do not explicitly state enthusiasm ("I'm excited about...", "I would love to...") UNLESS paragraph 1 is grounded in genuine company research or a real personal-interest connection — in those cases a brief, specific, earned line of interest is fine (e.g. "the shift toward X you've been building" — not "I'm excited about your mission"). Otherwise, let paragraph 1's personality grounding and paragraph 2's proof point carry the signal of fit without stating it.

## Tone

Plain and direct. Matter-of-fact and confident, no flourishes, no marketing language, no buzzwords ("leveraging", "passionate", "revolutionize", "cutting-edge"). Write like a competent person describing their own work and interests out loud, not like ad copy.

## Honesty rules (non-negotiable, same as the live app's cover-letter prompt)

- Use ONLY skills/experience actually present in the candidate profile above; never invent experience, skills, tools, or outcomes.
- Never imply a seniority or job title the candidate has not held.
- Use proof words ("proven", "expert", "track record", "extensive") ONLY for things backed by the candidate's real work; otherwise use lighter framing or omit.
- Only attach a skill to a role/project that actually used it.
- NEVER fabricate or inflate scale, volume, throughput, user counts, revenue, team size, or other metrics. If the profile states a concrete figure, use it verbatim; otherwise describe the work qualitatively.
- Describe personal/side projects honestly as such (things the candidate designed and built), not as production systems at commercial scale.
- A personal-interest line, if used, must be something plausibly true and low-key — not an invented passion or a generic "I've always loved technology."

<!--
ITERATION NOTES (local prompt-tuning workflow — not the live app prompt):
- v1 -> v2 changes, based on review of the Genpact/Pearson letters:
  1. v1 had no paragraph structure at all ("say what makes them a fit, optionally one more
     point") — in practice this collapsed into a tech-stack recap (the Genpact letter),
     because "one concrete proof point" was the only instruction with teeth. v2 enforces
     two paragraphs with distinct, named jobs: paragraph 1 is explicitly barred from being
     a skills list and must carry personality/company connection instead; paragraph 2 is
     where the proof point/skills belong.
  2. v1's web-research fallback only fired when company_signals was thin AND the JD gave
     no material at all. v2 makes company research/mention available whenever it would
     genuinely strengthen paragraph 1 (still optional, not mandatory every letter — user
     confirmed forcing it every time isn't wanted), and adds a personal-interest-line option
     as an alternative or complement to it, per user's answer.
  3. v1's "no personality" instruction was absent entirely; v2 explicitly requires paragraph
     1 to be grounded in trait/interest evidence pulled from the profile, not invented.
-->
