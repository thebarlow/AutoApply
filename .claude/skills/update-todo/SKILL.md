---
name: update-todo
description: Use in the auto-apply project whenever you finish a task, change the direction or scope of the work you're doing, or stop/halt work before a task is complete — so TODO.md always reflects the real state of the backlog. Trigger on "done", "that works", "let's do X instead", "actually, drop that", handing off, or ending a session mid-task.
---

# Keeping .claude/TODO.md Current

`.claude/TODO.md` is the multi-session source of truth for what's planned, in progress, and done. It is only useful if it matches reality. Whenever the state of the work changes, update it in the same turn — before moving on, not "later."

## When to Update (the three triggers)

1. **Task completed** — an item (or a checkbox sub-item) is finished and verified.
   - Mark it `[x]`, add a one-line result note (what shipped, where, commit/date if known), and move fully-done top-level items toward the **Done** section as the surrounding entries do.
2. **Direction / scope change** — you (or the user) decided to do something different, split an item, add a new item, drop one, or re-sequence.
   - Revise the item's scope notes inline, add the new item, or strike the abandoned approach. Record *why* the direction changed in one line so the next session isn't confused.
3. **Halting before completion** — the session ends, you hand off, or you stop an item mid-flight without finishing it.
   - Leave the item `[ ]` but append a **status note**: what's done so far, what's left, and any blocker. Never leave a half-done item looking untouched.

## The Rule

**A work-state change is not complete until TODO.md reflects it.** Update in the same turn the change happens — do not batch it for the end of the session, and do not assume the user will do it.

- Matching an existing entry's format beats inventing a new one — mirror the checkbox/notes style already in that section.
- Editing an existing item is preferred over adding a duplicate. Search TODO.md for the item first.
- If the change touches something with no TODO.md entry and it's multi-session-relevant, add one. Trivial one-turn fixes with no backlog relevance don't need an entry.
- If genuinely nothing in TODO.md is affected, say so explicitly ("no TODO.md change needed — this wasn't tracked") rather than silently skipping.

## Pruning Old Items

TODO.md is a working backlog, not an archive — git history is the archive. Whenever you update the file (any of the three triggers), also scan for staleness and prune in the same edit:

- **Done items**: keep only the most recent few (roughly the last ~2 weeks or ~10 entries) in the **Done** section as context for ongoing work. Delete older done entries outright — their commits and one-line results live in git history.
- **Superseded / abandoned items**: if an open item was made irrelevant by a later decision or shipped feature, delete it (or fold a one-line "superseded by X" into the surviving item) rather than leaving it open.
- **Long-dormant items**: an open item untouched for over a month either still matters (leave it, but re-check its notes are accurate) or it doesn't (delete it). Ask the user only if you genuinely can't tell.
- Never prune in-progress items or their status notes.

| Excuse | Reality |
|--------|---------|
| "I'll update TODO.md at the end" | End-of-session updates get dropped when context runs out. Update now. |
| "The user can mark it done" | Your job is to keep it current; don't offload it. |
| "It's obvious it's done" | Obvious to you now ≠ obvious to next session. Write it down. |
| "I only halted, didn't finish" | Halting mid-task is exactly trigger #3 — leave a status note. |
| "We changed our minds, no need to record" | Direction changes are trigger #2 — record the what and the why. |
| "It's a small change" | If it's tracked in TODO.md, update it. If it's not tracked and matters, add it. |

## Red Flags — STOP and update TODO.md

- About to say "done", "that's working", "shipped", "verified" → mark the item `[x]`.
- About to say "let's do X instead", "actually drop that", "new plan" → revise scope + record why.
- Ending your turn on an unfinished task, or the user is wrapping up → leave a status note.
- Committing work that closes or advances a TODO item → update the item in or before that commit.
