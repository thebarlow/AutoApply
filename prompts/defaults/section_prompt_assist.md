You write a concise résumé-section tailoring instruction.

Given a section name and the user's notes about its purpose and how it should adapt per job, output a single short instruction (1–3 sentences, max ~300 characters) telling a résumé generator how to tailor that section to a specific job posting. Match this register: imperative, specific, no preamble.

Output ONLY raw JSON: {"prompt": "<instruction>"}

Section: {section_name}
Purpose: {purpose}
Per-job tailoring: {tailoring}
