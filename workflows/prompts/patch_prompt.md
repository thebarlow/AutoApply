You are revising a tailored résumé to fix specific issues an evaluator found, without touching anything that wasn't flagged. Return ONLY valid JSON in the exact same schema as the input résumé — no markdown fences, no explanation.

# Job
Title: {title}
Company: {company}
Skills this job wants (required/preferred): {skills}
Key responsibilities: {key_responsibilities}

# Candidate's real profile (ground truth)
{profile}

# Current résumé (to revise)
{resume}

# Evaluator's findings — fix ONLY these, leave everything else unchanged
{failing_checks}

# Instructions

Output the full résumé JSON again, in the identical schema (summary, skills, work_history, projects, education), with ONLY the flagged issues corrected:
- If `no_fabrication` failed: remove or rewrite the unsupported claim so it's grounded in the profile, or delete it if it can't be grounded.
- If `no_keyword_stuffing` failed: rewrite the flagged bullet(s) to describe a real action/outcome instead of a tool list, still grounded in the profile.
- If `no_irrelevant_content` failed: remove or deprioritize the flagged skill/bullet.
- If `no_continuity_errors` failed: restore the correct work-history entry/dates/attribution to match the profile exactly.
- If `required_skills_covered` failed: work each missing genuinely-held required skill into the skills list (add it to the most fitting existing category — don't create a new one-item category) and/or an appropriate existing bullet where it's truthfully applicable — do not invent a new accomplishment just to mention it.
- If `summary_specific` failed: rewrite the summary to reference something specific to this role.

Do not change anything not covered by an issue above. Do not re-tailor bullets that weren't flagged. Preserve every work-history entry, in order, exactly as in the current résumé (only content flagged by `no_continuity_errors` may touch entry-level fields). All honesty rules from the original résumé generation still apply — never fabricate to satisfy a check.
