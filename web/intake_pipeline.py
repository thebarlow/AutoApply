from __future__ import annotations

from db.database import SessionLocal
from core.job import Job
from web.sse import send as _sse_send
from web import llm_status
from web.routers.jobs import _do_extract_description, _load_score_config
from core.user import User, PromptNotConfiguredError
from core.llm import get_client_for_profile


def _emit(job: Job) -> None:
    try:
        _sse_send("job", job.serialize())
    except Exception as exc:
        print(f"[intake_pipeline] SSE emit failed for {job.job_key}: {exc}", flush=True)


def _do_score(job: Job, db) -> None:
    """Run scoring and persist results."""
    user = User.load(db)
    try:
        prompt_content = user.resolve_prompt("scoring")
    except PromptNotConfiguredError as exc:
        raise RuntimeError(str(exc)) from exc
    try:
        client, model = get_client_for_profile(user, user.prompt_scoring_model)
    except RuntimeError:
        raise

    config = _load_score_config(db)
    job.score(user, config, client, model, db, prompt_content)
    job.unread_indicator = "ok"
    job.last_result_error = None
    db.commit()


def run_pipeline(job_key: str) -> None:
    """Run description extraction then scoring for a newly ingested job."""
    db = SessionLocal()
    try:
        job = Job.get(job_key, db)
        if job is None:
            return

        # Step 1: description extraction
        llm_status.start(job_key, "description")
        extraction_ok = False
        try:
            _do_extract_description(job, db)
            extraction_ok = True
        except Exception as exc:
            db.rollback()
            job = Job.get(job_key, db)
            job.unread_indicator = "error"
            job.last_result_error = str(exc)
            db.commit()
        finally:
            llm_status.finish(job_key, "description")
        db.refresh(job)
        _emit(job)

        if not extraction_ok:
            return

        # Step 2: scoring
        llm_status.start(job_key, "score")
        try:
            _do_score(job, db)
        except Exception as exc:
            db.rollback()
            job = Job.get(job_key, db)
            job.unread_indicator = "error"
            job.last_result_error = str(exc)
            db.commit()
        finally:
            llm_status.finish(job_key, "score")
        db.refresh(job)
        _emit(job)
    finally:
        db.close()
