"""Orchestrate the split résumé eval: mechanical checks run here (free,
instant), semantic checks are produced by a dispatched subagent against
prompts/eval_prompt.md and written to a scratch file, then finalized here.

Flow:
    python -m workflows.eval_resume <job_key>
        -> runs check_required_skills_covered + check_continuity locally,
           writes them to scratch_path(job_key, "eval_mechanical"),
           prints what's needed to dispatch the semantic-check subagent.

    [Claude Code dispatches a subagent against prompts/eval_prompt.md,
     which Writes its 4-check result to scratch_path(job_key, "eval_semantic")]

    python -m workflows.eval_resume <job_key> --finalize
        -> reads both scratch files, combines into the full 6-check shape,
           merges into workflows/output/resume_evals.json via merge_job_entry.

This script does not drive the patch-loop-until-pass decision itself — see
eval_loop.py for that. It only owns "how a single eval run's checks are
computed and written."
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from workflows.merge_utils import merge_job_entry, read_json, scratch_path
from workflows.resume_checks import check_continuity, check_required_skills_covered, required_direct_skills

_OUT_DIR = Path("workflows/output")

_SEMANTIC_CHECKS = ("no_fabrication", "no_keyword_stuffing", "no_irrelevant_content", "summary_specific")


def run_mechanical(job_key: str) -> dict:
    """Compute the two mechanical checks and write them to a scratch file."""
    resumes = read_json(_OUT_DIR / "resumes.json")
    compared = read_json(_OUT_DIR / "compared.json")
    profile = read_json(_OUT_DIR / "profile.json")

    resume = resumes[job_key]
    req = required_direct_skills(compared.get(job_key, {}))
    checks = {
        "required_skills_covered": check_required_skills_covered(resume, req),
        "no_continuity_errors": check_continuity(resume, profile),
    }
    scratch_path(job_key, "eval_mechanical").write_text(json.dumps(checks, indent=2), encoding="utf-8")
    return checks


def finalize_eval(job_key: str) -> dict:
    """Combine mechanical (scratch) + semantic (scratch, from subagent) checks
    into the full resume_evals.json shape and merge it in."""
    mechanical_path = scratch_path(job_key, "eval_mechanical")
    semantic_path = scratch_path(job_key, "eval_semantic")
    if not mechanical_path.exists():
        raise FileNotFoundError(f"{mechanical_path} missing — run without --finalize first.")
    if not semantic_path.exists():
        raise FileNotFoundError(f"{semantic_path} missing — dispatch the semantic-check subagent first.")

    mechanical = json.loads(mechanical_path.read_text(encoding="utf-8"))
    semantic = json.loads(semantic_path.read_text(encoding="utf-8"))
    semantic_checks = semantic.get("checks", semantic)  # tolerate either {"checks": {...}} or bare {...}

    missing = [c for c in _SEMANTIC_CHECKS if c not in semantic_checks]
    if missing:
        raise ValueError(f"Semantic scratch file missing checks: {missing}")

    checks = {**mechanical, **semantic_checks}
    overall_pass = all(c.get("pass", False) for c in checks.values())
    entry = {"checks": checks, "overall_pass": overall_pass}
    merge_job_entry(_OUT_DIR / "resume_evals.json", job_key, entry)
    return entry


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job_key")
    parser.add_argument("--finalize", action="store_true", help="Combine mechanical + semantic scratch results into resume_evals.json.")
    args = parser.parse_args()

    if args.finalize:
        entry = finalize_eval(args.job_key)
        status = "PASS" if entry["overall_pass"] else "FAIL"
        failing = [k for k, v in entry["checks"].items() if not v.get("pass", False)]
        print(f"{args.job_key}: [{status}]" + (f" failing: {failing}" if failing else ""))
        print(f"wrote {_OUT_DIR / 'resume_evals.json'}")
        return

    checks = run_mechanical(args.job_key)
    failing = [k for k, v in checks.items() if not v.get("pass", False)]
    print(f"{args.job_key}: mechanical checks computed. failing: {failing or 'none'}")
    print(f"wrote {scratch_path(args.job_key, 'eval_mechanical')}")
    print(
        f"\nNext: dispatch a subagent against prompts/eval_prompt.md for job_key={args.job_key} "
        f"(needs job fields from extracted.json, profile.json, and resumes.json[{args.job_key!r}]); "
        f"have it Write its 4-check result to {scratch_path(args.job_key, 'eval_semantic')}, "
        f"then re-run this script with --finalize."
    )


if __name__ == "__main__":
    main()
