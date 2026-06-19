from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import ClassVar, List, Optional

from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.orm import Session

from db.database import Base
import db.database as _db_core  # noqa: F401 — ensures Config/FieldHelp registered with Base.metadata
from core.profile_tree import (
    legacy_to_tree,
    tree_to_legacy,
    validate_tree,
    RootNode,
    with_rebuilt_tree,
)

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_PROMPTS_DEFAULTS_DIR = _PROMPTS_DIR / "defaults"

_PROMPT_LABELS: dict[str, str] = {
    "scoring": "Scoring",
    "resume": "Resume Generation",
    "cover": "Cover Letter Generation",
    "extraction": "Description Processing",
    "resume_parse": "Resume Parsing",
    "resume_eval": "Resume Evaluator",
    "resume_refine": "Resume Rewriter",
    "cover_eval": "Cover Letter Evaluator",
    "cover_refine": "Cover Letter Rewriter",
}


class PromptNotConfiguredError(Exception):
    """Raised when a required prompt is not configured for the active profile."""


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

        tree_raw = raw.get("profile_tree")
        migrated_tree = False
        if tree_raw:
            self.profile_tree = RootNode.model_validate(tree_raw)
        else:
            self.profile_tree = legacy_to_tree(raw)
            migrated_tree = True
        validate_tree(self.profile_tree)
        derived = tree_to_legacy(self.profile_tree)
        raw = {**raw, **derived}  # tree is source of truth for document sections

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

        # Initialize model attrs for all 9 prompt types (populated from DB rows in load()).
        from db.seed import PROMPT_TYPE_KEYS  # deferred: db.seed imports core.user

        for type_key in PROMPT_TYPE_KEYS:
            setattr(self, f"prompt_{type_key}_model", "")
        # Refinement config — resume
        self.resume_refine_enabled = bool(raw.get("resume_refine_enabled", True))
        self.resume_refine_max_turns = int(raw.get("resume_refine_max_turns", 3))
        self.resume_refine_pass_score = float(raw.get("resume_refine_pass_score", 0.80))
        # Refinement config — cover
        self.cover_refine_enabled = bool(raw.get("cover_refine_enabled", True))
        self.cover_refine_max_turns = int(raw.get("cover_refine_max_turns", 3))
        self.cover_refine_pass_score = float(raw.get("cover_refine_pass_score", 0.80))
        return migrated_tree

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
        }
        d["resume_refine_enabled"] = self.resume_refine_enabled
        d["resume_refine_max_turns"] = self.resume_refine_max_turns
        d["resume_refine_pass_score"] = self.resume_refine_pass_score
        d["cover_refine_enabled"] = self.cover_refine_enabled
        d["cover_refine_max_turns"] = self.cover_refine_max_turns
        d["cover_refine_pass_score"] = self.cover_refine_pass_score
        d = with_rebuilt_tree(d)
        return d

    @classmethod
    def load(cls, db: Session, profile_id: Optional[int] = None) -> "User":
        """Load a user profile by id.

        With no profile_id, returns the first row (legacy/seed usage). When
        profile_id is given it is authoritative: a missing id raises rather
        than silently falling back to another tenant's row.

        Args:
            db: SQLAlchemy session.
            profile_id: Optional explicit profile ID, resolved by the tenancy seam.

        Returns:
            Hydrated User instance.

        Raises:
            RuntimeError: If the requested (or any) profile does not exist.
        """
        if profile_id is not None:
            row = db.query(cls).filter_by(id=profile_id).first()
            if row is None:
                raise RuntimeError(f"No user profile with id={profile_id}.")
        else:
            row = db.query(cls).first()
            if row is None:
                raise RuntimeError("No user profile found. Add one via /config.")

        migrated = (
            row._hydrate()
        )  # always False post prompts-to-DB; branch kept for future migration hooks
        from db.database import Prompt

        for r in db.query(Prompt).filter_by(profile_id=row.id).all():
            setattr(row, f"prompt_{r.type_key}_model", r.model or "")
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
        data = with_rebuilt_tree(data)
        name = (
            data.get("name", "")
            or f"{data.get('first_name', '')} {data.get('last_name', '')}".strip()
            or "Default"
        )
        row = db.query(cls).first()
        if row:
            row.name = name
            row.data = json.dumps(data)
        else:
            db.add(cls(name=name, data=json.dumps(data)))
        db.commit()

    @classmethod
    def from_markdown(
        cls, md_text: str, db: Session, profile_id: Optional[int] = None
    ) -> dict:
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
        from core.llm import get_client_for_profile
        from core.job import _apply_template

        active_user = cls.load(db, profile_id=profile_id)
        try:
            prompt_text = active_user.resolve_prompt("resume_parse")
            system_prompt = _apply_template(prompt_text, {"user": active_user})
        except PromptNotConfiguredError:
            raise
        try:
            client, model = get_client_for_profile(
                active_user, active_user.prompt_resume_parse_model
            )
        except RuntimeError:
            raise
        response = client.chat.completions.create(
            model=model,
            temperature=0,
            timeout=30,
            max_tokens=8000,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": md_text},
            ],
        )
        from core.schemas import ParseResponse, parse_llm_json

        raw = response.choices[0].message.content or ""
        try:
            parsed = parse_llm_json(raw, ParseResponse).model_dump()
        except RuntimeError as exc:
            raise ValueError(str(exc)) from exc
        defaults = {"resume_path": "", "md_path": ""}
        return {**defaults, **parsed}

    @classmethod
    def from_pdf(
        cls, pdf_bytes: bytes, db: Session, profile_id: Optional[int] = None
    ) -> dict:
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
        return cls.from_markdown(md_text, db, profile_id=profile_id)

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

    @property
    def education_degrees(self) -> str:
        """Formatted degree list for hallucination-detection context in eval prompts."""
        if not self.education:
            return "none listed"
        return ", ".join(f"{e.degree} {e.field}" for e in self.education)

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
            if self.target_salary_min is not None
            else "Not specified"
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

    def render_work_history_indexed(self) -> str:
        """Render work history with stable integer indices for prompt `ref` keying.

        Index N corresponds to ``self.work_history[N]`` so the LLM's returned
        ``ref`` values join back to the correct entry.
        """
        return "\n".join(
            f"[{i}] {e.title} at {e.company} ({e.start}–{e.end}): {e.summary}"
            for i, e in enumerate(self.work_history)
        )

    def render_projects_indexed(self) -> str:
        """Render projects with stable integer indices for prompt `ref` keying.

        Index N corresponds to ``self.projects[N]``.
        """
        return "\n".join(
            f"[{i}] {e.name}: {e.description}"
            + (f" ({e.url})" if e.url else "")
            + (f" — {', '.join(e.technologies)}" if e.technologies else "")
            for i, e in enumerate(self.projects)
        )

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

    # Minimum words a configured prompt must contain to be considered usable.
    # A path that is missing or whose content falls at/below this is treated as
    # invalid and auto-reset to the shipped default before the run proceeds.
    _MIN_PROMPT_WORDS: ClassVar[int] = 10

    def resolve_prompt(self, type_key: str) -> str:
        """Return the active prompt content for the given type from the DB.

        Reads the prompts row for this profile. If the row is missing or its
        content is <= _MIN_PROMPT_WORDS words, repairs it from prompt_defaults
        (persisted), alerts the user via SSE, and returns the default content.

        Raises:
            PromptNotConfiguredError: If no usable default exists.
        """
        from sqlalchemy.orm import object_session
        from db.database import Prompt, PromptDefault

        label = _PROMPT_LABELS.get(type_key, type_key)
        sess = object_session(self)
        if sess is None:
            raise PromptNotConfiguredError(f"{label} not configured")

        row = (
            sess.query(Prompt).filter_by(profile_id=self.id, type_key=type_key).first()
        )
        invalid_reason: Optional[str] = None
        if row is None or not row.content:
            invalid_reason = "the prompt is unset"
        elif len(row.content.split()) <= self._MIN_PROMPT_WORDS:
            invalid_reason = (
                f"the prompt is too short (must exceed {self._MIN_PROMPT_WORDS} words)"
            )

        if invalid_reason is None:
            return row.content

        default = sess.query(PromptDefault).filter_by(type_key=type_key).first()
        if default is None or not default.content.strip():
            raise PromptNotConfiguredError(f"{label} not configured")

        self._reset_prompt_to_default(type_key, default.content, label, invalid_reason)
        return default.content

    def _reset_prompt_to_default(
        self, type_key: str, default_content: str, label: str, reason: str
    ) -> None:
        """Repair the profile's prompts row from the default, persist, alert via SSE."""
        from datetime import datetime, timezone
        from sqlalchemy.orm import object_session
        from db.database import Prompt

        sess = object_session(self)
        if sess is not None:
            row = (
                sess.query(Prompt)
                .filter_by(profile_id=self.id, type_key=type_key)
                .first()
            )
            now = datetime.now(timezone.utc).isoformat()
            try:
                with sess.begin_nested():
                    if row is None:
                        sess.add(
                            Prompt(
                                profile_id=self.id,
                                type_key=type_key,
                                content=default_content,
                                model="",
                                updated_at=now,
                            )
                        )
                    else:
                        row.content = default_content
                        row.updated_at = now
            except Exception:
                pass  # repair is best-effort; outer transaction is untouched
        try:
            from web.sse import send

            send(
                "prompt_reset",
                {
                    "type_key": type_key,
                    "label": label,
                    "reason": reason,
                    "message": f"{label} prompt was reset to default because {reason}.",
                },
            )
        except Exception:
            pass
