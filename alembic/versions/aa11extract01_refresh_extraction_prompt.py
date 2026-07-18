"""refresh unmodified extraction prompts to the atomic-skill default

Revision ID: aa11extract01
Revises: aa10units01
Create Date: 2026-07-18 00:00:00.000000

The job-view skill chips showed false résumé gaps because the extraction prompt
emitted verbose phrases ("Strong proficiency in Python") and comma-bearing
parentheticals, so the whole-phrase skill key never matched an atomic profile
skill. Commit 2ed4745 tightened ``prompts/defaults/extraction.md`` to require
atomic skill tokens, but seed files only reach NEW signups — existing hosted
profiles keep the old default in their ``prompts`` rows.

This migrates every extraction prompt whose stored content is byte-for-byte the
old factory default (i.e. the user never customised it) to the new default, and
refreshes the ``prompt_defaults`` factory row likewise. User-customised prompts
(content differing from the old default) are left untouched.

Idempotent: rows already carrying the new default no longer match ``_OLD`` and
are skipped. ``downgrade`` restores the old default on the same unmodified rows.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "aa11extract01"
down_revision: Union[str, Sequence[str], None] = "aa10units01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_OLD = """You are analyzing a job description to extract structured information for resume tailoring. Return ONLY valid JSON —
no markdown fences, no explanation, just the raw JSON object.

# Job Posting
Job Title: {job.title}
Company: {job.company}
Job Description:
{job.description}

# Instructions

Return this exact schema:
{
"required_skills": ["required SKILLS ranked by emphasis in the JD"],
"preferred_skills": ["nice-to-have SKILLS explicitly mentioned"],
"tech_stack": ["specific tools, frameworks, and languages named"],
"seniority": "junior | mid | senior | staff | not specified",
"role_type": "IC | manager | hybrid | not specified",
"domain": "1-2 word industry or domain",
"key_responsibilities": ["3-5 concise phrases describing what the role actually does"],
"company_signals": ["values, culture cues, or pain points mentioned in the JD"],
"work_arrangement": "remote | hybrid | onsite | not specified",
"employment_type": "full-time | contract | not specified"
}

A "skill" is a concrete technology, tool, framework, language, methodology, or professional competency. For `required_skills` and `preferred_skills`, do NOT include:
- Credentials or degrees (e.g. "Bachelor's degree") — these are not skills.
- Job or role titles (e.g. "Software Engineer or Programmer", "Coder").
- Generic filler like "proficiency in one programming language" — instead list the specific language(s) the JD names, or omit if none are named.
Keep each skill a short noun phrase, not a sentence."""


_NEW = """You are analyzing a job description to extract structured information for resume tailoring. Return ONLY valid JSON —
no markdown fences, no explanation, just the raw JSON object.

# Job Posting
Job Title: {job.title}
Company: {job.company}
Job Description:
{job.description}

# Instructions

Return this exact schema:
{
"required_skills": ["required SKILLS ranked by emphasis in the JD"],
"preferred_skills": ["nice-to-have SKILLS explicitly mentioned"],
"tech_stack": ["specific tools, frameworks, and languages named"],
"seniority": "junior | mid | senior | staff | not specified",
"role_type": "IC | manager | hybrid | not specified",
"domain": "1-2 word industry or domain",
"key_responsibilities": ["3-5 concise phrases describing what the role actually does"],
"company_signals": ["values, culture cues, or pain points mentioned in the JD"],
"work_arrangement": "remote | hybrid | onsite | not specified",
"employment_type": "full-time | contract | not specified"
}

A "skill" is a concrete technology, tool, framework, language, methodology, or professional competency. For `required_skills`, `preferred_skills`, and `tech_stack`, do NOT include:
- Credentials or degrees (e.g. "Bachelor's degree") — these are not skills.
- Job or role titles (e.g. "Software Engineer or Programmer", "Coder").
- Generic filler like "proficiency in one programming language" — instead list the specific language(s) the JD names, or omit if none are named.

Each entry MUST be an **atomic skill token** — the bare name of the skill, nothing else:
- Strip qualifier phrasing. "Strong proficiency in Python" → `"Python"`. "Experience with REST API development using FastAPI" → `"REST"`, `"FastAPI"`. "Understanding of NLP" → `"NLP"`.
- Never bundle multiple skills into one entry. Split conjunctions and parentheticals into separate entries: "Python (Pandas, NumPy)" → `"Python"`, `"Pandas"`, `"NumPy"`. "TensorFlow or PyTorch" → `"TensorFlow"`, `"PyTorch"`.
- Never put a comma inside an entry.
- Prefer the shortest common name: "the Kubernetes container orchestration platform" → `"Kubernetes"`."""


def _swap(from_text: str, to_text: str) -> None:
    """Replace unmodified extraction defaults (`prompts` + `prompt_defaults`).

    Compares on the rstrip'd content so a stray trailing newline on the stored
    copy still counts as unmodified; user-customised prompts never match.
    """
    conn = op.get_bind()
    from_norm = from_text.rstrip()
    # `prompts` is keyed by a surrogate id; `prompt_defaults` by its type_key PK.
    for table, key in (("prompts", "id"), ("prompt_defaults", "type_key")):
        rows = conn.execute(
            sa.text(f"SELECT {key} AS k, content FROM {table} WHERE type_key = 'extraction'")
        ).fetchall()
        for row in rows:
            if (row.content or "").rstrip() == from_norm:
                conn.execute(
                    sa.text(f"UPDATE {table} SET content = :c WHERE {key} = :k"),
                    {"c": to_text, "k": row.k},
                )


def upgrade() -> None:
    _swap(_OLD, _NEW)


def downgrade() -> None:
    _swap(_NEW, _OLD)
