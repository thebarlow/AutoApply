from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import Boolean, Column, Float, Integer, String, Text
from sqlalchemy.orm import Session

from db.database import Base

_OUTPUTS_DIR = Path(__file__).parent.parent / "generator" / "outputs"


def _field_to_str(value: Any) -> str:
    """Render a job or user field value to a string for template substitution."""
    from core.user import WorkHistoryEntry, EducationEntry, ProjectEntry
    if isinstance(value, list):
        if not value:
            return ""
        first = value[0]
        if isinstance(first, WorkHistoryEntry):
            return "\n".join(f"- {e.title} at {e.company} ({e.start}–{e.end}): {e.summary}" for e in value)
        if isinstance(first, EducationEntry):
            return "\n".join(f"- {e.degree} in {e.field} from {e.institution} ({e.graduated}), GPA {e.gpa}" for e in value)
        if isinstance(first, ProjectEntry):
            return "\n".join(
                f"- {e.name}: {e.description}"
                + (f" ({e.url})" if e.url else "")
                + (f" — {', '.join(e.technologies)}" if e.technologies else "")
                for e in value
            )
        return ", ".join(str(v) for v in value)
    if value is None:
        return ""
    return str(value)


def _apply_template(template: str, sources: dict[str, Any]) -> str:
    """Replace {table.field} placeholders using attribute values from sources dict."""
    import re
    def _replace(m: "re.Match[str]") -> str:
        table, field = m.group(1), m.group(2)
        obj = sources.get(table)
        if obj is None:
            return m.group(0)
        value = getattr(obj, field, None)
        if value is None:
            return m.group(0)
        return _field_to_str(value)
    return re.sub(r'\{(\w+)\.(\w+)\}', _replace, template)


class JobState(str, Enum):
    """Valid states for a job in the pipeline."""

    DRAFT = "draft"
    APPLIED = "applied"
    IN_CONTACT = "in_contact"
    REJECTED = "rejected"


class Job(Base):
    """A job posting with all associated pipeline data and behavior.

    Columns cover scraped data, scores, description extraction, and artifact paths.
    All operations that read or write job columns are methods on this class.
    """

    __tablename__ = "jobs"
    __allow_unmapped__ = True
    __table_args__ = {"extend_existing": True}

    # ── Scrape data ────────────────────────────────────────────────────────────
    id = Column(Integer, primary_key=True)
    job_key = Column(String, unique=True, nullable=False)
    source = Column(String, nullable=False)
    title = Column(String)
    company = Column(String)
    location = Column(String)
    salary = Column(String)
    remote = Column(Boolean)
    description = Column(Text)
    url = Column(String, unique=True, nullable=False)
    posted_at = Column(String)
    scraped_at = Column(String, default=lambda: datetime.now(timezone.utc).isoformat())
    state = Column(String, nullable=False, default="draft")

    # ── Scores ─────────────────────────────────────────────────────────────────
    desirability_score = Column(Float)
    fit_score = Column(Float)
    final_score = Column(Float)
    score_justification = Column(Text)

    # ── Extracted description fields ───────────────────────────────────────────
    ext_seniority = Column(String)
    ext_role_type = Column(String)
    ext_domain = Column(String)
    ext_work_arrangement = Column(String)
    ext_employment_type = Column(String)
    ext_required_skills = Column(Text)
    ext_preferred_skills = Column(Text)
    ext_tech_stack = Column(Text)
    ext_key_responsibilities = Column(Text)
    ext_company_signals = Column(Text)

    # ── Artifacts ──────────────────────────────────────────────────────────────
    resume_path = Column(String)
    cover_path = Column(String)
    applied_at = Column(String)
    sheets_row_id = Column(String)

    @classmethod
    def from_scraped(cls, scraped: Any) -> "Job":
        """Construct a Job instance from a ScrapedJob object.

        Does not persist — add the returned instance to a session and commit.

        Args:
            scraped: A ScrapedJob dataclass instance.

        Returns:
            Unsaved Job instance with state set to DRAFT.
        """
        return cls(
            job_key=scraped.job_key,
            source=scraped.source,
            title=scraped.title,
            company=scraped.company,
            url=scraped.url,
            description=scraped.description,
            location=scraped.location,
            salary=scraped.salary,
            remote=scraped.remote,
            posted_at=scraped.posted_at,
            state=JobState.DRAFT.value,
        )

    @classmethod
    def save_batch(cls, scraped_jobs: list[Any], db: Session) -> int:
        """Persist a list of ScrapedJob objects, skipping URL duplicates.

        Args:
            scraped_jobs: List of ScrapedJob instances from a scraper source.
            db: SQLAlchemy session.

        Returns:
            Number of newly inserted jobs.
        """
        count = 0
        for scraped in scraped_jobs:
            if db.query(cls).filter_by(url=scraped.url).first():
                continue
            db.add(cls.from_scraped(scraped))
            count += 1
        db.commit()
        return count

    @classmethod
    def get(cls, job_key: str, db: Session) -> Optional["Job"]:
        """Fetch a single job by job_key.

        Args:
            job_key: Unique job identifier.
            db: SQLAlchemy session.

        Returns:
            Job instance, or None if not found.
        """
        return db.query(cls).filter_by(job_key=job_key).first()

    @classmethod
    def get_or_raise(cls, job_key: str, db: Session) -> "Job":
        """Fetch a single job by job_key, raising if not found.

        Args:
            job_key: Unique job identifier.
            db: SQLAlchemy session.

        Returns:
            Job instance.

        Raises:
            ValueError: If no job with that key exists.
        """
        job = cls.get(job_key, db)
        if job is None:
            raise ValueError(f"Job '{job_key}' not found")
        return job

    @classmethod
    def all_draft(cls, db: Session) -> list["Job"]:
        """Return all DRAFT jobs ordered by final_score descending.

        Args:
            db: SQLAlchemy session.

        Returns:
            List of Job instances in DRAFT state.
        """
        return (
            db.query(cls)
            .filter_by(state=JobState.DRAFT.value)
            .order_by(cls.final_score.desc())
            .all()
        )

    def set_state(self, state: JobState, db: Session) -> None:
        """Set the job's pipeline state and commit.

        Args:
            state: New JobState value.
            db: SQLAlchemy session.
        """
        self.state = state.value
        db.commit()

    def mark_applied(self, db: Session) -> None:
        """Mark this job as applied and record the timestamp.

        Sets state to APPLIED and populates applied_at with the current UTC time.

        Args:
            db: SQLAlchemy session.
        """
        self.state = JobState.APPLIED.value
        self.applied_at = datetime.now(timezone.utc).isoformat()
        db.commit()

    # ── Scoring ────────────────────────────────────────────────────────────────

    def build_score_prompt(self, user: Any) -> str:
        """Build the LLM scoring prompt for this job.

        Args:
            user: A User instance with profile data.

        Returns:
            Prompt string ready to send to the LLM.
        """
        work_history_text = "\n".join(
            f"- {e.title} at {e.company} ({e.start}–{e.end}): {e.summary}"
            for e in user.work_history
        )
        education_text = "\n".join(
            f"- {e.degree} in {e.field} from {e.institution} ({e.graduated}), GPA {e.gpa}"
            for e in user.education
        )
        return f"""You are evaluating a job posting for a candidate. Score the job on two dimensions.

## Candidate Profile
Name: {f"{user.first_name} {user.last_name}".strip() or user.full_name()}
Skills: {", ".join(user.skills)}
Target roles: {", ".join(user.target_roles)}
Target salary: ${user.target_salary_min}–${user.target_salary_max}

Work History:
{work_history_text}

Education:
{education_text}

## Job Posting
Title: {self.title}
Company: {self.company}
Location: {self.location}
Salary: {self.salary or "Not specified"}
Description:
{self.description or "Not provided"}

## Instructions
Return ONLY a JSON object with exactly these four keys:
- desirability_score: float 0.0–1.0 (how much the candidate would want this job)
- fit_score: float 0.0–1.0 (how well the candidate matches the job requirements)
- desirability_justification: string (1–2 sentences explaining desirability score)
- fit_justification: string (1–2 sentences explaining fit score)

Consider for desirability: salary vs target, remote/location fit, role alignment, company quality.
Consider for fit: required skills vs candidate skills, experience level, education requirements.

Return only the JSON object, no other text.
"""

    def score(
        self,
        user: Any,
        config: dict,
        client: Any,
        model: str,
        db: Session,
    ) -> None:
        """Score this job using the LLM. Populates score fields and commits.

        Clamps scores to [0.0, 1.0]. Warns and returns early on LLM error or
        unparseable response without raising.

        Args:
            user: A User instance with profile data.
            config: Dict with keys w1, w2 (scoring weights).
            client: An OpenAI-compatible client instance.
            model: Model identifier string.
            db: SQLAlchemy session.
        """
        import warnings

        prompt = self.build_score_prompt(user)
        try:
            response = client.chat.completions.create(
                model=model,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.choices[0].message.content
        except Exception as e:
            warnings.warn(f"LLM API error for {self.job_key}: {e}")
            return

        required = {"desirability_score", "fit_score", "desirability_justification", "fit_justification"}
        try:
            parsed = json.loads(raw.strip())
            if not required.issubset(parsed.keys()):
                raise ValueError("Missing required keys")
        except (json.JSONDecodeError, ValueError, AttributeError):
            warnings.warn(f"Unparseable LLM response for {self.job_key}: {raw!r}")
            return

        desirability = max(0.0, min(1.0, float(parsed["desirability_score"])))
        fit = max(0.0, min(1.0, float(parsed["fit_score"])))
        w1, w2 = config.get("w1", 0.5), config.get("w2", 0.5)
        final = max(0.0, min(1.0, w1 * desirability + w2 * fit))

        self.desirability_score = desirability
        self.fit_score = fit
        self.final_score = final
        self.score_justification = json.dumps({
            "desirability": parsed["desirability_justification"],
            "fit": parsed["fit_justification"],
        })
        db.commit()

    # ── Description extraction ─────────────────────────────────────────────────

    def build_description_prompt(self, template: str) -> str:
        """Render the description extraction prompt template against this job's fields.

        Supports {job.field} placeholders. Also supports bare {field} placeholders
        (e.g., {description}, {title}) for backwards compatibility with existing prompts.

        Args:
            template: Prompt template string with placeholders.

        Returns:
            Rendered prompt string.
        """
        import re
        result = _apply_template(template, {"job": self})
        def _bare_replace(m: "re.Match[str]") -> str:
            value = getattr(self, m.group(1), None)
            return _field_to_str(value) if value is not None else m.group(0)
        return re.sub(r'\{(\w+)\}', _bare_replace, result)

    def extract_description(self, db: Session) -> None:
        """Extract structured fields from job.description using the LLM.

        Populates all ext_* columns. Skips silently if ext_seniority is already set.
        Resolves the active description prompt from the Config table.

        Args:
            db: SQLAlchemy session.

        Raises:
            RuntimeError: If no active description prompt is configured or the LLM fails.
        """
        if self.ext_seniority is not None:
            return

        from core.llm import get_client_for_named_provider
        import re

        prompt_cfg = self._resolve_active_prompt(db, "description")
        actual_prompt = self.build_description_prompt(prompt_cfg["content"])
        client, model = get_client_for_named_provider(
            db, prompt_cfg["provider_name"], prompt_cfg["model_id"]
        )

        response = client.chat.completions.create(
            model=model,
            max_tokens=2048,
            messages=[{"role": "user", "content": actual_prompt}],
        )
        choice = response.choices[0]
        raw = choice.message.content
        if not raw:
            raise RuntimeError(f"LLM returned empty extraction response (finish_reason={choice.finish_reason!r})")
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw.strip())
        result = raw.strip()
        if not result:
            raise RuntimeError("LLM extraction returned empty content after fence stripping")
        try:
            data = json.loads(result)
        except (json.JSONDecodeError, ValueError) as exc:
            raise RuntimeError(f"LLM extraction is not valid JSON: {exc}") from exc

        self.ext_seniority = data.get("seniority", "")
        self.ext_role_type = data.get("role_type", "")
        self.ext_domain = data.get("domain", "")
        self.ext_work_arrangement = data.get("work_arrangement", "")
        self.ext_employment_type = data.get("employment_type", "")
        self.ext_required_skills = ", ".join(data.get("required_skills") or [])
        self.ext_preferred_skills = ", ".join(data.get("preferred_skills") or [])
        self.ext_tech_stack = ", ".join(data.get("tech_stack") or [])
        self.ext_key_responsibilities = ", ".join(data.get("key_responsibilities") or [])
        self.ext_company_signals = ", ".join(data.get("company_signals") or [])
        db.flush()
        db.commit()

    @staticmethod
    def _resolve_active_prompt(db: Session, type_: str) -> dict:
        """Return the active prompt config dict for a given type.

        Args:
            db: SQLAlchemy session.
            type_: Prompt type key (e.g., 'description', 'resume', 'cover').

        Returns:
            Prompt config dict with keys: id, content, provider_name, model_id.

        Raises:
            RuntimeError: If no active prompt is configured for the given type.
        """
        from db.database import Config
        def _get(key: str) -> str:
            row = db.query(Config).filter_by(key=key).first()
            return row.value if row else ""
        active_id = _get(f"active_{type_}_prompt_id")
        prompts = json.loads(_get(f"{type_}_prompts") or "[]")
        prompt = next((p for p in prompts if p["id"] == active_id), None)
        if not prompt:
            raise RuntimeError(f"No active {type_} prompt configured. Set one under Config → Scaffolding.")
        return prompt

    # ── Generation ─────────────────────────────────────────────────────────────

    def build_resume_prompt(self, user: Any, template: str, db: Session) -> str:
        """Render the resume generation prompt.

        Handles the {user_profile.master_resume} virtual placeholder (reads from
        user.master_resume()) and {job.extracted_description} (auto-runs extraction
        if ext_* columns are empty).

        Args:
            user: A User instance with profile data.
            template: Prompt template string with placeholders.
            db: SQLAlchemy session (used for auto-extraction if needed).

        Returns:
            Rendered prompt string.
        """
        template = template.replace("{user_profile.master_resume}", user.master_resume())
        if "{job.extracted_description}" in template:
            if not self.ext_seniority:
                self.extract_description(db)
            extracted_md = self._ext_to_markdown()
            template = template.replace("{job.extracted_description}", extracted_md)
        return _apply_template(template, {"job": self, "user_profile": user})

    def build_cover_prompt(self, user: Any, template: str, db: Session) -> str:
        """Render the cover letter generation prompt.

        Handles the same virtual placeholders as build_resume_prompt.

        Args:
            user: A User instance with profile data.
            template: Prompt template string with placeholders.
            db: SQLAlchemy session (used for auto-extraction if needed).

        Returns:
            Rendered prompt string.
        """
        return self.build_resume_prompt(user, template, db)

    def generate_resume_md(
        self,
        user: Any,
        prompt_content: str,
        client: Any,
        model: str,
        db: Session,
    ) -> None:
        """Generate resume markdown via LLM and write to generator/outputs/.

        Writes to generator/outputs/{job_key}_resume.md, prepending YAML front matter
        with the user's contact info.

        Args:
            user: A User instance with profile data.
            prompt_content: Prompt template string.
            client: An OpenAI-compatible client instance.
            model: Model identifier string.
            db: SQLAlchemy session.
        """
        from core.llm import call_llm
        from core.utils import strip_header_block

        _OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        frontmatter = self._build_frontmatter(user, db)
        prompt = self.build_resume_prompt(user, prompt_content, db)
        content = call_llm(prompt, client, model)
        content = strip_header_block(content)
        md_path = _OUTPUTS_DIR / f"{self.job_key}_resume.md"
        md_path.write_text(frontmatter + content, encoding="utf-8")

    def generate_cover_md(
        self,
        user: Any,
        prompt_content: str,
        client: Any,
        model: str,
        db: Session,
    ) -> None:
        """Generate cover letter markdown via LLM and write to generator/outputs/.

        Writes to generator/outputs/{job_key}_cover.md, prepending YAML front matter.

        Args:
            user: A User instance with profile data.
            prompt_content: Prompt template string.
            client: An OpenAI-compatible client instance.
            model: Model identifier string.
            db: SQLAlchemy session.
        """
        from core.llm import call_llm

        _OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        frontmatter = self._build_frontmatter(user, db)
        prompt = self.build_cover_prompt(user, prompt_content, db)
        content = call_llm(prompt, client, model)
        md_path = _OUTPUTS_DIR / f"{self.job_key}_cover.md"
        md_path.write_text(frontmatter + content, encoding="utf-8")

    def generate_resume_pdf(self, template_path: Path, db: Session) -> None:
        """Render resume PDF from existing markdown and update resume_path.

        Requires generator/outputs/{job_key}_resume.md to exist.

        Args:
            template_path: Path to the LaTeX template file.
            db: SQLAlchemy session.

        Raises:
            FileNotFoundError: If the resume markdown file does not exist.
        """
        from core.utils import render_resume_pdf

        md_path = _OUTPUTS_DIR / f"{self.job_key}_resume.md"
        if not md_path.exists():
            raise FileNotFoundError(f"Resume markdown not found: {md_path}")
        pdf_path = _OUTPUTS_DIR / f"{self.job_key}_resume.pdf"
        render_resume_pdf(md_path, pdf_path, self.job_key, template_path)
        self.resume_path = str(pdf_path)
        db.commit()

    def generate_cover_pdf(self, template_path: Path, db: Session) -> None:
        """Render cover letter PDF from existing markdown and update cover_path.

        Requires generator/outputs/{job_key}_cover.md to exist.

        Args:
            template_path: Path to the LaTeX template file.
            db: SQLAlchemy session.

        Raises:
            FileNotFoundError: If the cover letter markdown file does not exist.
        """
        from core.utils import render_pdf

        md_path = _OUTPUTS_DIR / f"{self.job_key}_cover.md"
        if not md_path.exists():
            raise FileNotFoundError(f"Cover markdown not found: {md_path}")
        pdf_path = _OUTPUTS_DIR / f"{self.job_key}_cover.pdf"
        render_pdf(md_path, pdf_path, template_path)
        self.cover_path = str(pdf_path)
        db.commit()

    # ── Private helpers ────────────────────────────────────────────────────────

    def _ext_to_markdown(self) -> str:
        """Format the extracted description fields as human-readable markdown.

        Returns:
            Markdown string with sections for overview metadata, skills, tech stack,
            responsibilities, and company signals.
        """
        sections = []
        meta = []
        for attr, label in [
            ("ext_seniority", "Seniority"), ("ext_role_type", "Role Type"),
            ("ext_domain", "Domain"), ("ext_work_arrangement", "Work Arrangement"),
            ("ext_employment_type", "Employment Type"),
        ]:
            if val := getattr(self, attr, ""):
                meta.append(f"**{label}:** {val}")
        if meta:
            sections.append("## Overview\n\n" + "\n\n".join(meta))
        for attr, heading in [
            ("ext_required_skills", "Required Skills"),
            ("ext_preferred_skills", "Preferred Skills"),
            ("ext_tech_stack", "Tech Stack"),
            ("ext_key_responsibilities", "Key Responsibilities"),
            ("ext_company_signals", "Company Signals"),
        ]:
            raw = getattr(self, attr, "") or ""
            items = [i.strip() for i in raw.split(",") if i.strip()]
            if items:
                sections.append(f"## {heading}\n" + "\n".join(f"- {item}" for item in items))
        return "\n\n".join(sections)

    def _build_frontmatter(self, user: Any, db: Session) -> str:
        """Build YAML front matter for resume/cover letter markdown files.

        Reads resume_github, resume_linkedin, resume_website from the Config table.

        Args:
            user: A User instance with contact info.
            db: SQLAlchemy session.

        Returns:
            YAML front matter string ending with a blank line.
        """
        from db.database import Config

        def _cfg(key: str) -> str:
            row = db.query(Config).filter_by(key=key).first()
            return row.value if row else ""

        full_name = user.full_name()
        first = user.first_name or full_name.split(" ", 1)[0]
        last = user.last_name or (full_name.split(" ", 1)[1] if " " in full_name else "")
        github = _cfg("resume_github")
        linkedin = _cfg("resume_linkedin")
        website = _cfg("resume_website")

        lines = [
            "---",
            f"name: {full_name}", f"firstname: {first}", f"lastname: {last}",
            f"email: {user.email}", f"phone: {user.phone}", f"location: {user.location}",
        ]
        if github:
            lines.append(f"github: {github}")
        if linkedin:
            lines.append(f"linkedin: {linkedin}")
        if website:
            lines.append(f"website: {website}")
        lines.extend(["---", ""])
        return "\n".join(lines) + "\n"

    def serialize(self) -> dict:
        """Return a JSON-serializable dict of all job fields for the API.

        Parses score_justification JSON if stored as a string. Checks for
        generated markdown and PDF artifacts on disk.

        Returns:
            Dict with all job fields suitable for API responses.
        """
        justification = self.score_justification
        if isinstance(justification, str):
            try:
                justification = json.loads(justification)
            except (json.JSONDecodeError, TypeError):
                justification = {}
        return {
            "job_key": self.job_key,
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "salary": self.salary,
            "url": self.url,
            "description": self.description,
            "remote": self.remote,
            "state": self.state,
            "desirability_score": self.desirability_score,
            "fit_score": self.fit_score,
            "final_score": self.final_score,
            "score_justification": justification,
            "resume_path": self.resume_path,
            "cover_path": self.cover_path,
            "resume_md_exists": (_OUTPUTS_DIR / f"{self.job_key}_resume.md").exists(),
            "cover_md_exists": (_OUTPUTS_DIR / f"{self.job_key}_cover.md").exists(),
            "extraction_json_exists": bool(self.ext_required_skills or self.ext_seniority),
            "scraped_at": self.scraped_at or "",
        }
