"""Eval/patch loop state machine.

Pure control-flow, no LLM calls of its own — it can't dispatch a subagent
(only Claude Code can), so its job is to tell Claude Code exactly what to do
next, replacing the manual turn-counting and failing-check bookkeeping that
was previously done by hand.

Usage (Claude Code consults this between dispatches, it is not an autonomous
background loop):

    python -m workflows.eval_loop <job_key> [--cap 3]

Returns one of four actions as JSON on stdout:
    {"action": "run_eval"}
        No eval yet this round. Run `eval_resume.py <job_key>` (mechanical),
        dispatch the semantic subagent, run `eval_resume.py <job_key>
        --finalize`, then call this script again.
    {"action": "dispatch_patch", "turn": n, "failing_checks": {...}}
        Eval failed and turn < cap. Dispatch a patch subagent against
        prompts/patch_prompt.md with exactly this failing_checks payload
        (scratch-file output per merge_utils' convention), merge its result
        into resumes.json, then call this script again (it will record the
        turn and route back through run_eval).
    {"action": "done", "result": "pass"}
        overall_pass is true. Stop.
    {"action": "done", "result": "cap_reached", "remaining_issues": {...}}
        Still failing at turn >= cap. Stop; a human should look at
        remaining_issues.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from workflows.merge_utils import read_json, scratch_path

_EVAL_PATH = Path("workflows/output/resume_evals.json")


def _loop_state_path(job_key: str):
    return scratch_path(job_key, "loop_state")


def _load_state(job_key: str) -> dict:
    path = _loop_state_path(job_key)
    if not path.exists():
        return {"turn": 0, "history": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_state(job_key: str, state: dict) -> None:
    _loop_state_path(job_key).write_text(json.dumps(state, indent=2), encoding="utf-8")


def next_step(job_key: str, cap: int = 3) -> dict:
    """Decide the next action for job_key's eval/patch loop. Advances loop
    state (increments turn) whenever it hands back a dispatch_patch action for
    a NEW turn — callers should not increment turn themselves."""
    evals = read_json(_EVAL_PATH)
    entry = evals.get(job_key)
    state = _load_state(job_key)

    if entry is None:
        # No eval recorded yet. But maybe the mechanical+semantic scratch
        # files exist from a not-yet-finalized run — leave that to
        # eval_resume.py to detect; from this script's point of view, no
        # entry means "go run an eval."
        return {"action": "run_eval"}

    failing = {k: v for k, v in entry["checks"].items() if not v.get("pass", False)}

    if entry.get("overall_pass"):
        state["history"].append({"turn": state["turn"], "result": "pass"})
        _save_state(job_key, state)
        return {"action": "done", "result": "pass"}

    if state["turn"] >= cap:
        state["history"].append({"turn": state["turn"], "result": "cap_reached", "failing": list(failing)})
        _save_state(job_key, state)
        return {"action": "done", "result": "cap_reached", "remaining_issues": failing}

    turn = state["turn"] + 1
    state["turn"] = turn
    state["history"].append({"turn": turn, "result": "dispatch_patch", "failing": list(failing)})
    _save_state(job_key, state)
    return {
        "action": "dispatch_patch",
        "turn": turn,
        "failing_checks": failing,
        "patch_scratch_path": str(scratch_path(job_key, "patch")),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job_key")
    parser.add_argument("--cap", type=int, default=3)
    parser.add_argument("--reset", action="store_true", help="Clear loop state for this job_key and exit.")
    args = parser.parse_args()

    if args.reset:
        state_path = _loop_state_path(args.job_key)
        if state_path.exists():
            state_path.unlink()
        print(f"reset loop state for {args.job_key}")
        return

    result = next_step(args.job_key, cap=args.cap)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
