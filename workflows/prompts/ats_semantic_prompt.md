You simulate an Applicant Tracking System résumé parser, then check whether it recovered the résumé correctly. Two steps.

# Step 1 — parse

Given the raw text extracted from a résumé PDF's text layer, extract the fields below **as you believe an automated ATS parser would read them** — do not infer, correct, or fill gaps intelligently the way a human reader would. Report only what the text literally supports, including its flaws (a parser is dumb; if the layout confused it, say so).

# Extracted résumé text
{extracted_text}

Parse into this schema:
{"name": "", "email": "", "phone": "", "sections": [], "skills": [], "experience_dates": []}

- `name`/`email`/`phone`: the contact values as a naive parser would isolate them from the raw text.
- `sections`: the section headers you detect, lowercased (e.g. "experience").
- `skills`: individual skill tokens you detect.
- `experience_dates`: date ranges you detect, as written.

# Step 2 — diff against ground truth

Ground truth (the document as actually written, not what you parsed):
{ground_truth}

Compare your Step 1 parse against this ground truth and produce a list of issues. Return ONLY valid JSON — no markdown fences, no explanation:

{
"issues": [
  {"layer": "semantic", "severity": "warning", "code": "roundtrip_name | roundtrip_email | roundtrip_phone | roundtrip_sections", "message": "specific, evidence-based description of the mismatch"}
]
}

Rules:
- **All issues here are `"severity": "warning"` — never `"critical"`.** This layer is advisory only; it never blocks. (The critical/hard-block checks already ran separately, mechanically, before this step.)
- `roundtrip_name`: only if ground truth's `header.name` is non-empty AND your parsed `name` is non-empty AND they don't match case-insensitively. Message should include both values.
- `roundtrip_email`: same pattern for `header.email`.
- `roundtrip_phone`: same pattern for `header.phone`.
- `roundtrip_sections`: only if your parsed `sections` list is non-empty (an empty parse means you under-parsed, not that sections are missing — don't penalize that). Compare your parsed sections (case-insensitive) against ground truth's `section_order`; if any ground-truth section has no case-insensitive match in your parsed list, report ONE `roundtrip_sections` issue naming all the missing ones together (don't emit one issue per missing section).
- If nothing is amiss, return `{"issues": []}`.
- Be specific: name the actual parsed value vs. the actual ground-truth value in every message, don't just assert a mismatch occurred.
