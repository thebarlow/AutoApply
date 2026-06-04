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


def _run_doc_refinement(job_key: str, doc_type: str) -> None:
    """Background refinement loop for a generated document (resume or cover).

    Alternates between LLM evaluation and LLM rewriting until the document
    scores above pass_score or the turn limit is reached.  Per-turn snapshots
    are written to generator/outputs/ as {job_key}_{doc_type}_turn_{n}.md and
    deleted when the user dismisses the review action via /seen/{action}.

    Args:
        job_key: Unique job identifier.
        doc_type: "resume" or "cover".
    """
    import json as _json
    from pathlib import Path

    _GEN_DIR = Path(__file__).parent.parent / "generator"
    _OUTPUTS = _GEN_DIR / "outputs"
    _TEMPLATES = {
        "resume": _GEN_DIR / "resume_template.html",
        "cover": _GEN_DIR / "cover_template.html",
    }
    template_path = _TEMPLATES[doc_type]
    score_field = f"{doc_type}_eval_score"
    turns_field = f"{doc_type}_eval_turns"
    log_field = f"{doc_type}_eval_log"
    eval_key = f"{doc_type}_eval"
    refine_key = f"{doc_type}_refine"

    from db.database import Document

    def _save_turn_snapshot(n: int) -> None:
        """Snapshot the stored structured document for this turn as JSON."""
        dest = _OUTPUTS / f"{job_key}_{doc_type}_turn_{n}.json"
        sdb = SessionLocal()
        try:
            row = Document.fetch(sdb, job_key, doc_type)
            if row is not None:
                dest.write_text(row.structured_json, encoding="utf-8")
        except Exception as e:
            print(f"[refinement:{doc_type}] {job_key}: snapshot turn {n} failed: {e}", flush=True)
        finally:
            sdb.close()

    def _restore_best(eval_log: list) -> None:
        """Re-persist the highest-scoring turn's structured doc and re-render."""
        if not eval_log:
            return
        best = max(eval_log, key=lambda e: e["score"])
        best_n = best["turn"]
        snap = _OUTPUTS / f"{job_key}_{doc_type}_turn_{best_n}.json"
        if not snap.exists():
            return
        structured_json = snap.read_text(encoding="utf-8")
        db2 = SessionLocal()
        try:
            row = Document.fetch(db2, job_key, doc_type)
            if row is not None and row.structured_json == structured_json:
                return  # best turn already live
            Document.upsert(db2, job_key, doc_type, structured_json)
            job2 = Job.get(job_key, db2)
            if job2:
                from core.schemas import ResumeDocument, CoverDocument
                if doc_type == "resume":
                    job2.write_resume_markdown(ResumeDocument.model_validate_json(structured_json))
                    job2.generate_resume_pdf(template_path, db2, max_pages=1)
                else:
                    job2.write_cover_markdown(CoverDocument.model_validate_json(structured_json))
                    job2.generate_cover_pdf(template_path, db2)
                setattr(job2, score_field, best["score"])
                db2.commit()
                db2.refresh(job2)
                _emit(job2)
                print(f"[refinement:{doc_type}] {job_key}: restored turn {best_n} (best={best['score']:.2f})", flush=True)
        except Exception as e:
            print(f"[refinement:{doc_type}] {job_key}: restore failed: {e}", flush=True)
            db2.rollback()
        finally:
            db2.close()

    db = SessionLocal()
    try:
        job = Job.get(job_key, db)
        if job is None:
            return
        user = User.load(db)

        enabled = getattr(user, f"{doc_type}_refine_enabled", True)
        max_turns = int(getattr(user, f"{doc_type}_refine_max_turns", 3))
        pass_score = float(getattr(user, f"{doc_type}_refine_pass_score", 0.80))

        if not enabled or max_turns == 0:
            return

        try:
            eval_prompt = user.resolve_prompt(eval_key)
        except PromptNotConfiguredError as exc:
            print(f"[refinement:{doc_type}] {job_key}: eval prompt not configured — {exc}", flush=True)
            return

        try:
            refine_prompt = user.resolve_prompt(refine_key)
        except PromptNotConfiguredError as exc:
            print(f"[refinement:{doc_type}] {job_key}: refine prompt not configured — {exc}", flush=True)
            return

        eval_model = getattr(user, f"prompt_{eval_key}_model", "") or ""
        refine_model = getattr(user, f"prompt_{refine_key}_model", "") or ""

        try:
            eval_client, resolved_eval_model = get_client_for_profile(user, eval_model)
            refine_client, resolved_refine_model = get_client_for_profile(user, refine_model)
        except RuntimeError as exc:
            print(f"[refinement:{doc_type}] {job_key}: LLM client error — {exc}", flush=True)
            return

        eval_log = []
        result = None

        # Turn 0 = the initially generated document
        _save_turn_snapshot(0)

        for turn in range(1, max_turns + 1):
            # Step A: Evaluate
            llm_status.start(job_key, f"{doc_type}_eval")
            try:
                print(f"[refinement:{doc_type}] {job_key}: turn {turn} evaluating", flush=True)
                evaluate_fn = getattr(job, f"evaluate_{doc_type}_md")
                result = evaluate_fn(eval_prompt, user, eval_client, resolved_eval_model)
                passed = result["score"] >= pass_score
                eval_log.append({
                    "turn": turn,
                    "score": result["score"],
                    "issues": result["issues"],
                    "passed": passed,
                })
                # Snapshot the doc that was just evaluated as turn N
                _save_turn_snapshot(turn)
                setattr(job, score_field, result["score"])
                setattr(job, turns_field, turn)
                setattr(job, log_field, _json.dumps(eval_log))
                job.last_result_error = None
                db.commit()
                db.refresh(job)
                _emit(job)
                print(
                    f"[refinement:{doc_type}] {job_key}: turn {turn} score={result['score']:.2f}"
                    + (" ✓ passed" if passed else ""),
                    flush=True,
                )
            except Exception as exc:
                db.rollback()
                job = Job.get(job_key, db)
                job.last_result_error = f"{doc_type.capitalize()} eval turn {turn} failed: {exc}"
                job.unread_indicator = "error"
                db.commit()
                _emit(job)
                print(f"[refinement:{doc_type}] {job_key}: eval failed — {exc}", flush=True)
                _restore_best(eval_log)
                return
            finally:
                llm_status.finish(job_key, f"{doc_type}_eval")

            if result["score"] >= pass_score:
                return

            if turn >= max_turns:
                _restore_best(eval_log)
                return

            # Step B: Rewrite
            llm_status.start(job_key, f"{doc_type}_refine")
            try:
                print(f"[refinement:{doc_type}] {job_key}: turn {turn} rewriting", flush=True)
                refine_fn = getattr(job, f"refine_{doc_type}_md")
                refine_fn(
                    user, refine_prompt, refine_client, resolved_refine_model,
                    db, result["issues"], template_path,
                )
                db.commit()
                db.refresh(job)
                _emit(job)
                print(f"[refinement:{doc_type}] {job_key}: turn {turn} rewrite complete", flush=True)
            except Exception as exc:
                db.rollback()
                job = Job.get(job_key, db)
                job.last_result_error = f"{doc_type.capitalize()} refine turn {turn} failed: {exc}"
                job.unread_indicator = "error"
                db.commit()
                _emit(job)
                print(f"[refinement:{doc_type}] {job_key}: rewrite failed — {exc}", flush=True)
                _restore_best(eval_log)
                return
            finally:
                llm_status.finish(job_key, f"{doc_type}_refine")
    finally:
        db.close()


def run_resume_refinement(job_key: str) -> None:
    """Run the evaluate→rewrite loop for a generated resume."""
    _run_doc_refinement(job_key, "resume")


def run_cover_refinement(job_key: str) -> None:
    """Run the evaluate→rewrite loop for a generated cover letter."""
    _run_doc_refinement(job_key, "cover")
