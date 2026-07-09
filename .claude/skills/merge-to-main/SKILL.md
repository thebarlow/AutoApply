---
name: merge-to-main
description: Use when merging or integrating a feature branch into `main` in the auto-apply project (including the finishing-a-development-branch flow). Enforces a documentation-sync gate so CLAUDE.md, ARCHITECTURE.md, and affected CONTEXT.md files reflect the merged change before it lands.
---

# Merging to Main

A change is not done until the docs describe it. Before any merge to `main` completes, sync the project documentation to the change. This runs **in addition to** the mechanics of `superpowers:finishing-a-development-branch` (test verify → merge → push → cleanup) — treat it as a required gate, not an optional polish step.

## The Rule

**Before finalizing a merge to `main`, update the documentation as necessary:**

1. **`CLAUDE.md`** (project root) — the routing table and rules. Update when the change adds/removes/moves a module, router, table, or subsystem, or changes how work is routed. Example: a new DB table must appear in the `db/` routing row.
2. **`ARCHITECTURE.md`** (project root) — top-level structure. Update when the change adds/removes a major module or model, changes a data-flow, or is release-worthy (per global CLAUDE.md, ARCHITECTURE.md is updated as part of a release). Keep it top-level; don't inline incremental detail.
3. **Affected `CONTEXT.md` files** — every subdirectory the change touched that has (or should have) a `CONTEXT.md`. Update the per-file routing tables, endpoint lists, known-issues, and any prose the change invalidated. Create one if a touched directory lacks it.

"As necessary" means: if the change touched a subsystem, the doc that describes that subsystem is in scope. A pure-internal refactor with no structural/interface change may need no doc edits — but you must consciously check, not skip.

## Checklist (run before the merge commit / push)

- [ ] Did this change add, remove, or rename a **table / model**? → update `CLAUDE.md` db row + `ARCHITECTURE.md` model list + `db/CONTEXT.md`.
- [ ] Add, remove, or move a **router / endpoint**? → update `web/CONTEXT.md` endpoint table (delete rows for removed endpoints) + `CLAUDE.md` routing table if the routing changed.
- [ ] Add or retire a **module / major component**? → `ARCHITECTURE.md` + the relevant `CONTEXT.md` + `CLAUDE.md` routing table.
- [ ] Change a **cross-cutting contract** (auth seam, tenancy, metering, document pipeline)? → the owning `CONTEXT.md` + `ARCHITECTURE.md`.
- [ ] Remove **dead code / endpoints**? → delete their doc rows so the docs don't reference things that no longer exist.
- [ ] Grep the docs for names the change removed (`grep -rn "<removed-name>" CLAUDE.md ARCHITECTURE.md **/CONTEXT.md`) — no stale references should remain.
- [ ] Mark the corresponding `TODO.md` item done if the change closes one.

## Integration

- This gate sits inside the merge flow. When using `superpowers:finishing-a-development-branch`, run this doc-sync **after tests pass and before the merge/push completes**, so the doc updates land in the same integration.
- Doc-only fixups discovered after a merge are still valid — apply them promptly rather than deferring.
- Spec/plan docs under `docs/superpowers/` are gitignored by project convention; they are NOT a substitute for updating the tracked `CLAUDE.md` / `ARCHITECTURE.md` / `CONTEXT.md` files.
