from __future__ import annotations

import json as _json
import logging

from db.database import SessionLocal
from core.job import Job
from web.sse import send as _sse_send
from web import llm_status
from web.routers.jobs import _do_extract_description, _load_score_config
from core.user import User, PromptNotConfiguredError
from core.llm import get_client_for_profile
from core.credits import InsufficientCredits
from core.metering import meter_action
from core.section_generator import generate_resume_by_section

from pathlib import Path as _Path

_OUTPUTS_DIR = _Path(__file__).parent.parent / "generator" / "outputs"

logger = logging.getLogger(__name__)


def _render_doc_from_json(job, doc_type: str, structured_json: str, template_path, db) -> None:
    """Re-render a résumé or cover letter from stored structured JSON.

    Branches on tree-v1 discriminator for résumés; legacy path uses
    ResumeDocument. Cover path unchanged.
    """
    from core.schemas import ResumeDocument, CoverDocument
    from core.resume_document_io import is_tree_v1, deserialize_document_tree

    if doc_type == "resume":
        if is_tree_v1(structured_json):
            job.write_resume_markdown(deserialize_document_tree(structured_json))
        else:
            job.write_resume_markdown(ResumeDocument.model_validate_json(structured_json))
        job.generate_resume_pdf(template_path, db)
    else:
        job.write_cover_markdown(CoverDocument.model_validate_json(structured_json))
        job.generate_cover_pdf(template_path, db)


def build_feedback_issues(notes: list[dict]) -> list[dict]:
    """Convert UI section-anchored feedback notes to refine ``issues``.

    Each note is ``{"section", "label", "note"}``. The ``label`` carries the
    human-readable (and, for résumés, index-bearing) section anchor so the
    refine prompt can locate the target. Notes with blank text are dropped.

    Args:
        notes: List of note dicts from the feedback modal.

    Returns:
        Issue dicts shaped like ``EvalResponse`` issues:
        ``{"category": "user_feedback", "description": "<label>: <note>"}``.
    """
    issues = []
    for n in notes:
        text = (n.get("note") or "").strip()
        if not text:
            continue
        label = (n.get("label") or "").strip() or "Document"
        issue: dict = {"category": "user_feedback", "description": f"{label}: {text}"}
        section = (n.get("section") or "").strip()
        if section:
            issue["section"] = section
        issues.append(issue)
    return issues


def _emit(job: Job) -> None:
    try:
        _sse_send("job", job.serialize(), profile_id=job.profile_id)
    except Exception as exc:
        logger.warning("SSE emit failed for %s: %s", job.job_key, exc)


def _do_score(job: Job, db, profile_id: int) -> None:
    """Run scoring and persist results."""
    user = User.load(db, profile_id)
    try:
        prompt_content = user.resolve_prompt("scoring")
    except PromptNotConfiguredError as exc:
        raise RuntimeError(str(exc)) from exc
    try:
        client, model = get_client_for_profile(user, user.prompt_scoring_model)
    except RuntimeError:
        raise

    config = _load_score_config(db, profile_id)
    with meter_action(db, profile_id, action="score", job_key=job.job_key):
        job.score(user, config, client, model, db, prompt_content)
    job.unread_indicator = "ok"
    job.last_result_error = None
    db.commit()


def run_pipeline(job_key: str, profile_id: int) -> None:
    """Run description extraction then scoring for a newly ingested job."""
    db = SessionLocal()
    try:
        job = Job.get(job_key, db, profile_id)
        if job is None:
            return

        if not job.has_description():
            job.unread_indicator = "error"
            job.last_result_error = "Scrape failed: empty description."
            db.commit()
            _emit(job)
            return

        # Step 1: description extraction
        llm_status.start(profile_id, job_key, "description")
        extraction_ok = False
        try:
            _do_extract_description(job, db, profile_id)
            extraction_ok = True
        except Exception as exc:
            db.rollback()
            job = Job.get(job_key, db, profile_id)
            job.unread_indicator = "error"
            job.last_result_error = str(exc)
            db.commit()
        finally:
            llm_status.finish(profile_id, job_key, "description")
        db.refresh(job)
        _emit(job)

        if not extraction_ok:
            return

        # Step 2: scoring
        llm_status.start(profile_id, job_key, "score")
        try:
            _do_score(job, db, profile_id)
        except Exception as exc:
            db.rollback()
            job = Job.get(job_key, db, profile_id)
            job.unread_indicator = "error"
            job.last_result_error = str(exc)
            db.commit()
        finally:
            llm_status.finish(profile_id, job_key, "score")
        db.refresh(job)
        _emit(job)
    finally:
        db.close()


def _restore_best_sections(db, job_key: str, profile_id: int,
                           eval_log: list[dict], template_path) -> None:
    """Re-persist + re-render the highest-min turn's snapshot (tree-v1)."""
    from db.database import Document

    if not eval_log:
        return
    best = max(eval_log, key=lambda e: e["score"])
    snap = _OUTPUTS_DIR / f"{profile_id}_{job_key}_resume_turn_{best['turn']}.json"
    if not snap.exists():
        return
    structured_json = snap.read_text(encoding="utf-8")
    cur = Document.fetch(db, job_key, "resume", profile_id)
    if cur is not None and cur.structured_json == structured_json:
        return
    Document.upsert(db, job_key, "resume", structured_json, profile_id)
    job = Job.get(job_key, db, profile_id)
    if job is not None:
        _render_doc_from_json(job, "resume", structured_json, template_path, db)
        job.resume_eval_score = best["score"]
        db.commit()
        db.refresh(job)
        _emit(job)


def _run_resume_section_refinement(job_key: str, profile_id: int) -> None:
    """Per-section auto-refine for a tree-v1 résumé: score each regenerable
    section, regenerate only sub-threshold sections (with their issues as
    critique), repeat until all pass or max_turns; restore the best-by-min
    turn."""
    import json as _json
    from pathlib import Path
    from core.document_tree import authored_values_from_tree, build_resume_document_tree
    from core.profile_tree import resolve_profile_tokens
    from core.resume_document_io import (
        serialize_document_tree, deserialize_document_tree, is_tree_v1,
    )
    from core.job import Job, _apply_template
    from core.user import User, PromptNotConfiguredError
    from db.database import Document

    template_path = Path(__file__).parent.parent / "generator" / "resume_template.html"

    db = SessionLocal()
    try:
        job = Job.get(job_key, db, profile_id)
        if job is None:
            return
        user = User.load(db, profile_id)
        if not getattr(user, "resume_refine_enabled", True):
            return
        max_turns = int(getattr(user, "resume_refine_max_turns", 3))
        pass_score = float(getattr(user, "resume_refine_pass_score", 0.80))
        if max_turns == 0:
            return

        row = Document.fetch(db, job_key, "resume", profile_id)
        if row is None or not is_tree_v1(row.structured_json):
            return

        try:
            eval_prompt = user.resolve_prompt("resume_eval_sectioned")
            gen_prompt = user.resolve_prompt("resume")
        except PromptNotConfiguredError as exc:
            print(f"[section-refine] {job_key}: prompt not configured — {exc}", flush=True)
            return
        eval_client, eval_model = get_client_for_profile(
            user, getattr(user, "prompt_resume_eval_sectioned_model", "") or "")
        gen_client, gen_model = get_client_for_profile(
            user, getattr(user, "prompt_resume_model", "") or "")

        root = user.profile_tree_root()
        authored = authored_values_from_tree(deserialize_document_tree(row.structured_json))
        job_ctx = job.build_resume_prompt(user, gen_prompt, db)

        def resolve(text: str) -> str:
            return _apply_template(resolve_profile_tokens(root, text), {"job": job, "user": user})

        def _snapshot(n: int) -> None:
            r = Document.fetch(db, job_key, "resume", profile_id)
            if r is not None:
                (_OUTPUTS_DIR / f"{profile_id}_{job_key}_resume_turn_{n}.json").write_text(
                    r.structured_json, encoding="utf-8")

        eval_log: list[dict] = []
        _snapshot(0)
        for turn in range(1, max_turns + 1):
            llm_status.start(profile_id, job_key, "resume_eval")
            try:
                with meter_action(db, profile_id, action="eval", job_key=job_key):
                    scores = job.evaluate_resume_sections(
                        eval_prompt, user, eval_client, eval_model, db)
            except Exception as exc:
                db.rollback()
                job = Job.get(job_key, db, profile_id)
                job.last_result_error = f"Section eval turn {turn} failed: {exc}"
                job.unread_indicator = "error"
                db.commit()
                _emit(job)
                logger.exception("%s: section eval turn %s failed", job_key, turn)
                _restore_best_sections(db, job_key, profile_id, eval_log, template_path)
                return
            finally:
                llm_status.finish(profile_id, job_key, "resume_eval")

            if not scores:
                return
            min_score = min(s["score"] for s in scores.values())
            failing = {n for n, s in scores.items() if s["score"] < pass_score}
            eval_log.append({"turn": turn, "score": min_score,
                             "issues": [i for s in scores.values() for i in s["issues"]],
                             "passed": not failing})
            job.resume_eval_score = min_score
            job.resume_eval_turns = turn
            job.resume_eval_log = _json.dumps(eval_log)
            job.last_result_error = None
            db.commit()
            db.refresh(job)
            _emit(job)

            if not failing:
                return
            if turn >= max_turns:
                _restore_best_sections(db, job_key, profile_id, eval_log, template_path)
                return

            llm_status.start(profile_id, job_key, "resume_refine")
            try:
                critiques = {n: scores[n]["issues"] for n in failing}
                with meter_action(db, profile_id, action="refine", job_key=job_key):
                    new_vals = generate_resume_by_section(
                        root, job_ctx, gen_client, gen_model, resolve=resolve,
                        only_sections=failing, critiques=critiques)
                authored.update(new_vals)
                doc_tree = build_resume_document_tree(root, authored)
                Document.upsert(db, job_key, "resume",
                                serialize_document_tree(doc_tree), profile_id=profile_id)
                job.write_resume_markdown(doc_tree)
                job.generate_resume_pdf(template_path, db)
                db.commit()
                db.refresh(job)
                _emit(job)
            except Exception as exc:
                db.rollback()
                job = Job.get(job_key, db, profile_id)
                job.last_result_error = f"Section refine turn {turn} failed: {exc}"
                job.unread_indicator = "error"
                db.commit()
                _emit(job)
                logger.exception("%s: section refine turn %s failed", job_key, turn)
                _restore_best_sections(db, job_key, profile_id, eval_log, template_path)
                return
            finally:
                llm_status.finish(profile_id, job_key, "resume_refine")
    finally:
        db.close()


def _run_doc_refinement(job_key: str, doc_type: str, profile_id: int) -> None:
    """Background refinement loop for a generated document (resume or cover).

    Alternates between LLM evaluation and LLM rewriting until the document
    scores above pass_score or the turn limit is reached.  Per-turn snapshots
    are written to generator/outputs/ as {job_key}_{doc_type}_turn_{n}.json and
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
        dest = _OUTPUTS / f"{profile_id}_{job_key}_{doc_type}_turn_{n}.json"
        sdb = SessionLocal()
        try:
            row = Document.fetch(sdb, job_key, doc_type, profile_id)
            if row is not None:
                dest.write_text(row.structured_json, encoding="utf-8")
            else:
                print(f"[refinement:{doc_type}] {job_key}: snapshot turn {n}: no Document row — skipped", flush=True)
        except Exception as e:
            logger.exception("%s: %s snapshot turn %s failed", job_key, doc_type, n)
        finally:
            sdb.close()

    def _restore_best(eval_log: list) -> None:
        """Re-persist the highest-scoring turn's structured doc and re-render."""
        if not eval_log:
            return
        best = max(eval_log, key=lambda e: e["score"])
        best_n = best["turn"]
        snap = _OUTPUTS / f"{profile_id}_{job_key}_{doc_type}_turn_{best_n}.json"
        if not snap.exists():
            return
        structured_json = snap.read_text(encoding="utf-8")
        db2 = SessionLocal()
        try:
            row = Document.fetch(db2, job_key, doc_type, profile_id)
            if row is not None and row.structured_json == structured_json:
                return  # best turn already live
            Document.upsert(db2, job_key, doc_type, structured_json, profile_id)
            job2 = Job.get(job_key, db2, profile_id)
            if job2:
                _render_doc_from_json(job2, doc_type, structured_json, template_path, db2)
                setattr(job2, score_field, best["score"])
                db2.commit()
                db2.refresh(job2)
                _emit(job2)
                print(f"[refinement:{doc_type}] {job_key}: restored turn {best_n} (best={best['score']:.2f})", flush=True)
        except Exception as e:
            logger.exception("%s: %s restore failed", job_key, doc_type)
            db2.rollback()
        finally:
            db2.close()

    db = SessionLocal()
    try:
        job = Job.get(job_key, db, profile_id)
        if job is None:
            return

        # Dispatch: all résumés are tree-v1 (generation always produces a
        # document tree), so résumé refinement is always the per-section loop.
        # The generic evaluate→rewrite loop below is cover-only.
        if doc_type == "resume":
            _run_resume_section_refinement(job_key, profile_id)
            return

        user = User.load(db, profile_id)

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
            llm_status.start(profile_id, job_key, f"{doc_type}_eval")
            try:
                print(f"[refinement:{doc_type}] {job_key}: turn {turn} evaluating", flush=True)
                evaluate_fn = getattr(job, f"evaluate_{doc_type}_md")
                with meter_action(db, profile_id, action="eval", job_key=job.job_key):
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
                job = Job.get(job_key, db, profile_id)
                job.last_result_error = f"{doc_type.capitalize()} eval turn {turn} failed: {exc}"
                job.unread_indicator = "error"
                db.commit()
                _emit(job)
                logger.exception("%s: %s eval failed", job_key, doc_type)
                _restore_best(eval_log)
                return
            finally:
                llm_status.finish(profile_id, job_key, f"{doc_type}_eval")

            if result["score"] >= pass_score:
                return

            if turn >= max_turns:
                _restore_best(eval_log)
                return

            # Step B: Rewrite
            llm_status.start(profile_id, job_key, f"{doc_type}_refine")
            try:
                print(f"[refinement:{doc_type}] {job_key}: turn {turn} rewriting", flush=True)
                refine_fn = getattr(job, f"refine_{doc_type}_md")
                with meter_action(db, profile_id, action="refine", job_key=job.job_key):
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
                job = Job.get(job_key, db, profile_id)
                job.last_result_error = f"{doc_type.capitalize()} refine turn {turn} failed: {exc}"
                job.unread_indicator = "error"
                db.commit()
                _emit(job)
                logger.exception("%s: %s rewrite failed", job_key, doc_type)
                _restore_best(eval_log)
                return
            finally:
                llm_status.finish(profile_id, job_key, f"{doc_type}_refine")
    finally:
        db.close()


def run_ats_gate(job_key: str, profile_id: int) -> None:
    """Run the ATS gate over the current résumé render and persist the report.

    Background entry point. Resolves the active profile's client/model, runs both
    gate layers (mechanical + LLM round-trip), stores the report on the job, and
    emits a UI update. Failures (missing artifacts, no profile) are logged and
    swallowed so they never break the request that spawned this thread.
    """
    llm_status.start(profile_id, job_key, "ats")
    db = SessionLocal()
    try:
        job = Job.get(job_key, db, profile_id)
        if job is None:
            return
        try:
            user = User.load(db, profile_id)
        except RuntimeError as exc:
            print(f"[ats] {job_key}: no profile — {exc}", flush=True)
            return
        try:
            client, model = get_client_for_profile(user)
        except RuntimeError as exc:
            print(f"[ats] {job_key}: LLM client error — {exc}", flush=True)
            return
        try:
            # Metered: the gate's LLM round-trip is user-triggerable at will
            # (every résumé document save re-spawns it), so it must be billed
            # and blocked at zero balance like any other LLM action.
            with meter_action(db, profile_id, action="ats", job_key=job_key):
                report = job.run_ats_check(db, user, client, model)
        except InsufficientCredits as exc:
            print(f"[ats] {job_key}: skipped — {exc}", flush=True)
            return
        except FileNotFoundError as exc:
            print(f"[ats] {job_key}: artifact missing — {exc}", flush=True)
            return
        job.store_ats_report(report)
        db.commit()
        db.refresh(job)
        _emit(job)
        print(
            f"[ats] {job_key}: passed={report.passed} score={report.score:.2f} "
            f"issues={len(report.issues)}",
            flush=True,
        )
    except Exception as exc:
        db.rollback()
        logger.exception("%s: ATS gate run failed", job_key)
    finally:
        db.close()
        llm_status.finish(profile_id, job_key, "ats")


def run_resume_refinement(job_key: str, profile_id: int) -> None:
    """Run the evaluate→rewrite loop for a generated resume, then the ATS gate.

    The gate runs after refinement settles so it scores the final résumé render.
    ``_run_doc_refinement`` is a no-op when refinement is disabled or set to 0
    turns, so this also covers the "gate right after generation" case.

    Runs in a daemon thread; any failure is logged rather than raised so it never
    surfaces as an unhandled thread exception.
    """
    try:
        _run_doc_refinement(job_key, "resume", profile_id)
    except Exception as exc:
        logger.exception("%s: resume refinement failed", job_key)
    run_ats_gate(job_key, profile_id)


def run_cover_refinement(job_key: str, profile_id: int) -> None:
    """Run the evaluate→rewrite loop for a generated cover letter."""
    _run_doc_refinement(job_key, "cover", profile_id)


def _run_resume_feedback_refine(job_key: str, doc_type: str, notes: list[dict], profile_id: int) -> None:
    """Tree-v1 résumé user-feedback refine: regenerate only the commented,
    regenerable sections via 4B-2 selective regen, then eval-for-score + ATS.
    No restore-best (the user-directed result is always kept)."""
    import json as _json
    from pathlib import Path
    from core.document_tree import authored_values_from_tree, build_resume_document_tree
    from core.profile_tree import resolve_profile_tokens
    from core.resume_document_io import serialize_document_tree, deserialize_document_tree
    from core.job import Job, _apply_template
    from db.database import Document

    template_path = Path(__file__).parent.parent / "generator" / "resume_template.html"
    issues = build_feedback_issues(notes)
    if not issues:
        return

    db = SessionLocal()
    try:
        job = Job.get(job_key, db, profile_id)
        if job is None:
            return
        user = User.load(db, profile_id)
        row = Document.fetch(db, job_key, "resume", profile_id)
        if row is None:
            return

        # Group notes by owning section, keep only regenerable ones.
        regenerable = set(job._regenerable_section_names(db))
        by_section: dict[str, list[dict]] = {}
        for i in issues:
            sec = i.get("section")
            if sec in regenerable:
                by_section.setdefault(sec, []).append(i)

        if by_section:
            try:
                gen_prompt = user.resolve_prompt("resume")
            except PromptNotConfiguredError as exc:
                print(f"[feedback:resume] {job_key}: prompt not configured — {exc}", flush=True)
                return
            gen_client, gen_model = get_client_for_profile(
                user, getattr(user, "prompt_resume_model", "") or "")
            root = user.profile_tree_root()
            authored = authored_values_from_tree(deserialize_document_tree(row.structured_json))
            job_ctx = job.build_resume_prompt(user, gen_prompt, db)

            def resolve(text: str) -> str:
                return _apply_template(resolve_profile_tokens(root, text), {"job": job, "user": user})

            llm_status.start(profile_id, job_key, "resume_refine")
            try:
                with meter_action(db, profile_id, action="refine", job_key=job_key):
                    new_vals = generate_resume_by_section(
                        root, job_ctx, gen_client, gen_model, resolve=resolve,
                        only_sections=set(by_section), critiques=by_section)
                authored.update(new_vals)
                doc_tree = build_resume_document_tree(root, authored)
                Document.upsert(db, job_key, "resume",
                                serialize_document_tree(doc_tree), profile_id=profile_id)
                job.write_resume_markdown(doc_tree)
                job.generate_resume_pdf(template_path, db)
                db.commit()
                db.refresh(job)
                _emit(job)
            except Exception as exc:
                db.rollback()
                job = Job.get(job_key, db, profile_id)
                job.last_result_error = f"Resume feedback refine failed: {exc}"
                job.unread_indicator = "error"
                db.commit()
                _emit(job)
                logger.exception("%s: resume feedback refine failed", job_key)
                return
            finally:
                llm_status.finish(profile_id, job_key, "resume_refine")

        # Eval-for-score (informational; non-fatal; no restore-best).
        llm_status.start(profile_id, job_key, "resume_eval")
        try:
            eval_prompt = user.resolve_prompt("resume_eval_sectioned")
            eval_client, eval_model = get_client_for_profile(
                user, getattr(user, "prompt_resume_eval_sectioned_model", "") or "")
            with meter_action(db, profile_id, action="eval", job_key=job_key):
                scores = job.evaluate_resume_sections(eval_prompt, user, eval_client, eval_model, db)
            if scores:
                min_score = min(s["score"] for s in scores.values())
                pass_score = float(getattr(user, "resume_refine_pass_score", 0.80))
                eval_log = _json.loads(job.resume_eval_log or "[]")
                turn = len(eval_log) + 1
                eval_log.append({"turn": turn, "score": min_score,
                                 "issues": [i for s in scores.values() for i in s["issues"]],
                                 "passed": min_score >= pass_score, "source": "user_feedback"})
                job.resume_eval_score = min_score
                job.resume_eval_turns = turn
                job.resume_eval_log = _json.dumps(eval_log)
                db.commit()
                db.refresh(job)
                _emit(job)
        except Exception as exc:
            db.rollback()
            logger.exception("%s: post-feedback resume eval failed (non-fatal)", job_key)
        finally:
            llm_status.finish(profile_id, job_key, "resume_eval")
    finally:
        db.close()

    run_ats_gate(job_key, profile_id)


def run_user_feedback_refine(job_key: str, doc_type: str, notes: list[dict], profile_id: int) -> None:
    """Apply user section-anchored feedback as a one-shot refine.

    Reuses the existing refine path (patch structured doc → re-derive md →
    re-render PDF). Then runs eval once for an informational score and appends a
    turn tagged ``source="user_feedback"``. Unlike the auto loop it does NOT
    restore a prior best turn — the user-directed result is always kept. Résumé
    runs trigger the ATS gate afterward. Runs in a daemon thread; failures are
    logged, never raised.

    Args:
        job_key: Unique job identifier.
        doc_type: "resume" or "cover".
        notes: Feedback notes from the modal (``{section,label,note}``).
    """
    from pathlib import Path

    if doc_type not in ("resume", "cover"):
        print(f"[feedback] {job_key}: invalid doc_type {doc_type!r}", flush=True)
        return

    issues = build_feedback_issues(notes)
    if not issues:
        return

    # Tree-v1 résumés use the selective per-section regen path.
    if doc_type == "resume":
        _probe = SessionLocal()
        try:
            from db.database import Document
            from core.resume_document_io import is_tree_v1
            _r = Document.fetch(_probe, job_key, "resume", profile_id)
            _is_tree = _r is not None and is_tree_v1(_r.structured_json)
        finally:
            _probe.close()
        if _is_tree:
            _run_resume_feedback_refine(job_key, "resume", notes, profile_id)
            return

    _GEN_DIR = Path(__file__).parent.parent / "generator"
    template_path = {
        "resume": _GEN_DIR / "resume_template.html",
        "cover": _GEN_DIR / "cover_template.html",
    }[doc_type]
    refine_key = f"{doc_type}_refine"
    eval_key = f"{doc_type}_eval"

    db = SessionLocal()
    try:
        job = Job.get(job_key, db, profile_id)
        if job is None:
            return
        user = User.load(db, profile_id)

        try:
            refine_prompt = user.resolve_prompt(refine_key)
        except PromptNotConfiguredError as exc:
            print(f"[feedback:{doc_type}] {job_key}: refine prompt not configured — {exc}", flush=True)
            return

        refine_model = getattr(user, f"prompt_{refine_key}_model", "") or ""
        try:
            refine_client, resolved_refine_model = get_client_for_profile(user, refine_model)
        except RuntimeError as exc:
            print(f"[feedback:{doc_type}] {job_key}: LLM client error — {exc}", flush=True)
            return

        # Step A: refine with user-authored issues
        llm_status.start(profile_id, job_key, f"{doc_type}_refine")
        try:
            refine_fn = getattr(job, f"refine_{doc_type}_md")
            with meter_action(db, profile_id, action="refine", job_key=job.job_key):
                refine_fn(
                    user, refine_prompt, refine_client, resolved_refine_model,
                    db, issues, template_path,
                )
            db.commit()
            db.refresh(job)
            _emit(job)
        except Exception as exc:
            db.rollback()
            job = Job.get(job_key, db, profile_id)
            job.last_result_error = f"{doc_type.capitalize()} feedback refine failed: {exc}"
            job.unread_indicator = "error"
            db.commit()
            _emit(job)
            logger.exception("%s: %s feedback refine failed", job_key, doc_type)
            return
        finally:
            llm_status.finish(profile_id, job_key, f"{doc_type}_refine")

        # Step B: eval once for an informational score (non-fatal; no restore-best)
        llm_status.start(profile_id, job_key, f"{doc_type}_eval")
        try:
            eval_prompt = user.resolve_prompt(eval_key)
            eval_model = getattr(user, f"prompt_{eval_key}_model", "") or ""
            eval_client, resolved_eval_model = get_client_for_profile(user, eval_model)
            evaluate_fn = getattr(job, f"evaluate_{doc_type}_md")
            with meter_action(db, profile_id, action="eval", job_key=job.job_key):
                result = evaluate_fn(eval_prompt, user, eval_client, resolved_eval_model)

            pass_score = float(getattr(user, f"{doc_type}_refine_pass_score", 0.80))
            log_field = f"{doc_type}_eval_log"
            eval_log = _json.loads(getattr(job, log_field) or "[]")
            turn = len(eval_log) + 1
            eval_log.append({
                "turn": turn,
                "score": result["score"],
                "issues": result["issues"],
                "passed": result["score"] >= pass_score,
                "source": "user_feedback",
            })
            setattr(job, f"{doc_type}_eval_score", result["score"])
            setattr(job, f"{doc_type}_eval_turns", turn)
            setattr(job, log_field, _json.dumps(eval_log))
            db.commit()
            db.refresh(job)
            _emit(job)
        except Exception as exc:
            db.rollback()
            logger.exception("%s: %s post-feedback eval failed (non-fatal)", job_key, doc_type)
        finally:
            llm_status.finish(profile_id, job_key, f"{doc_type}_eval")
    finally:
        db.close()

    if doc_type == "resume":
        run_ats_gate(job_key, profile_id)
