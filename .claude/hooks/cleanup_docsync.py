"""UserPromptSubmit hook: when the user asks to "clean up", ask the agent to
summarize what changed and dispatch a doc-sync subagent.

Stays silent (exit 0, no output) unless the submitted prompt contains a
clean-up phrase. The hook never edits docs itself; it only injects an
instruction for the main agent.
"""

import json
import re
import sys

TRIGGER = re.compile(r"clean[\s-]?up", re.IGNORECASE)

INSTRUCTION = (
    "The user asked to clean up. First gather a brief summary of what changed "
    "this session (`git status --porcelain` and `git diff --stat HEAD`). Then "
    "dispatch a documentation-sync subagent via the Agent tool (subagent_type: "
    "general-purpose, run_in_background: false). Do NOT update docs yourself. "
    "Give the subagent your change summary and task it to: update .claude/TODO.md "
    "to reflect completed/changed/halted work, and sync any affected docs "
    "(.claude/CLAUDE.md routing, docs/ARCHITECTURE.md, relevant CONTEXT.md) per "
    "the merge-to-main doc-sync conventions. Relay only the subagent's summary."
)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    prompt = payload.get("prompt", "") or ""
    if not TRIGGER.search(prompt):
        return 0
    out = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": INSTRUCTION,
        }
    }
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
