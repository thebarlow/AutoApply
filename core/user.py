from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import ClassVar, List, Optional

from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.orm import Session

from db.database import Base
import db.database as _db_core  # noqa: F401 — ensures Config/FieldHelp registered with Base.metadata


_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

_PROMPT_TYPES = ("scoring", "resume", "cover", "extraction", "intake", "resume_parse")

_PROMPT_LABELS: dict[str, str] = {
    "scoring": "Scoring",
    "resume": "Resume Generation",
    "cover": "Cover Letter Generation",
    "extraction": "Description Processing",
    "intake": "Intake",
    "resume_parse": "Resume Parsing",
}


class PromptNotConfiguredError(Exception):
    """Raised when a required prompt is not configured for the active profile."""


_DEFAULT_RESUME_PARSE_PROMPT = """\
You are a resume parser. Extract structured data from the resume text the user provides.
Return ONLY a JSON object — no markdown fences, no prose, no explanation.

Use this exact schema:
{
  "name": "string",
  "first_name": "string",
  "last_name": "string",
  "email": "string",
  "phone": "string",
  "location": "string",
  "skills": ["string"],
  "work_history": [
    {"title": "string", "company": "string", "start": "string", "end": "string", "summary": "string"}
  ],
  "education": [
    {"institution": "string", "degree": "string", "field": "string", "graduated": "string", "gpa": number}
  ],
  "projects": [
    {"name": "string", "description": "string", "url": "string", "technologies": ["string"]}
  ]
}

Rules:
- Use empty string "" for missing string fields.
- Use 0.0 for missing gpa.
- Use [] for missing list fields.
- For start/end dates use the format found in the resume (e.g. "2022-01" or "Jan 2022").
- "end" should be "Present" if the role is current.\
"""


@dataclasses.dataclass
class WorkHistoryEntry:
    """A single entry in a user's work history."""

    company: str
    title: str
    start: str
    end: str
    summary: str


@dataclasses.dataclass
class EducationEntry:
    """A single education credential."""

    institution: str
    degree: str
    field: str
    graduated: str
    gpa: float


@dataclasses.dataclass
class ProjectEntry:
    """A personal, academic, or side project."""

    name: str
    description: str
    url: str = ""
    technologies: list[str] = dataclasses.field(default_factory=list)


class User(Base):
    """User profile: stored as a JSON blob in the DB, surfaced as typed Python attributes.

    Use User.load() to fetch from the database. Profile fields (email, skills, etc.)
    are not SQLAlchemy columns — they are populated by _hydrate() after loading.
    Use user.save() to persist changes back to the DB.
    """

    __tablename__ = "user_profile"
    # Profile fields live in the JSON `data` column and are set by _hydrate(),
    # not declared as Mapped[] — suppress SQLAlchemy 2.x unmapped attr errors.
    __allow_unmapped__ = True

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, default="Default")
    data = Column(Text, nullable=False, default="{}")

    # Profile attributes are not columns — set as instance attrs by _hydrate()

    def _hydrate(self) -> bool:
        """Deserialize the JSON data column into typed instance attributes.

        Returns True if legacy text-blob prompts were migrated to files (caller should save).
        """
        raw = json.loads(self.data or "{}")
        self.first_name = raw.get("first_name", "")
        self.last_name = raw.get("last_name", "")
        self.hero = raw.get("hero", "")
        self.email = raw.get("email", "")
        self.phone = raw.get("phone", "")
        self.linkedin = raw.get("linkedin", "")
        self.github = raw.get("github", "")
        self.location = raw.get("location", "")
        self.skills = raw.get("skills", [])
        self.work_history = [WorkHistoryEntry(**e) for e in raw.get("work_history", [])]
        self.education = [EducationEntry(**e) for e in raw.get("education", [])]
        self.projects = [ProjectEntry(**e) for e in raw.get("projects", [])]
        self.target_salary_min = raw.get("target_salary_min")
        self.target_salary_max = raw.get("target_salary_max")
        self.target_roles = raw.get("target_roles", [])
        self.resume_path = raw.get("resume_path", "")
        self.md_path = raw.get("md_path", "")
        self.website = raw.get("website", "")
        self.llm_provider_type = raw.get("llm_provider_type", "")
        self.llm_model = raw.get("llm_model", "")

        migrated = False
        for type_key in _PROMPT_TYPES:
            field = f"prompt_{type_key}"
            model_field = f"prompt_{type_key}_model"
            val = raw.get(field, "")
            # Migration: if value is a text blob (not a .md file path), write to file
            if val and ("\n" in val or not val.endswith(".md")):
                _PROMPTS_DIR.mkdir(exist_ok=True)
                dest = _PROMPTS_DIR / f"{type_key}_{self.id}.md"
                dest.write_text(val, encoding="utf-8")
                val = str(dest)
                migrated = True
            setattr(self, field, val)
            setattr(self, model_field, raw.get(model_field, ""))
        return migrated

    def _to_dict(self) -> dict:
        """Serialize profile attributes to a dict for JSON storage."""
        d = {
            "first_name": self.first_name,
            "last_name": self.last_name,
            "hero": self.hero,
            "email": self.email,
            "phone": self.phone,
            "linkedin": self.linkedin,
            "github": self.github,
            "location": self.location,
            "skills": self.skills,
            "work_history": [dataclasses.asdict(e) for e in self.work_history],
            "education": [dataclasses.asdict(e) for e in self.education],
            "projects": [dataclasses.asdict(e) for e in self.projects],
            "target_salary_min": self.target_salary_min,
            "target_salary_max": self.target_salary_max,
            "target_roles": self.target_roles,
            "resume_path": self.resume_path,
            "md_path": self.md_path,
            "website": self.website,
            "llm_provider_type": self.llm_provider_type,
            "llm_model": self.llm_model,
        }
        for type_key in _PROMPT_TYPES:
            d[f"prompt_{type_key}"] = getattr(self, f"prompt_{type_key}", "")
            d[f"prompt_{type_key}_model"] = getattr(self, f"prompt_{type_key}_model", "")
        return d

    @classmethod
    def load(cls, db: Session, profile_id: Optional[int] = None) -> "User":
        """Load the active user profile from the database.

        Checks the active_profile_id config key first. Falls back to the first row.

        Args:
            db: SQLAlchemy session.
            profile_id: Optional explicit profile ID. Overrides active_profile_id config.

        Returns:
            Hydrated User instance.

        Raises:
            RuntimeError: If no profile exists in the database.
        """
        from db.database import Config

        row: Optional[User] = None

        if profile_id is not None:
            row = db.query(cls).filter_by(id=profile_id).first()
        else:
            active_raw = db.query(Config).filter_by(key="active_profile_id").first()
            if active_raw and active_raw.value:
                try:
                    row = db.query(cls).filter_by(id=int(active_raw.value)).first()
                except (ValueError, TypeError):
                    pass

        if row is None:
            row = db.query(cls).first()

        if row is None:
            raise RuntimeError("No user profile found. Add one via /config.")

        migrated = row._hydrate()
        if migrated:
            row.save(db)
        return row

    @classmethod
    def load_from_json(cls, path: str, db: Session) -> None:
        """Upsert a user profile from a JSON file on disk.

        Replaces db/seed_profile.py. Creates a new profile row if none exists,
        otherwise updates the first row.

        Args:
            path: Filesystem path to a JSON file conforming to the profile schema.
            db: SQLAlchemy session.
        """
        with open(path) as f:
            data = json.load(f)
        name = data.get("name", "") or f"{data.get('first_name', '')} {data.get('last_name', '')}".strip() or "Default"
        row = db.query(cls).first()
        if row:
            row.name = name
            row.data = json.dumps(data)
        else:
            db.add(cls(name=name, data=json.dumps(data)))
        db.commit()

    @classmethod
    def from_markdown(cls, md_text: str, db: Session) -> dict:
        """Parse resume markdown into a structured profile dict via LLM.

        Does not persist — caller decides what to do with the result.

        Args:
            md_text: Plain text or markdown of a resume.
            db: SQLAlchemy session (used to resolve the active LLM provider and user prefs).

        Returns:
            Dict conforming to the profile schema. resume_path and md_path are
            always present but empty.

        Raises:
            ValueError: If the LLM returns invalid JSON.
        """
        import re
        from core.llm import get_client_for_profile
        from core.job import _apply_template

        active_user = cls.load(db)
        try:
            prompt_text = active_user.resolve_prompt("resume_parse")
            system_prompt = _apply_template(prompt_text, {"user": active_user})
        except PromptNotConfiguredError:
            raise
        try:
            client, model = get_client_for_profile(active_user, active_user.prompt_resume_parse_model)
        except RuntimeError:
            raise
        response = client.chat.completions.create(
            model=model,
            temperature=0,
            timeout=30,
            max_tokens=1500,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": md_text},
            ],
        )
        raw = response.choices[0].message.content or ""
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        raw = re.sub(r"\s*```$", "", raw)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM returned invalid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("LLM returned unexpected JSON shape")
        for key in ("skills", "work_history", "education", "projects", "target_roles"):
            if not isinstance(parsed.get(key), list):
                parsed[key] = []
        defaults = {
            "projects": [], "target_salary_min": None, "target_salary_max": None,
            "target_roles": [], "resume_path": "", "md_path": "",
        }
        return {**defaults, **parsed}

    @classmethod
    def from_pdf(cls, pdf_bytes: bytes, db: Session) -> dict:
        """Convert raw PDF bytes into a structured profile dict via LLM.

        Does not persist — caller decides what to do with the result.

        Args:
            pdf_bytes: Raw bytes of a PDF resume.
            db: SQLAlchemy session (used to resolve the active LLM provider).

        Returns:
            Dict conforming to the profile schema.

        Raises:
            ValueError: If the PDF cannot be parsed or the LLM returns invalid JSON.
        """
        import io
        import pdfplumber

        if not pdf_bytes:
            raise ValueError("Empty PDF bytes")
        lines: list[str] = []
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page in pdf.pages:
                    text = page.extract_text() or ""
                    for line in text.splitlines():
                        stripped = line.strip()
                        if not stripped:
                            lines.append("")
                            continue
                        if stripped.isupper() and 2 <= len(stripped.split()) < 8:
                            lines.append(f"## {stripped.title()}")
                        elif stripped.startswith(("•", "·", "-", "*")):
                            lines.append(f"- {stripped.lstrip('•·-* ')}")
                        else:
                            lines.append(stripped)
        except Exception as exc:
            raise ValueError(f"Could not parse PDF: {exc}") from exc
        md_text = "\n".join(lines)
        return cls.from_markdown(md_text, db)

    def save(self, db: Session) -> None:
        """Persist the current state of this user to the database.

        Serializes all profile attributes back to the JSON data column and commits.

        Args:
            db: SQLAlchemy session.
        """
        self.data = json.dumps(self._to_dict())
        db.add(self)
        db.commit()

    def full_name(self) -> str:
        """Return the user's display name.

        Returns the name column if set, otherwise constructs from first_name + last_name.

        Returns:
            Full name string.
        """
        if self.name and self.name.strip():
            return self.name.strip()
        return f"{self.first_name} {self.last_name}".strip()

    def render_for_prompt(self) -> str:
        """Format the user profile as a human-readable string for LLM prompt injection.

        Returns:
            Multi-line string with work history, education, and skills sections.
        """
        work = "\n".join(
            f"- {e.title} at {e.company} ({e.start}–{e.end}): {e.summary}"
            for e in self.work_history
        )
        education = "\n".join(
            f"- {e.degree} in {e.field} from {e.institution} ({e.graduated}), GPA {e.gpa}"
            for e in self.education
        )
        projects = "\n".join(
            f"- {e.name}: {e.description}"
            + (f" ({e.url})" if e.url else "")
            + (f" — {', '.join(e.technologies)}" if e.technologies else "")
            for e in self.projects
        )
        salary_str = (
            f"${self.target_salary_min}–${self.target_salary_max}"
            if self.target_salary_min is not None else "Not specified"
        )
        result = (
            f"Name: {self.full_name()}\n"
            f"Target roles: {', '.join(self.target_roles)}\n"
            f"Target salary: {salary_str}\n"
            f"Skills: {', '.join(self.skills)}\n\n"
            f"Work History:\n{work}\n\n"
            f"Education:\n{education}"
        )
        if projects:
            result += f"\n\nProjects:\n{projects}"
        return result

    def master_resume(self) -> str:
        """Return the master resume markdown for prompt injection.

        Reads from md_path if the file exists, otherwise falls back to render_for_prompt().

        Returns:
            Markdown string of the user's resume content.
        """
        if self.md_path:
            p = Path(self.md_path)
            if p.exists():
                return p.read_text(encoding="utf-8")
        return self.render_for_prompt()

    def resolve_prompt(self, type_key: str) -> str:
        """Read and return the prompt file content for the given type.

        Args:
            type_key: One of the keys in _PROMPT_TYPES (e.g. "scoring", "resume").

        Returns:
            Prompt text content.

        Raises:
            PromptNotConfiguredError: If path is empty, file does not exist, or content is empty.
        """
        label = _PROMPT_LABELS.get(type_key, type_key)
        path_str = getattr(self, f"prompt_{type_key}", "")
        if not path_str:
            raise PromptNotConfiguredError(f"{label} not configured")
        p = Path(path_str)
        if not p.exists():
            raise PromptNotConfiguredError(f"{label} not configured")
        content = p.read_text(encoding="utf-8").strip()
        if not content:
            raise PromptNotConfiguredError(f"{label} not configured")
        return content
