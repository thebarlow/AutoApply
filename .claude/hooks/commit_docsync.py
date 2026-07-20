"""PostToolUse(Bash) hook: after a real git commit, ask the agent to dispatch a
doc-sync subagent seeded with the commit message.

Detection is text-independent: rather than parse the Bash command (fragile —
heredocs, echoes, and test payloads that merely mention "git commit" would
false-trigger), the hook tracks HEAD in a per-repo marker file and fires only
when HEAD has advanced to a brand-new commit stacked on the previously seen
HEAD. Resets/checkouts/amends silently re-sync the marker without firing. The
hook never edits docs itself.
"""

import hashlib
import json
import os
import pathlib
import subprocess
import sys

INSTRUCTION = (
    "A git commit just landed: {subject}\n\n"
    "Dispatch a documentation-sync subagent now via the Agent tool "
    "(subagent_type: general-purpose, run_in_background: false). Do NOT update "
    "docs yourself. Give the subagent the commit context (`git show --stat HEAD` "
    "and the full message), and task it to: update .claude/TODO.md to reflect "
    "what this commit completed/changed, and sync any docs the commit affects "
    "(.claude/CLAUDE.md routing, docs/ARCHITECTURE.md, the relevant CONTEXT.md "
    "files) per the merge-to-main doc-sync conventions. Relay only the "
    "subagent's summary back."
)


def _git(*args: str) -> str:
    try:
        r = subprocess.run(
            ["git", *args], capture_output=True, text=True, timeout=8
        )
    except Exception:
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def _marker() -> pathlib.Path:
    key = hashlib.sha1(os.getcwd().encode()).hexdigest()[:12]
    return pathlib.Path(os.path.expanduser("~/.claude")) / f".commit-docsync-{key}"


def _is_docs_only(head: str) -> bool:
    """True when every file the commit touched is itself one of the docs the
    sync subagent would update. Such a commit is the doc-sync — re-dispatching a
    subagent for it just loops, so the hook stays quiet."""
    files = _git("show", "--pretty=", "--name-only", head).splitlines()
    files = [f.strip() for f in files if f.strip()]
    if not files:
        return False  # no diff resolved — don't suppress, let it fire
    for f in files:
        if f in (".claude/TODO.md", ".claude/CLAUDE.md", "docs/ARCHITECTURE.md"):
            continue
        if f.endswith("CONTEXT.md"):
            continue
        return False  # a non-doc file was touched → real change, fire
    return True


def main() -> int:
    # Drain stdin (payload unused) so the writer never sees a broken pipe.
    try:
        sys.stdin.read()
    except Exception:
        pass

    head = _git("rev-parse", "HEAD")
    if not head:
        return 0  # not a git repo / no commits yet

    marker = _marker()
    prev = ""
    if marker.exists():
        try:
            prev = marker.read_text().strip()
        except Exception:
            prev = ""
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(head)
    except Exception:
        pass

    if not prev or head == prev:
        return 0  # bootstrap, or HEAD unchanged

    # Fire only when HEAD is a NEW commit whose ancestry includes the prior HEAD
    # (a normal commit or merge), not a reset/checkout to an unrelated ref.
    parents = _git("rev-list", "--parents", "-n", "1", "HEAD").split()[1:]
    if prev not in parents:
        return 0

    # A commit that only edits the sync-target docs IS the doc-sync — skip it so
    # TODO/CONTEXT tweaks don't trigger a self-referential subagent loop.
    if _is_docs_only(head):
        return 0

    subject = _git("log", "-1", "--pretty=%s") or "(no subject)"
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": INSTRUCTION.format(subject=subject),
        }
    }
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
