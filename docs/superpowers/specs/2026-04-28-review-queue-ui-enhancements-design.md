# Review Queue UI Enhancements

**Date:** 2026-04-28  
**Status:** Approved

## Overview

Add three missing pieces to the review queue job cards: a link to the original posting, an expandable description preview, and a remote badge. Also remove a dead `employment_type` reference that has never been populated.

## Files Changed

| File | Change |
|---|---|
| `web/routers/jobs.py` | Add `url`, `description`, `remote` to `_serialize()` |
| `web/static/index.html` | Update `buildCard()` — link icon, description block, remote pill, drop `employment_type` |
| `web/static/style.css` | Styles for description clamp, expand toggle, remote badge |

## API Changes

`_serialize()` in `web/routers/jobs.py` currently omits `url`, `description`, and `remote`. All three exist on the `Job` model and must be added to the serialized response.

## Card Layout

Top to bottom:

1. **Actions row** — Approve / Reject buttons (unchanged)
2. **Header** — job title + final score + external link icon (opens `url` in new tab)
3. **Meta** — company · location
4. **Detail** — salary · posted_at (`employment_type` removed — field not collected by scrapers)
5. **Pills** — Desirability · Fit · Remote (Remote pill only rendered if `remote === true`)
6. **Description** — 3-line clamp via CSS `-webkit-line-clamp: 3`; "Read more" / "Show less" toggle below; toggle implemented as a JS class swap (`.expanded`) on the description element
7. **Justification** — desirability and fit text blocks
8. **Feedback area** — inline action feedback (unchanged)

## Description Expand Behavior

- Default state: description clamped to 3 lines, "Read more" link visible below
- Expanded state: clamp removed, "Show less" link visible
- Implemented via a CSS class toggle — no text swapping, no re-render
- Cards with no description: description block not rendered

## Remote Badge

- Rendered as a pill in the pills row, styled distinctly (e.g., blue tint)
- Only shown when `job.remote === true`
- Not shown when `remote` is `null` or `false`

## Removed

- `employment_type` reference in `buildCard()` — field not present on `Job` model and not collected by either scraper. Tracked as a future scraper enhancement in `1_scraper/CONTEXT.md`.
