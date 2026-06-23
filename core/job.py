from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import Boolean, Column, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Session

from db.database import Base, Document
from core.schemas import (
    CoverDocument,
    EvalResponse,
    ExtractionResponse,
    ResumeDocument,
    ResumeGeneration,
    ScoreResponse,
    parse_llm_json,
)
from core.llm import call_llm
from core.document_builder import build_resume_document, build_cover_document
from core.document_assembler import assemble_resume_markdown, assemble_cover_markdown
from core.tree_assembler import assemble_resume_tree_markdown
from core.resume_document_io import is_tree_v1, deserialize_document_tree, serialize_document_tree
from core.profile_tree import RootNode, resolve_profile_tokens
from core.section_generator import generate_resume_by_section
from core.document_tree import build_resume_document_tree
from core.utils import render_pdf
from core.paths import OUTPUTS_DIR as _OUTPUTS_DIR

# Appended to every structured (JSON) LLM call. Small/fast models (e.g. DeepSeek
# Flash, Haiku) sometimes break a markdown `description` out of its JSON string,
# producing invalid JSON ("Expecting value" at the value position). This makes
# the contract explicit; the retry below recovers the residual nondeterministic
# failures.
_JSON_RETRY_SUFFIX = (
    "\n\nReturn ONLY a single valid JSON object. Output compact JSON. Every "
    "newline inside a string value MUST be escaped as \\n — never break a string "
    "across physical lines. Do not emit markdown, code fences, comments, or any "
    "text outside the JSON object."
)


def _llm_json_with_retry(
    prompt: str,
    client: Any,
    model: str,
    model_cls: type,
    *,
    max_tokens: int,
    empty_msg: str,
    retries: int = 1,
):
    """Call the LLM for a structured JSON response, retrying once on parse failure.

    Appends a strict-JSON instruction to harden the contract, then parses the
    response against ``model_cls``. If parsing fails (the model emitted invalid
    JSON), retries with an added corrective note up to ``retries`` times before
    re-raising the last error.

    Args:
        prompt: The fully-substituted prompt (before the JSON hardening suffix).
        client: An OpenAI-compatible client instance.
        model: Model identifier string.
        model_cls: The Pydantic model to validate the JSON against.
        max_tokens: Maximum tokens in the response.
        empty_msg: Error message to raise if the LLM returns empty content.
        retries: Number of retries after the initial attempt (default 1).

    Returns:
        A validated instance of ``model_cls``.

    Raises:
        RuntimeError: If the response is empty, or still unparseable after retries.
    """
    sent = prompt + _JSON_RETRY_SUFFIX
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        raw = call_llm(sent, client, model, max_tokens=max_tokens)
        if not (raw or "").strip():
            raise RuntimeError(empty_msg)
        try:
            return parse_llm_json(raw, model_cls)
        except RuntimeError as exc:
            last_exc = exc
            sent = (
                prompt
                + _JSON_RETRY_SUFFIX
                + "\n\nYour previous reply was NOT valid JSON and failed to parse. "
                "Return ONLY a single valid, compact JSON object this time."
            )
    raise last_exc  # type: ignore[misc]


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
    __table_args__ = (
        UniqueConstraint("profile_id", "job_key", name="uq_jobs_profile_job_key"),
        UniqueConstraint("profile_id", "url", name="uq_jobs_profile_url"),
    )

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
    profile_id = Column(Integer, nullable=False, index=True)
    job_key = Column(String, nullable=False)
    source = Column(String, nullable=False)
    title = Column(String)
    company = Column(String)
    location = Column(String)
    salary = Column(String)
    remote = Column(Boolean)
    description = Column(Text)
    url = Column(String, nullable=False)
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
    resume_docx_path = Column(String)
    cover_generated_at = Column(String)
    # ── ATS gate — last report for the current résumé render ────────────────────
    ats_passed = Column(Boolean)        # null = never checked
    ats_score = Column(Float)
    ats_report_json = Column(Text)      # full AtsReport JSON for UI display
    ats_checked_at = Column(String)     # ISO timestamp of the check
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
    def from_scraped_for(cls, scraped: Any, profile_id: int) -> "Job":
        """Like from_scraped but stamps the owning tenant.

        Args:
            scraped: A ScrapedJob dataclass instance.
            profile_id: Owning tenant's profile id.

        Returns:
            Unsaved Job instance with profile_id set.
        """
        job = cls.from_scraped(scraped)
        job.profile_id = profile_id
        return job

    @classmethod
    def save_batch(cls, scraped_jobs: list[Any], db: Session, profile_id: int) -> int:
        """Persist a list of ScrapedJob objects, skipping URL duplicates.

        Args:
            scraped_jobs: List of ScrapedJob instances from a scraper source.
            db: SQLAlchemy session.
            profile_id: Owning tenant's profile id.

        Returns:
            Number of newly inserted jobs.
        """
        count = 0
        for scraped in scraped_jobs:
            if db.query(cls).filter_by(url=scraped.url, profile_id=profile_id).first():
                continue
            db.add(cls.from_scraped_for(scraped, profile_id))
            count += 1
        db.commit()
        return count

    @classmethod
    def save_batch_returning(cls, scraped_jobs: list[Any], db: Session, profile_id: int) -> list["Job"]:
        """Persist new (non-duplicate) jobs and return the inserted Job objects.

        Args:
            scraped_jobs: List of ScrapedJob instances from a scraper source.
            db: SQLAlchemy session.
            profile_id: Owning tenant's profile id.

        Returns:
            List of newly inserted Job instances.
        """
        if not scraped_jobs:
            return []
        urls = {s.url for s in scraped_jobs}
        existing_urls = {
            row[0]
            for row in db.query(cls.url).filter(cls.url.in_(urls), cls.profile_id == profile_id).all()
        }
        new_jobs: list["Job"] = []
        for scraped in scraped_jobs:
            if scraped.url in existing_urls:
                continue
            job = cls.from_scraped_for(scraped, profile_id)
            db.add(job)
            new_jobs.append(job)
        db.commit()
        for job in new_jobs:
            db.refresh(job)
        return new_jobs

    @classmethod
    def get(cls, job_key: str, db: Session, profile_id: int) -> Optional["Job"]:
        """Fetch a single job by job_key, scoped to a tenant.

        Args:
            job_key: Unique job identifier.
            db: SQLAlchemy session.
            profile_id: Owning tenant's profile id.

        Returns:
            Job instance, or None if not found.
        """
        return db.query(cls).filter_by(job_key=job_key, profile_id=profile_id).first()

    @classmethod
    def get_or_raise(cls, job_key: str, db: Session, profile_id: int) -> "Job":
        """Fetch a single job by job_key, raising if not found.

        Args:
            job_key: Unique job identifier.
            db: SQLAlchemy session.
            profile_id: Owning tenant's profile id.

        Returns:
            Job instance.

        Raises:
            ValueError: If no job with that key exists.
        """
        job = cls.get(job_key, db, profile_id)
        if job is None:
            raise ValueError(f"Job '{job_key}' not found")
        return job

    @classmethod
    def list_for_review(cls, db: Session, profile_id: int) -> list["Job"]:
        """Return all jobs awaiting review (new or pending_review) ordered by final_score descending.

        Args:
            db: SQLAlchemy session.
            profile_id: Owning tenant's profile id.

        Returns:
            List of Job instances in NEW or PENDING_REVIEW state.
        """
        return (
            db.query(cls)
            .filter(cls.state.in_([JobState.NEW.value, JobState.PENDING_REVIEW.value]))
            .filter(cls.profile_id == profile_id)
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

        parsed = parse_llm_json(raw, ScoreResponse)

        w1, w2 = config.get("w1", 0.5), config.get("w2", 0.5)
        final = max(0.0, min(1.0, w1 * parsed.desirability_score + w2 * parsed.fit_score))

        self.desirability_score = parsed.desirability_score
        self.fit_score = parsed.fit_score
        self.final_score = final
        self.score_justification = json.dumps({
            "desirability": parsed.desirability_justification.model_dump(),
            "fit": parsed.fit_justification.model_dump(),
        })
        db.commit()

    # ── Refinement — evaluation ────────────────────────────────────────────────

    def _regenerable_section_names(self, db: Session) -> list[str]:
        """Names of stored tree-v1 sections that have an unlocked llm_output field."""
        from core.section_generator import _outputable
        from core.profile_tree import GroupNode, ListNode, FieldNode
        row = Document.fetch(db, self.job_key, "resume", profile_id=self.profile_id)
        if row is None or not is_tree_v1(row.structured_json):
            return []
        root = deserialize_document_tree(row.structured_json)
        names: list[str] = []
        for s in root.children:
            if not s.visible or s.locked:
                continue
            child = s.children[0] if s.children else None
            groups = (child.children if isinstance(child, ListNode)
                      else [child] if isinstance(child, GroupNode) else [])
            has = any(
                _outputable(f) for g in groups for f in g.children
            ) if groups else (isinstance(child, FieldNode) and _outputable(child))
            if has:
                names.append(s.name)
        return names

    def evaluate_resume_sections(
        self, eval_prompt: str, user: Any, client: Any, model: str, db: Session,
    ) -> dict:
        """Per-section résumé evaluation. Returns {section_name: {score, issues}} for
        regenerable sections only (others are dropped)."""
        from core.schemas import SectionEvalResponse
        names = self._regenerable_section_names(db)
        if not names:
            return {}
        md_path = _OUTPUTS_DIR / f"{self.job_key}_resume.md"
        body = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
        prompt = eval_prompt.replace("{current_document}", body)
        prompt = prompt.replace("{sections_to_score}", "\n".join(names))
        prompt = _apply_template(prompt, {"job": self, "user": user})
        raw = call_llm(prompt, client, model, max_tokens=8192)
        parsed = parse_llm_json(raw, SectionEvalResponse)
        allowed = set(names)
        return {
            s.section: {"score": s.score, "issues": [i.model_dump() for i in s.issues]}
            for s in parsed.sections if s.section in allowed
        }

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
        md_path = _OUTPUTS_DIR / f"{self.job_key}_{doc_type}.md"
        if not md_path.exists():
            raise FileNotFoundError(
                f"{doc_type.capitalize()} markdown not found: {md_path}"
            )
        _, body = _strip_yaml_frontmatter(md_path.read_text(encoding="utf-8"))
        return self._evaluate_body(doc_type, body, eval_prompt, user, client, model)

    def _evaluate_body(
        self, doc_type: str, body: str, eval_prompt: str, user: Any, client: Any, model: str
    ) -> dict:
        """Evaluate a Markdown body string. Empty body → hard fail (never scored)."""
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
        parsed = parse_llm_json(raw, EvalResponse)
        return {
            "score": parsed.score,
            "issues": [i.model_dump() for i in parsed.issues],
        }

    def evaluate_resume_body(
        self, body: str, eval_prompt: str, user: Any, client: Any, model: str
    ) -> dict:
        """Public: evaluate an arbitrary résumé Markdown body (comparison harness)."""
        return self._evaluate_body("resume", body, eval_prompt, user, client, model)

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
        db: Any,
    ) -> None:
        """Refine a generated document by patching its structured form.

        Loads the stored Document (source of truth). For résumés the LLM returns
        a prose-only keyed patch (ResumeGeneration) applied to the document's
        prose leaves — structural facts and the header snapshot are never
        touched. For covers the LLM rewrites the body prose. The patched
        document is re-persisted and the `.md` re-assembled. Caller renders the
        PDF and commits eval fields.

        Raises:
            FileNotFoundError: If no stored Document exists for this job/doc_type.
            RuntimeError: If the LLM returns empty or unparseable content.
        """
        from core.document_builder import apply_resume_patch

        row = Document.fetch(db, self.job_key, doc_type, profile_id=self.profile_id)
        if row is None:
            raise FileNotFoundError(
                f"No structured {doc_type} document found for {self.job_key}"
            )

        critique = json.dumps(issues)
        prompt = refine_prompt.replace("{critique}", critique)

        if doc_type == "resume" and is_tree_v1(row.structured_json):
            # Interim tree-v1 refine: re-author all llm_output sections with the
            # critique in context, rebuild the document tree, re-persist + re-render.
            # (Per-section scoring / selective regen is 4B-2.)
            root = user.profile_tree_root()
            refine_with_ctx = refine_prompt.replace("{critique}", critique) + "\n\n{job.extracted_description}"
            job_ctx = self.build_resume_prompt(user, refine_with_ctx, db)

            def resolve(text: str) -> str:
                text = resolve_profile_tokens(root, text)
                return _apply_template(text, {"job": self, "user": user})

            authored = generate_resume_by_section(root, job_ctx, client, model, resolve=resolve)
            doc_tree = build_resume_document_tree(root, authored)
            Document.upsert(db, self.job_key, "resume",
                            serialize_document_tree(doc_tree), profile_id=self.profile_id)
            self.write_resume_markdown(doc_tree)
            return

        if doc_type == "resume":
            doc = ResumeDocument.model_validate_json(row.structured_json)
            prompt = prompt.replace("{current_profile_summary}", doc.profile_summary)
            prompt = prompt.replace(
                "{current_experience_indexed}",
                "\n".join(
                    f"[{i}] {e.title} at {e.company} ({e.start}–{e.end})"
                    for i, e in enumerate(doc.experience)
                ),
            )
            prompt = prompt.replace(
                "{current_projects_indexed}",
                "\n".join(f"[{i}] {p.name}" for i, p in enumerate(doc.projects)),
            )
            prompt = _apply_template(prompt, {"job": self, "user": user})
            generation = _llm_json_with_retry(
                prompt, client, model, ResumeGeneration,
                max_tokens=32768, empty_msg="Resume refine returned empty content",
            )
            patched = apply_resume_patch(doc, generation)
            Document.upsert(db, self.job_key, "resume", patched.model_dump_json(), profile_id=self.profile_id)
            self.write_resume_markdown(patched)
        else:
            doc = CoverDocument.model_validate_json(row.structured_json)
            prompt = prompt.replace("{current_document}", doc.body)
            prompt = _apply_template(prompt, {"job": self, "user": user})
            content = call_llm(prompt, client, model, max_tokens=32768)
            if not (content or "").strip():
                raise RuntimeError("Cover refine returned empty content")
            doc.body = (content or "").strip()
            Document.upsert(db, self.job_key, "cover", doc.model_dump_json(), profile_id=self.profile_id)
            self.write_cover_markdown(doc)

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
        """Patch the stored structured résumé, re-assemble the .md, and regenerate the PDF.

        Args:
            user: Hydrated User instance.
            refine_prompt: Rewriter prompt template.
            client: OpenAI-compatible client.
            model: Model identifier string.
            db: SQLAlchemy session (passed to generate_resume_pdf).
            issues: List of issue dicts from evaluate_resume_md.
            template_path: Path to the HTML resume template for PDF rendering.
        """
        self._refine_doc_md("resume", user, refine_prompt, client, model, issues, db)
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
        """Patch the stored structured cover letter, re-assemble the .md, and regenerate the PDF.

        Args:
            user: Hydrated User instance.
            refine_prompt: Rewriter prompt template.
            client: OpenAI-compatible client.
            model: Model identifier string.
            db: SQLAlchemy session (passed to generate_cover_pdf).
            issues: List of issue dicts from evaluate_cover_md.
            template_path: Path to the HTML cover letter template for PDF rendering.
        """
        self._refine_doc_md("cover", user, refine_prompt, client, model, issues, db)
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
        parsed = parse_llm_json(raw, ExtractionResponse)

        self.ext_seniority = parsed.seniority
        self.ext_role_type = parsed.role_type
        self.ext_domain = parsed.domain
        self.ext_work_arrangement = parsed.work_arrangement
        self.ext_employment_type = parsed.employment_type
        self.ext_required_skills = ", ".join(parsed.required_skills)
        self.ext_preferred_skills = ", ".join(parsed.preferred_skills)
        self.ext_tech_stack = ", ".join(parsed.tech_stack)
        self.ext_key_responsibilities = ", ".join(parsed.key_responsibilities)
        self.ext_company_signals = ", ".join(parsed.company_signals)
        self.ext_salary_min = parsed.salary_min
        self.ext_salary_max = parsed.salary_max
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
                thread_job = thread_db.query(Job).filter_by(job_key=job_key, profile_id=self.profile_id).first()
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
        template = template.replace(
            "{user_profile.work_history_indexed}", user.render_work_history_indexed()
        )
        template = template.replace(
            "{user_profile.projects_indexed}", user.render_projects_indexed()
        )
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
        """Generate the résumé as a tree-v1 document and write its Markdown.

        Runs per-section generation against the profile tree, materializes a
        self-contained document tree (pruned, value-baked, locked nodes verbatim),
        stores it under ``schema:"tree-v1"`` (source of truth), and writes the
        derived ``.md`` (no front matter).
        """
        root = user.profile_tree_root()
        prompt = self.build_resume_prompt(user, prompt_content, db)

        def resolve(text: str) -> str:
            text = resolve_profile_tokens(root, text)
            return _apply_template(text, {"job": self, "user": user})

        authored = generate_resume_by_section(root, prompt, client, model, resolve=resolve)
        doc_tree = build_resume_document_tree(root, authored)
        Document.upsert(
            db, self.job_key, "resume",
            serialize_document_tree(doc_tree), profile_id=self.profile_id,
        )
        self.write_resume_markdown(doc_tree)

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
        prompt = self.build_cover_prompt(user, prompt_content, db)
        content = call_llm(prompt, client, model, max_tokens=16384)
        if not content.strip():
            raise RuntimeError(
                "Cover letter generation returned empty content — the model likely hit "
                "its token limit before producing output (common with reasoning models). "
                "Try a non-reasoning model or a shorter prompt."
            )
        doc = build_cover_document(user, content.strip(), db)
        Document.upsert(db, self.job_key, "cover", doc.model_dump_json(), profile_id=self.profile_id)
        self.write_cover_markdown(doc)

    def write_resume_markdown(self, doc: "ResumeDocument | RootNode") -> None:
        """Write the derived résumé .md.

        A document tree (tree-v1) is rendered by the generic tree assembler with
        NO front matter — contact and education are ordinary body sections. A
        legacy ``ResumeDocument`` keeps the front matter + fixed assembler path.
        """
        _OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        md_path = _OUTPUTS_DIR / f"{self.job_key}_resume.md"
        if isinstance(doc, RootNode):
            md_path.write_text(assemble_resume_tree_markdown(doc), encoding="utf-8")
            return
        frontmatter = self._build_frontmatter_from_header(doc.header, doc.education)
        body = assemble_resume_markdown(doc)
        md_path.write_text(frontmatter + body, encoding="utf-8")

    def write_cover_markdown(self, doc: "CoverDocument") -> None:
        """Write the derived cover .md (front matter + assembled body).

        Args:
            doc: Structured cover letter produced by ``build_cover_document``.
        """
        _OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        frontmatter = self._build_frontmatter_from_header(doc.header, [])
        body = assemble_cover_markdown(doc)
        md_path = _OUTPUTS_DIR / f"{self.job_key}_cover.md"
        md_path.write_text(frontmatter + body, encoding="utf-8")

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
        md_path = _OUTPUTS_DIR / f"{self.job_key}_resume.md"
        if not md_path.exists():
            raise FileNotFoundError(f"Resume markdown not found: {md_path}")
        pdf_path = _OUTPUTS_DIR / f"{self.job_key}_resume.pdf"
        meta = self._render_meta("resume", db)
        render_pdf(md_path, pdf_path, template_path, max_pages=max_pages, meta=meta)
        self.resume_path = str(pdf_path)
        self.resume_generated_at = datetime.now(timezone.utc).isoformat()
        db.commit()

    def run_ats_check(self, db: Any, user: Any, client: Any, model: str) -> "AtsReport":
        """Run the ATS gate over this job's rendered résumé PDF.

        Loads the rendered PDF and the stored ResumeDocument (source of truth),
        runs the deterministic mechanical checks (hard-block) plus the advisory
        LLM round-trip, and returns the report. Does not mutate job state — the
        caller decides what to do with ``report.passed``.

        Args:
            db: SQLAlchemy session.
            user: Hydrated User instance (provides ``skills``).
            client: OpenAI-compatible client.
            model: Model identifier.

        Returns:
            AtsReport.

        Raises:
            FileNotFoundError: If the PDF or stored ResumeDocument is missing.
        """
        from core import ats_gate
        from core.schemas import ResumeDocument
        from db.database import Document, PromptDefault

        pdf_path = _OUTPUTS_DIR / f"{self.job_key}_resume.pdf"
        if not pdf_path.exists():
            raise FileNotFoundError(f"Resume PDF not found: {pdf_path}")
        row = Document.fetch(db, self.job_key, "resume", profile_id=self.profile_id)
        if row is None:
            raise FileNotFoundError(f"No structured resume document for {self.job_key}")
        if is_tree_v1(row.structured_json):
            from core.ats_tree_adapter import resume_document_for_ats
            doc = resume_document_for_ats(deserialize_document_tree(row.structured_json))
        else:
            doc = ResumeDocument.model_validate_json(row.structured_json)

        required = [s.strip() for s in (self.ext_required_skills or "").split(",") if s.strip()]
        preferred = [s.strip() for s in (self.ext_preferred_skills or "").split(",") if s.strip()]
        user_skills = list(getattr(user, "skills", []) or [])

        prompt_row = db.query(PromptDefault).filter_by(type_key="ats_parse").first()
        roundtrip_prompt = prompt_row.content if prompt_row else "{extracted_text}"

        pt = ats_gate.extract_text(pdf_path)
        return ats_gate.run_gate(pt, doc, required, preferred, user_skills,
                                 roundtrip_prompt, client, model)

    def store_ats_report(self, report: "AtsReport") -> None:
        """Persist an AtsReport onto the job's columns (caller commits).

        Records the result of the gate run so ``confirm-applied`` can trust the
        stored report instead of re-running the gate. Sets ``ats_checked_at`` to
        now; staleness is later judged against ``resume_generated_at``.
        """
        self.ats_passed = report.passed
        self.ats_score = report.score
        self.ats_report_json = report.model_dump_json()
        self.ats_checked_at = datetime.now(timezone.utc).isoformat()

    def ats_is_stale(self) -> bool:
        """True if no ATS check covers the current résumé render.

        Stale when the gate never ran, or the résumé PDF was (re)rendered after
        the last check (``resume_generated_at`` newer than ``ats_checked_at``).
        """
        if not self.ats_checked_at:
            return True
        if self.resume_generated_at and self.resume_generated_at > self.ats_checked_at:
            return True
        return False

    def generate_cover_pdf(self, template_path: Path, db: Session) -> None:
        """Render cover letter PDF from existing markdown and update cover_path.

        Requires generator/outputs/{job_key}_cover.md to exist.

        Args:
            template_path: Path to the Jinja2 HTML template file.
            db: SQLAlchemy session.

        Raises:
            FileNotFoundError: If the cover letter markdown file does not exist.
        """
        md_path = _OUTPUTS_DIR / f"{self.job_key}_cover.md"
        if not md_path.exists():
            raise FileNotFoundError(f"Cover markdown not found: {md_path}")
        pdf_path = _OUTPUTS_DIR / f"{self.job_key}_cover.pdf"
        meta = self._render_meta("cover", db)
        render_pdf(md_path, pdf_path, template_path, meta=meta)
        self.cover_path = str(pdf_path)
        self.cover_generated_at = datetime.now(timezone.utc).isoformat()
        db.commit()

    def generate_resume_docx(self, db: Session) -> None:
        """Render a DOCX résumé from the existing markdown via pandoc.

        DOCX is inherently single-column and highly ATS-parseable, so it is
        emitted as an alternate artifact and is not run through the ATS gate.
        Requires generator/outputs/{job_key}_resume.md to exist.

        Args:
            db: SQLAlchemy session.

        Raises:
            FileNotFoundError: If the résumé markdown file does not exist.
            RuntimeError: If pandoc fails.
        """
        import subprocess

        md_path = _OUTPUTS_DIR / f"{self.job_key}_resume.md"
        if not md_path.exists():
            raise FileNotFoundError(f"Resume markdown not found: {md_path}")
        out_path = _OUTPUTS_DIR / f"{self.job_key}_resume.docx"
        # Resolve to repo root: core/job.py → core/ → repo root → generator/
        reference = Path(__file__).parent.parent / "generator" / "reference.docx"
        cmd = ["pandoc", str(md_path), "-o", str(out_path)]
        if reference.exists():
            cmd += ["--reference-doc", str(reference)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"pandoc docx export failed: {result.stderr.strip()}")
        self.resume_docx_path = str(out_path)
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
        github = (user.github or "") or _cfg("resume_github")
        linkedin = (user.linkedin or "") or _cfg("resume_linkedin")
        website = (user.website or "") or _cfg("resume_website")
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

    def _meta_from_header(self, header: Any, education: list) -> dict:
        """Build the render/front-matter meta dict from a snapshot header.

        Mirrors _frontmatter_data's shape (firstname/lastname split from name,
        github/linkedin/website only when set, education list, company from job).
        """
        name = header.name or ""
        # rpartition keeps the final token as the surname (the cover template
        # displays lastname prominently), matching its name.split()[-1] fallback.
        first, _, last = name.rpartition(" ")
        if not first:  # single-token name → it is the first name
            first, last = last, ""
        data: dict = {
            "name": name,
            "firstname": first,
            "lastname": last,
            "email": header.email or "",
            "phone": header.phone or "",
            "location": header.location or "",
        }
        if header.github:
            data["github"] = header.github
        if header.linkedin:
            data["linkedin"] = header.linkedin
        if header.website:
            data["website"] = header.website
        if education:
            data["education"] = [e.model_dump() for e in education]
        if self.company:
            data["company"] = self.company
        return data

    def _render_meta(self, doc_type: str, db: Session) -> dict:
        """Render meta from the stored document snapshot, falling back to profile.

        For a tree-v1 résumé row there is no front-matter channel — contact and
        education render from the body — so meta is empty.
        """
        from core.user import User
        row = Document.fetch(db, self.job_key, doc_type, profile_id=self.profile_id)
        if row is not None:
            if doc_type == "resume" and is_tree_v1(row.structured_json):
                return {}
            model = ResumeDocument if doc_type == "resume" else CoverDocument
            stored = model.model_validate_json(row.structured_json)
            education = getattr(stored, "education", [])
            return self._meta_from_header(stored.header, education)
        return self._frontmatter_data(User.load(db), db)

    def _build_frontmatter_from_header(self, header: Any, education: list) -> str:
        """Serialize a snapshot header to a YAML front matter string."""
        import yaml
        return "---\n" + yaml.dump(
            self._meta_from_header(header, education),
            allow_unicode=True,
            default_flow_style=False,
        ) + "---\n\n"

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
            "ats_passed": self.ats_passed,
            "ats_score": self.ats_score,
            "ats_checked_at": self.ats_checked_at or "",
            "ats_stale": self.ats_is_stale(),
            "ats_issues": (
                json.loads(self.ats_report_json).get("issues", [])
                if self.ats_report_json else []
            ),
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
