You simulate an Applicant Tracking System résumé parser. Given the raw text
extracted from a résumé PDF, extract the fields below as you believe an
automated parser would read them — do not infer or correct, report what the
text literally supports.

Return ONLY a JSON object — no prose, no code fences.

# Extracted résumé text
{extracted_text}

# Output schema
{"name": "", "email": "", "phone": "", "sections": [], "skills": [], "experience_dates": []}

Rules:
- name/email/phone: the contact values as a parser would isolate them.
- sections: the section headers you detect, lowercased (e.g. "experience").
- skills: individual skill tokens you detect.
- experience_dates: date ranges you detect, as written.
