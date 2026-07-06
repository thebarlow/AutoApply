# Onboarding Guided Tour — Design

**Date:** 2026-07-06
**Status:** Approved (design), pending implementation plan
**Sub-project:** (4) Onboarding UX rework — this spec covers the guided-tour piece only.

## Problem

A brand-new hosted user signs in, completes (or skips) the résumé-upload wizard, and lands
on the dashboard with an empty job inbox and no guidance. This is the "what do I do now?"
moment — the single weakest part of first-run. The rest of sub-project 4's original scope is
already built: the LLM API-key step is gone (platform owns the key), credits/buy-flow exist in
the navbar, and a manual job-paste path (`UploadModal` → `POST /api/scraper/stage-job`) already
ingests + auto-scores jobs.

## Goal

An interactive product tour that teaches the app via spotlight-highlighted stops with popover
explanations. It runs once for new users after the résumé step, splits into two parts gated on
the user adding their first job, is skippable at any point, and is replayable from the Help menu.

## Non-goals (scope boundary)

- Does **not** change résumé-parse quality, the parse preview/edit flow, or the résumé wizard
  itself (beyond launching the tour when it finishes).
- Does **not** change credits gating/metering logic or the buy-credits flow — the tour only
  *points at* the existing credit balance.
- Does **not** redesign the empty-inbox visual state beyond what the tour highlights.

## Approach

**Library:** `react-joyride` (the standard React product-tour library) in **controlled mode**,
so our own state drives step index and the Part 1 → pause → Part 2 gating. Spotlight overlay,
tooltip positioning, and scroll-into-view are handled by the library. Styled to the existing
dark/purple theme.

**Targeting:** stops target stable `data-tour="<id>"` attributes added to ~11 elements, NOT
existing CSS classes — so the tour survives styling changes.

## Flow & State Machine

Durable tour state lives on the backend (profile/account), because Part 2 may occur in a later
session (upload résumé today, add a job next week). States:

```
unstarted → part1_done → completed
                       ↘ skipped   (terminal; reachable from any point)
```

Transitions:

1. **First sign-in.** The existing résumé `Wizard` shows unchanged. On finish OR skip, if tour
   state is `unstarted`, **Part 1 launches** (stops 1–7: profile arc + inbox + add-a-job).
2. **End of Part 1** → state set to `part1_done`. Tour pauses (no more stops shown).
3. **User adds their first job.** App detects `part1_done` AND the job count transitions 0→1 →
   **Part 2 launches** (stops 8–11) → on completion, state set to `completed`.
4. **Skip** (any point, either part) → state set to `skipped`; the tour never auto-runs again.
5. **Replay** (Help menu → "Take a tour") → runs the full 11-stop sequence regardless of stored
   state. Stops whose target elements don't exist (e.g. no job in the inbox) are skipped
   gracefully. Replay does NOT downgrade a `completed`/`skipped` flag to a partial state.

## Tour Stops

**Arc A — Profile (auto-runs right after résumé upload):**

1. **Profile overview** — "Here's your profile, built from your résumé. Check that everything
   parsed correctly."
2. **Sections & the tree** — "Your résumé is a tree of sections (Experience, Education, Skills…).
   Rename, reorder, add, or remove them."
3. **Lock / visibility** — "Lock a section to keep its wording verbatim, or hide it from generated
   documents."
4. **Custom prompts** — "Give a section or item a prompt to steer how the AI writes it — baseline
   facts, what to emphasize, what not to claim."
5. **Output format & theme** — "Choose bullets vs. paragraphs per field, and pick a résumé theme."

**Arc B — Dashboard / applying (6–7 auto-run after Arc A; 8–11 gated on a real job):**

6. **Job inbox** — "Your jobs live here. It's empty — let's add one."
7. **Add-a-job** — "Paste a posting to add it manually." *(Part 1 ends here.)*
8. **Scoring** — "Jobs auto-score against your profile so you know if they're worth pursuing."
9. **Generate** — "Generate a tailored résumé + cover letter for a job."
10. **Document modal / preview** — "Review, edit, and refine with live PDF preview."
11. **Credits** — "Generating costs credits; here's your balance and where to buy more."

Copy above is the baseline; refine per stop during implementation. Keep each popover concise.

## Components

### Backend
- **Migration:** add an `onboarding_tour` column (enum/string: `unstarted` default,
  `part1_done`, `completed`, `skipped`) to the profile/account table (decide which during
  planning — mirror how `setup-status` fields are sourced). Alembic revision.
- **Read:** extend `GET /api/setup-status` to include `onboarding_tour` (avoids a second
  round-trip; the frontend already loads setup status on boot).
- **Write:** `PATCH /api/onboarding/tour` accepting the new state; validates the transition is
  legal (no `completed` → `part1_done` downgrade), tenant-scoped via the existing
  `current_profile_id` seam.

### Frontend
- **`useOnboardingTour` hook** — reads tour state from setup-status; owns run flag, current part,
  and step index; exposes `advance`, `skip`, `finish`, and `run({ replay })`; persists transitions
  via the PATCH endpoint. Drives react-joyride in controlled mode.
- **Tour mount** — a single `<Joyride>` instance mounted in `App.jsx` (authed shell), themed to
  the dark/purple palette, with the Part 1 and Part 2 step arrays.
- **`data-tour` targets** — add `data-tour="<id>"` attributes to the ~11 target elements: profile
  tree root, a section node, lock/visibility control, prompt-edit control, output-format/theme
  control, job inbox, add-job button, a job card's score, the generate button, the document
  modal/preview, the navbar credit balance.
- **Part 2 trigger** — watch the job list; when tour state is `part1_done` and job count
  transitions 0→1, launch Part 2.
- **Help menu** — add a **"Take a tour"** item that calls `run({ replay: true })`.

## Testing

- **Backend:** endpoint + migration unit tests — legal transitions, illegal-transition rejection,
  tenant scoping, `setup-status` includes the field.
- **Frontend:** `useOnboardingTour` state-machine tests (`unstarted → part1_done → completed`,
  skip from either part, replay does not downgrade); Help-menu button triggers replay; assert the
  `data-tour` target attributes are present on their host components. react-joyride's own overlay
  rendering is mocked/shallow — we test our orchestration, not the library internals.

## Open questions for the plan (not blocking)

- Exact home of the `onboarding_tour` column (account vs user_profile) — resolve against how the
  session seam and `setup-status` currently source their data.
- Whether stop 5 (output format & theme) stays a distinct stop or folds into stop 4 if the tour
  feels long in practice.
