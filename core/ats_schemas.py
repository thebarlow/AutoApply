"""Hand-authored standard-application field maps for supported ATSs.

Maps each ATS's native form-field identifier to a canonical key (see
core/application_fields.py). Only the low-defense, form-based ATSs that
sub-project 3 targets first are covered: greenhouse, lever, ashby. Any other
ats_type has no static schema and relies entirely on dynamic enumeration.
"""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass
class SchemaField:
    """One field in an ATS's standard application form."""

    field_id: str
    label: str
    canonical_key: str
    required: bool = False


STATIC_SCHEMAS: dict[str, list[SchemaField]] = {
    "greenhouse": [
        SchemaField("first_name", "First Name", "first_name", True),
        SchemaField("last_name", "Last Name", "last_name", True),
        SchemaField("email", "Email", "email", True),
        SchemaField("phone", "Phone", "phone"),
        SchemaField("resume", "Resume/CV", "resume_file", True),
        SchemaField("cover_letter", "Cover Letter", "cover_letter_text"),
        SchemaField(
            "job_application[answers_attributes][linkedin]",
            "LinkedIn Profile",
            "linkedin_url",
        ),
    ],
    "lever": [
        SchemaField("name", "Full name", "full_name", True),
        SchemaField("email", "Email", "email", True),
        SchemaField("phone", "Phone", "phone"),
        SchemaField("resume", "Resume/CV", "resume_file", True),
        SchemaField("urls[LinkedIn]", "LinkedIn URL", "linkedin_url"),
        SchemaField("urls[GitHub]", "GitHub URL", "github_url"),
        SchemaField("comments", "Additional information", "cover_letter_text"),
    ],
    "ashby": [
        SchemaField("name", "Name", "full_name", True),
        SchemaField("email", "Email", "email", True),
        SchemaField("phone", "Phone", "phone"),
        SchemaField("resume", "Resume", "resume_file", True),
        SchemaField("linkedin", "LinkedIn", "linkedin_url"),
        SchemaField("github", "GitHub", "github_url"),
    ],
}


def schema_for(ats_type: str) -> list[SchemaField]:
    """Return the static schema for an ATS, or [] if unsupported."""
    return STATIC_SCHEMAS.get(ats_type or "", [])
