from __future__ import annotations

import json
import re
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
    """Replace {table.field} placeholders using attribute values from sources dict.

    Unknown tables or missing attributes are left as-is. None field values render as "".
    """
    import re
    def _replace(m: "re.Match[str]") -> str:
        table, field = m.group(1), m.group(2)
        obj = sources.get(table)
        if obj is None:
            return m.group(0)
        if not hasattr(obj, field):
            return m.group(0)
        return _field_to_str(getattr(obj, field))
    return re.sub(r'\{(\w+)\.(\w+)\}', _replace, template)


def _strip_yaml_frontmatter(text: str) -> tuple[str, str]:
    """Split a markdown file with YAML front matter into (frontmatter, body).

    Returns ("", text) if no front matter is found.
    """
    if not text.startswith("---") or (len(text) > 3 and text[3] not in ("\n", "\r")):
        return ("", text)
    end = text.find("\n---", 3)
    if end == -1:
        return ("", text)
    fm_end = end + 4  # past \n---
    if fm_end < len(text) and text[fm_end] == "\n":
        fm_end += 1
    return (text[:fm_end], text[fm_end:])


class JobState(str, Enum):
    """Valid states for a job in the pipeline."""

    NEW = "new"
    PENDING_REVIEW = "pending_review"
    READY = "ready"
    APPLIED = "applied"
    CONTACT = "contact"
    REJECTED = "rejected"
    DELETED = "deleted"


class Job(Base):
    """A job posting with all associated pipeline data and behavior.

    Columns cover scraped data, scores, description extraction, and artifact paths.
    All operations that read or write job columns are methods on this class.
    """

    __tablename__ = "jobs"
    __allow_unmapped__ = True

    def __new__(cls, *args: Any, **kwargs: Any) -> "Job":
        """Ensure SQLAlchemy instance state is initialized when using __new__ directly.

        SQLAlchemy normally sets up _sa_instance_state in __init__. When tests
        (or other code) call Job.__new__(Job) without __init__, attribute access
        fails. This override bootstraps ORM state without calling __init__ (which
        would cause a double-init on every normal Job() construction).
        """
        instance = object.__new__(cls)
        if not hasattr(instance, "_sa_instance_state"):
            from sqlalchemy.orm import instrumentation
            instrumentation.manager_of_class(cls).setup_instance(instance)
        return instance

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
    state = Column(String, nullable=False, default="new")

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
    ext_salary_min = Column(Float)
    ext_salary_max = Column(Float)

    # ── Artifacts ──────────────────────────────────────────────────────────────
    resume_path = Column(String)
    cover_path = Column(String)
    resume_generated_at = Column(String)
    cover_generated_at = Column(String)
    applied_at = Column(String)
    sheets_row_id = Column(String)
    unread_indicator = Column(String)   # null | "ok" | "error"
    last_result_error = Column(Text)
    pending_review_actions = Column(Text)  # JSON list of action names awaiting review
    flagged = Column(Boolean, default=False, nullable=False)

    # ── Refinement — evaluation tracking ────────────────────────────────────────
    resume_eval_score = Column(Float)
    resume_eval_turns = Column(Integer)
    resume_eval_log = Column(Text)  # JSON list of evaluation turns
    cover_eval_score = Column(Float)
    cover_eval_turns = Column(Integer)
    cover_eval_log = Column(Text)  # JSON list of evaluation turns

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
            state=JobState.NEW.value,
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
    def save_batch_returning(cls, scraped_jobs: list[Any], db: Session) -> list["Job"]:
        """Persist new (non-duplicate) jobs and return the inserted Job objects.

        Args:
            scraped_jobs: List of ScrapedJob instances from a scraper source.
            db: SQLAlchemy session.

        Returns:
            List of newly inserted Job instances.
        """
        if not scraped_jobs:
            return []
        urls = {s.url for s in scraped_jobs}
        existing_urls = {
            row[0]
            for row in db.query(cls.url).filter(cls.url.in_(urls)).all()
        }
        new_jobs: list["Job"] = []
        for scraped in scraped_jobs:
            if scraped.url in existing_urls:
                continue
            job = cls.from_scraped(scraped)
            db.add(job)
            new_jobs.append(job)
        db.commit()
        for job in new_jobs:
            db.refresh(job)
        return new_jobs

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
    def all_inbox(cls, db: Session) -> list["Job"]:
        """Return all jobs awaiting review (new or pending_review) ordered by final_score descending.

        Args:
            db: SQLAlchemy session.

        Returns:
            List of Job instances in NEW or PENDING_REVIEW state.
        """
        return (
            db.query(cls)
            .filter(cls.state.in_([JobState.NEW.value, JobState.PENDING_REVIEW.value]))
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

    def build_score_prompt(self, user: Any, template: str) -> str:
        """Render the scoring prompt template against this job and user.

        Args:
            user: A User instance with profile data.
            template: Prompt template string with {job.*} and {user.*} placeholders.

        Returns:
            Rendered prompt string ready to send to the LLM.
        """
        return _apply_template(template, {"job": self, "user": user})

    def score(
        self,
        user: Any,
        config: dict,
        client: Any,
        model: str,
        db: Session,
        prompt_content: str,
    ) -> None:
        """Score this job using the LLM. Populates score fields and commits.

        Warns and returns early (without raising) on LLM API error or unparseable response.

        Args:
            user: A User instance with profile data.
            config: Dict with keys w1, w2 (scoring weights).
            client: An OpenAI-compatible client instance.
            model: Model identifier string.
            db: SQLAlchemy session.
            prompt_content: Rendered scoring prompt template text.
        """
        import warnings

        prompt = self.build_score_prompt(user, prompt_content)
        try:
            response = client.chat.completions.create(
                model=model,
                max_tokens=8192,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as e:
            raise RuntimeError(f"LLM API error: {e}") from e
        usage = getattr(response, "usage", None)
        if usage is not None:
            from core import session_cost
            session_cost.add_cost(float(getattr(usage, "cost", None) or 0.0))
        choice = response.choices[0]
        raw = choice.message.content
        finish = getattr(choice, "finish_reason", None)
        if finish and finish != "stop":
            raise RuntimeError(
                f"LLM stopped early (finish_reason={finish!r}); "
                f"consider raising max_tokens or shortening the prompt."
            )
        if not raw:
            raise RuntimeError("LLM returned empty content")

        required = {"desirability_score", "fit_score", "desirability_justification", "fit_justification"}
        cleaned = raw.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        first = cleaned.find("{")
        last = cleaned.rfind("}")
        if first != -1 and last > first:
            cleaned = cleaned[first : last + 1]
        try:
            parsed = json.loads(cleaned)
            if not required.issubset(parsed.keys()):
                raise ValueError(f"Missing required keys; got {sorted(parsed.keys())}")
        except (json.JSONDecodeError, ValueError, AttributeError) as e:
            preview = (raw or "")[:300].replace("\n", " ")
            raise RuntimeError(f"Unparseable LLM response: {e}. Preview: {preview!r}") from e

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

    # ── Refinement — evaluation ────────────────────────────────────────────────

    def _evaluate_doc_md(
        self,
        doc_type: str,
        eval_prompt: str,
        user: Any,
        client: Any,
        model: str,
    ) -> dict:
        """Evaluate a generated document (resume or cover letter) for quality.

        Args:
            doc_type: "resume" or "cover".
            eval_prompt: Rendered evaluation prompt template.
            user: Hydrated User instance.
            client: OpenAI-compatible client.
            model: Model identifier string.

        Returns:
            {"score": float, "issues": list[dict]}

        Raises:
            FileNotFoundError: If the document markdown file does not exist.
            RuntimeError: If the LLM returns unparseable or malformed JSON.
        """
        from core.llm import call_llm

        md_path = _OUTPUTS_DIR / f"{self.job_key}_{doc_type}.md"
        if not md_path.exists():
            raise FileNotFoundError(
                f"{doc_type.capitalize()} markdown not found: {md_path}"
            )

        _, body = _strip_yaml_frontmatter(md_path.read_text(encoding="utf-8"))

        # An empty document body (e.g. a generation that hit the token limit and
        # produced only frontmatter) must never be scored by the LLM — it
        # hallucinates a passing grade. Short-circuit to a hard failure.
        if not body.strip():
            return {
                "score": 0.0,
                "issues": [{
                    "category": "personalization",
                    "description": "Document body is empty — nothing to evaluate.",
                }],
            }

        prompt = eval_prompt.replace("{current_document}", body)
        prompt = _apply_template(prompt, {"job": self, "user": user})

        raw = call_llm(prompt, client, model, max_tokens=8192)

        cleaned = raw.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        first = cleaned.find("{")
        last = cleaned.rfind("}")
        if first != -1 and last > first:
            cleaned = cleaned[first : last + 1]

        try:
            parsed = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError) as exc:
            preview = (raw or "")[:200].replace("\n", " ")
            raise RuntimeError(
                f"Eval LLM returned invalid JSON: {exc}. Preview: {preview!r}"
            ) from exc

        if "score" not in parsed or "issues" not in parsed:
            raise RuntimeError(
                f"Eval response missing required keys; got {sorted(parsed.keys())}"
            )

        score = max(0.0, min(1.0, float(parsed["score"])))
        issues = parsed.get("issues", [])
        if not isinstance(issues, list):
            issues = []

        return {"score": score, "issues": issues}

    def evaluate_resume_md(
        self,
        eval_prompt: str,
        user: Any,
        client: Any,
        model: str,
    ) -> dict:
        """Evaluate the generated resume markdown. Returns {"score", "issues"}."""
        return self._evaluate_doc_md("resume", eval_prompt, user, client, model)

    def evaluate_cover_md(
        self,
        eval_prompt: str,
        user: Any,
        client: Any,
        model: str,
    ) -> dict:
        """Evaluate the generated cover letter markdown. Returns {"score", "issues"}."""
        return self._evaluate_doc_md("cover", eval_prompt, user, client, model)

    # ── Refinement — rewriting ─────────────────────────────────────────────────

    def _refine_doc_md(
        self,
        doc_type: str,
        user: Any,
        refine_prompt: str,
        client: Any,
        model: str,
        issues: list,
    ) -> None:
        """Rewrite a generated document to address evaluation issues.

        Overwrites the existing markdown file in generator/outputs/ in place.
        Preserves the YAML front matter block from the original file.
        Caller is responsible for calling generate_resume_pdf / generate_cover_pdf
        and committing eval fields to the DB.

        Args:
            doc_type: "resume" or "cover".
            user: Hydrated User instance.
            refine_prompt: Rewriter prompt template.
            client: OpenAI-compatible client.
            model: Model identifier string.
            issues: List of issue dicts from the evaluator.

        Raises:
            FileNotFoundError: If the document markdown file does not exist.
        """
        from core.llm import call_llm
        from core.utils import strip_header_block

        md_path = _OUTPUTS_DIR / f"{self.job_key}_{doc_type}.md"
        if not md_path.exists():
            raise FileNotFoundError(
                f"{doc_type.capitalize()} markdown not found: {md_path}"
            )

        frontmatter, body = _strip_yaml_frontmatter(
            md_path.read_text(encoding="utf-8")
        )

        critique = json.dumps(issues)
        prompt = refine_prompt.replace("{current_document}", body)
        prompt = prompt.replace("{critique}", critique)
        prompt = _apply_template(prompt, {"job": self, "user": user})

        content = call_llm(prompt, client, model, max_tokens=32768)
        if not content:
            raise RuntimeError(
                f"{doc_type.capitalize()} rewrite returned empty content — "
                "input may be too long for the model's context window"
            )
        content = strip_header_block(content)
        md_path.write_text(frontmatter + content, encoding="utf-8")

    def refine_resume_md(
        self,
        user: Any,
        refine_prompt: str,
        client: Any,
        model: str,
        db: Any,
        issues: list,
        template_path: Any,
    ) -> None:
        """Rewrite resume markdown and regenerate the PDF.

        Args:
            user: Hydrated User instance.
            refine_prompt: Rewriter prompt template.
            client: OpenAI-compatible client.
            model: Model identifier string.
            db: SQLAlchemy session (passed to generate_resume_pdf).
            issues: List of issue dicts from evaluate_resume_md.
            template_path: Path to the HTML resume template for PDF rendering.
        """
        self._refine_doc_md("resume", user, refine_prompt, client, model, issues)
        self.generate_resume_pdf(template_path, db, max_pages=1)

    def refine_cover_md(
        self,
        user: Any,
        refine_prompt: str,
        client: Any,
        model: str,
        db: Any,
        issues: list,
        template_path: Any,
    ) -> None:
        """Rewrite cover letter markdown and regenerate the PDF.

        Args:
            user: Hydrated User instance.
            refine_prompt: Rewriter prompt template.
            client: OpenAI-compatible client.
            model: Model identifier string.
            db: SQLAlchemy session (passed to generate_cover_pdf).
            issues: List of issue dicts from evaluate_cover_md.
            template_path: Path to the HTML cover letter template for PDF rendering.
        """
        self._refine_doc_md("cover", user, refine_prompt, client, model, issues)
        self.generate_cover_pdf(template_path, db)

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

        Uses the active profile's extraction prompt and LLM config.

        Args:
            db: SQLAlchemy session.

        Raises:
            FileNotFoundError: If description prompt is not configured.
            PromptNotConfiguredError: If extraction prompt is not configured.
            RuntimeError: If the LLM fails or returns invalid JSON.
        """
        import re
        from core.user import User, PromptNotConfiguredError
        from core.llm import get_client_for_profile

        # Idempotent: skip jobs already extracted to avoid redundant LLM cost.
        if self.ext_seniority:
            return

        user = User.load(db)
        prompt_content = user.resolve_prompt("extraction")
        client, model = get_client_for_profile(user, user.prompt_extraction_model)

        actual_prompt = self.build_description_prompt(prompt_content)
        response = client.chat.completions.create(
            model=model,
            max_tokens=2048,
            messages=[{"role": "user", "content": actual_prompt}],
        )
        usage = getattr(response, "usage", None)
        if usage is not None:
            from core import session_cost
            session_cost.add_cost(float(getattr(usage, "cost", None) or 0.0))
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
        salary_min = data.get("salary_min")
        salary_max = data.get("salary_max")
        self.ext_salary_min = float(salary_min) if salary_min is not None else None
        self.ext_salary_max = float(salary_max) if salary_max is not None else None
        db.flush()
        db.commit()

    def intake(self) -> None:
        """Run post-intake processing (description extraction) in a background thread.

        Opens a fresh DB session so the thread is session-safe. Logs start,
        completion, and any failure to stdout.
        """
        import threading
        from db.database import SessionLocal

        job_key = self.job_key

        def _run() -> None:
            from web import llm_status
            from web.sse import send as _sse_send

            thread_db = SessionLocal()
            llm_status.start(job_key)
            try:
                print(f"[intake] {job_key}: extraction started", flush=True)
                thread_job = thread_db.query(Job).filter_by(job_key=job_key).first()
                if thread_job is None:
                    print(f"[intake] {job_key}: job not found in thread session", flush=True)
                    return
                try:
                    thread_job.extract_description(thread_db)
                    thread_job.unread_indicator = "ok"
                    thread_job.last_result_error = None
                    thread_db.commit()
                    _sse_send("job", thread_job.serialize())
                    print(f"[intake] {job_key}: extraction complete", flush=True)
                except Exception as exc:
                    thread_job.unread_indicator = "error"
                    thread_job.last_result_error = str(exc)
                    thread_db.commit()
                    _sse_send("job", thread_job.serialize())
                    print(f"[intake] {job_key}: extraction failed — {exc}", flush=True)
            finally:
                llm_status.finish(job_key)
                thread_db.close()

        t = threading.Thread(target=_run, daemon=True)
        t.start()

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
        return _apply_template(template, {"job": self, "user": user, "user_profile": user})

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
        content = call_llm(prompt, client, model, max_tokens=16384)
        if not content.strip():
            raise RuntimeError(
                "Resume generation returned empty content — the model likely hit its "
                "token limit before producing output (common with reasoning models). "
                "Try a non-reasoning model or a shorter prompt."
            )
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
        content = call_llm(prompt, client, model, max_tokens=16384)
        if not content.strip():
            raise RuntimeError(
                "Cover letter generation returned empty content — the model likely hit "
                "its token limit before producing output (common with reasoning models). "
                "Try a non-reasoning model or a shorter prompt."
            )
        md_path = _OUTPUTS_DIR / f"{self.job_key}_cover.md"
        md_path.write_text(frontmatter + content, encoding="utf-8")

    def generate_resume_pdf(self, template_path: Path, db: Session, max_pages: int | None = 1) -> None:
        """Render resume PDF from existing markdown and update resume_path.

        Requires generator/outputs/{job_key}_resume.md to exist.

        Args:
            template_path: Path to the Jinja2 HTML template file.
            db: SQLAlchemy session.
            max_pages: Maximum number of pages allowed. ``None`` disables the limit.
                Defaults to 1 (enforced for LLM-generated resumes; pass ``None``
                when saving user edits to allow multi-page documents).

        Raises:
            FileNotFoundError: If the resume markdown file does not exist.
            RuntimeError: If `max_pages` is set and the rendered resume exceeds that limit.
        """
        from core.utils import render_pdf
        from core.user import User

        md_path = _OUTPUTS_DIR / f"{self.job_key}_resume.md"
        if not md_path.exists():
            raise FileNotFoundError(f"Resume markdown not found: {md_path}")
        pdf_path = _OUTPUTS_DIR / f"{self.job_key}_resume.pdf"
        meta = self._frontmatter_data(User.load(db), db)
        render_pdf(md_path, pdf_path, template_path, max_pages=max_pages, meta=meta)
        self.resume_path = str(pdf_path)
        self.resume_generated_at = datetime.now(timezone.utc).isoformat()
        db.commit()

    def generate_cover_pdf(self, template_path: Path, db: Session) -> None:
        """Render cover letter PDF from existing markdown and update cover_path.

        Requires generator/outputs/{job_key}_cover.md to exist.

        Args:
            template_path: Path to the Jinja2 HTML template file.
            db: SQLAlchemy session.

        Raises:
            FileNotFoundError: If the cover letter markdown file does not exist.
        """
        from core.utils import render_pdf
        from core.user import User

        md_path = _OUTPUTS_DIR / f"{self.job_key}_cover.md"
        if not md_path.exists():
            raise FileNotFoundError(f"Cover markdown not found: {md_path}")
        pdf_path = _OUTPUTS_DIR / f"{self.job_key}_cover.pdf"
        meta = self._frontmatter_data(User.load(db), db)
        render_pdf(md_path, pdf_path, template_path, meta=meta)
        self.cover_path = str(pdf_path)
        self.cover_generated_at = datetime.now(timezone.utc).isoformat()
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

    def _frontmatter_data(self, user: Any, db: Session) -> dict:
        """Build the frontmatter dict for resume/cover letter templates."""
        import dataclasses
        from db.database import Config

        def _cfg(key: str) -> str:
            row = db.query(Config).filter_by(key=key).first()
            return row.value if row else ""

        first = user.first_name or ""
        last = user.last_name or ""
        data: dict = {
            "name": f"{first} {last}".strip() or user.full_name(),
            "firstname": first,
            "lastname": last,
            "email": user.email or "",
            "phone": user.phone or "",
            "location": user.location or "",
        }
        github = _cfg("resume_github")
        linkedin = _cfg("resume_linkedin")
        website = _cfg("resume_website")
        if github:
            data["github"] = github
        if linkedin:
            data["linkedin"] = linkedin
        if website:
            data["website"] = website
        if getattr(user, "education", None):
            data["education"] = [dataclasses.asdict(e) for e in user.education]
        if self.company:
            data["company"] = self.company
        return data

    def _build_frontmatter(self, user: Any, db: Session) -> str:
        """Serialize frontmatter data to a YAML front matter string."""
        import yaml
        return "---\n" + yaml.dump(
            self._frontmatter_data(user, db),
            allow_unicode=True,
            default_flow_style=False,
        ) + "---\n\n"

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
            "applied_at": self.applied_at or "",
            "ext_salary_min": self.ext_salary_min,
            "ext_salary_max": self.ext_salary_max,
            "resume_path": self.resume_path,
            "cover_path": self.cover_path,
            "resume_generated_at": self.resume_generated_at or "",
            "cover_generated_at": self.cover_generated_at or "",
            "resume_md_exists": (_OUTPUTS_DIR / f"{self.job_key}_resume.md").exists(),
            "cover_md_exists": (_OUTPUTS_DIR / f"{self.job_key}_cover.md").exists(),
            "extraction_json_exists": (has_extraction := bool(self.ext_required_skills or self.ext_seniority)),
            "extraction": {
                "seniority": self.ext_seniority,
                "role_type": self.ext_role_type,
                "domain": self.ext_domain,
                "work_arrangement": self.ext_work_arrangement,
                "employment_type": self.ext_employment_type,
                "required_skills": [s.strip() for s in (self.ext_required_skills or "").split(",") if s.strip()],
                "preferred_skills": [s.strip() for s in (self.ext_preferred_skills or "").split(",") if s.strip()],
                "tech_stack": [s.strip() for s in (self.ext_tech_stack or "").split(",") if s.strip()],
                "key_responsibilities": [s.strip() for s in (self.ext_key_responsibilities or "").split(",") if s.strip()],
                "company_signals": [s.strip() for s in (self.ext_company_signals or "").split(",") if s.strip()],
            } if has_extraction else None,
            "scraped_at": self.scraped_at or "",
            "unread_indicator": self.unread_indicator,
            "last_result_error": self.last_result_error,
            "pending_review_actions": json.loads(self.pending_review_actions or "[]"),
            "flagged": bool(self.flagged),
            "resume_eval_score": self.resume_eval_score,
            "resume_eval_turns": self.resume_eval_turns,
            "resume_eval_log": (
                json.loads(self.resume_eval_log)
                if isinstance(self.resume_eval_log, str) and self.resume_eval_log
                else []
            ),
            "cover_eval_score": self.cover_eval_score,
            "cover_eval_turns": self.cover_eval_turns,
            "cover_eval_log": (
                json.loads(self.cover_eval_log)
                if isinstance(self.cover_eval_log, str) and self.cover_eval_log
                else []
            ),
        }
