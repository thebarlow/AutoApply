# Applicator Context

**Scope: TBD**

This stage will handle submitting job applications using the generated resume and cover letter artifacts from `../generator/outputs/`.

Key design questions to resolve before building:
- Target submission method: direct email, ATS form automation, or human-in-the-loop review + submit
- Which ATS platforms to support (Workday, Greenhouse, Lever, iCIMS, etc.)
- Application tracking: where to log status, follow-up dates, outcomes
