# Onboarding Guided Tour Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an interactive react-joyride product tour that runs once after résumé upload, splits into two parts gated on the user adding their first job, is skippable, and is replayable from the navbar Help area.

**Architecture:** Durable tour state (`unstarted → part1_done → completed`, plus terminal `skipped`) is stored in the `user_profile.data` JSON blob (no migration — mirrors `resume_theme`), read via the existing `GET /api/setup-status`, and written via a new `PATCH /api/onboarding/tour`. The frontend adds a `useOnboardingTour` hook driving a single controlled `<Joyride>` instance mounted in `App.jsx`; step targets are stable `data-tour="<id>"` attributes on ~11 elements. The tour opens the profile editor / document modal for the relevant stops by dispatching the app's existing `auto-apply:*` CustomEvents.

**Tech Stack:** React 18.3, react-joyride ^2.9, react-router-dom v7, Vitest + @testing-library/react + jsdom; FastAPI, SQLAlchemy, pytest.

## Global Constraints

- Store tour state in `user_profile.data` JSON (key `onboarding_tour`), NOT a new column. Default `"unstarted"`.
- Legal states: `unstarted`, `part1_done`, `completed`, `skipped`. The PATCH endpoint must reject illegal transitions (any move OUT of a terminal `completed`/`skipped` to `part1_done`/`unstarted`), returning HTTP 409.
- All new backend endpoints are tenant-scoped via `current_profile_id` (the tenancy seam) — never the legacy dev stub.
- Frontend tests: `import { describe, it, expect, vi } from 'vitest'`; `render`/`screen` from `@testing-library/react`; jest-dom matchers are globally set up.
- Run FE tests from `react-dashboard/`: `npm run test`. Run backend tests from repo root: `pytest`.
- Reuse existing Tailwind space tokens (`space-bg`, `space-card`, `space-border`, `space-accent`, `space-text`, `space-dim`, `purple-*`). No new theme entries.
- The tour never auto-runs for a user who did not just finish/skip the résumé wizard (existing résumé'd users are untouched until they click "Take a tour").
- Commit format: `[type] Imperative subject` (types: feat, fix, refactor, docs, test, chore). No Claude/Anthropic attribution.

---

### Task 1: Backend — tour state persistence + read/write endpoints

**Files:**
- Modify: `core/user.py` (`_hydrate` ~L164, `_to_dict` ~L196)
- Modify: `web/routers/setup_status.py` (add tour state to the payload)
- Create: `web/routers/onboarding.py` (the PATCH endpoint)
- Modify: `web/main.py` (register the new router, near L175)
- Test: `tests/web/test_onboarding_tour.py`

**Interfaces:**
- Consumes: `User.load(db, profile_id)` / `user.save(db)` (existing); `current_profile_id` dependency (existing, from `web.tenancy`).
- Produces:
  - `User.onboarding_tour: str` instance attribute (hydrated from / serialized to `data` JSON).
  - `GET /api/setup-status` response gains `"onboarding_tour": <str>`.
  - `PATCH /api/onboarding/tour` — body `{"state": "<one of the 4>"}`, returns `{"onboarding_tour": "<state>"}` on success, 422 for an unknown state, 409 for an illegal transition.
  - Module constant `web/routers/onboarding.py::_LEGAL = {"unstarted","part1_done","completed","skipped"}` and helper `_is_legal_transition(old, new) -> bool`.

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_onboarding_tour.py
"""Tests for onboarding tour state persistence + endpoints."""
from fastapi.testclient import TestClient

from web.main import app
from web.tenancy import current_profile_id
from core.user import User
from db.database import get_db


def _client(db_session, profile_id):
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[current_profile_id] = lambda: profile_id
    return TestClient(app)


def test_default_state_is_unstarted(db_session, seeded_profile):
    client = _client(db_session, seeded_profile.id)
    body = client.get("/api/setup-status").json()
    assert body["onboarding_tour"] == "unstarted"
    app.dependency_overrides.clear()


def test_patch_advances_state_and_persists(db_session, seeded_profile):
    client = _client(db_session, seeded_profile.id)
    r = client.patch("/api/onboarding/tour", json={"state": "part1_done"})
    assert r.status_code == 200
    assert r.json()["onboarding_tour"] == "part1_done"
    # reload from DB to confirm persistence
    reloaded = User.load(db_session, seeded_profile.id)
    assert reloaded.onboarding_tour == "part1_done"
    app.dependency_overrides.clear()


def test_patch_rejects_unknown_state(db_session, seeded_profile):
    client = _client(db_session, seeded_profile.id)
    r = client.patch("/api/onboarding/tour", json={"state": "banana"})
    assert r.status_code == 422
    app.dependency_overrides.clear()


def test_patch_rejects_downgrade_from_terminal(db_session, seeded_profile):
    client = _client(db_session, seeded_profile.id)
    client.patch("/api/onboarding/tour", json={"state": "completed"})
    r = client.patch("/api/onboarding/tour", json={"state": "part1_done"})
    assert r.status_code == 409
    app.dependency_overrides.clear()
```

Note on fixtures: this repo already has pytest fixtures for a DB session and a seeded profile. If `db_session` / `seeded_profile` fixtures do not exist under `tests/`, add them to `tests/conftest.py` mirroring the setup used by the nearest existing `tests/web/test_*.py` (find one with `grep -rl "current_profile_id" tests/`). Reuse, do not reinvent, the existing session/profile factory.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/web/test_onboarding_tour.py -v`
Expected: FAIL — `KeyError: 'onboarding_tour'` / 404 on the PATCH route (endpoint not registered).

- [ ] **Step 3: Persist the field on the model**

In `core/user.py` `_hydrate`, after the `resume_theme` line (~L164) add:

```python
        # Onboarding tour progress — see web/routers/onboarding.py
        self.onboarding_tour: str = raw.get("onboarding_tour") or "unstarted"
```

In `core/user.py` `_to_dict`, after the `d["resume_theme"] = self.resume_theme` line (~L196) add:

```python
        d["onboarding_tour"] = self.onboarding_tour
```

- [ ] **Step 4: Expose it on setup-status**

In `web/routers/setup_status.py`, add a helper and include it in the response:

```python
def _tour_state(db: Session, profile_id: int) -> str:
    """Return the caller's onboarding tour state (default 'unstarted')."""
    row = db.query(User).filter_by(id=profile_id).first()
    if row is None:
        return "unstarted"
    data = json.loads(row.data) if row.data else {}
    return data.get("onboarding_tour") or "unstarted"
```

Then in `get_setup_status`, add the key to the returned dict:

```python
    return {
        "llm_configured": _has_configured_llm_provider(db),
        "resume_parsed": _has_parsed_resume(db, profile_id),
        "onboarding_tour": _tour_state(db, profile_id),
    }
```

- [ ] **Step 5: Add the PATCH endpoint**

Create `web/routers/onboarding.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.user import User
from db.database import get_db
from web.tenancy import current_profile_id

router = APIRouter()

_LEGAL = {"unstarted", "part1_done", "completed", "skipped"}
_TERMINAL = {"completed", "skipped"}


def _is_legal_transition(old: str, new: str) -> bool:
    """Reject moving out of a terminal state back to an in-progress one."""
    if old in _TERMINAL and new in {"unstarted", "part1_done"}:
        return False
    return True


class TourUpdate(BaseModel):
    state: str


@router.patch("/api/onboarding/tour")
def set_tour_state(
    body: TourUpdate,
    db: Session = Depends(get_db),
    profile_id: int = Depends(current_profile_id),
) -> dict[str, str]:
    """Persist the caller's onboarding tour progress."""
    if body.state not in _LEGAL:
        raise HTTPException(status_code=422, detail=f"Unknown tour state: {body.state}")
    user = User.load(db, profile_id)
    if not _is_legal_transition(user.onboarding_tour, body.state):
        raise HTTPException(status_code=409, detail="Illegal tour state transition")
    user.onboarding_tour = body.state
    user.save(db)
    return {"onboarding_tour": user.onboarding_tour}
```

Register it in `web/main.py` alongside the other routers (near L175):

```python
from web.routers import onboarding  # near the other `from web.routers import ...`
# ...
app.include_router(onboarding.router)  # near app.include_router(setup_status.router)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/web/test_onboarding_tour.py -v`
Expected: PASS (4 tests).

- [ ] **Step 7: Commit**

```bash
git add core/user.py web/routers/setup_status.py web/routers/onboarding.py web/main.py tests/web/test_onboarding_tour.py
git commit -m "[feat] Persist onboarding tour state + read/write endpoints"
```

---

### Task 2: Frontend — api client + `useOnboardingTour` state-machine hook

**Files:**
- Modify: `react-dashboard/src/api.js` (add `setTourState`)
- Modify: `react-dashboard/src/hooks/usePrerequisites.js` (surface `onboardingTour` + `refresh` already exists)
- Create: `react-dashboard/src/hooks/useOnboardingTour.js`
- Test: `react-dashboard/src/hooks/useOnboardingTour.test.jsx`

**Interfaces:**
- Consumes: `getSetupStatus()` (existing, returns `{ llm_configured, resume_parsed, onboarding_tour }`); `setTourState(state)` (new).
- Produces:
  - `api.js`: `export const setTourState = (state) => _fetch('/api/onboarding/tour', { method:'PATCH', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ state }) })`.
  - `usePrerequisites`: state gains `onboardingTour` (string; defaults `'unstarted'`).
  - `useOnboardingTour({ tourState, jobCount, onStateChange })` returns
    `{ run: bool, part: 1|2|null, launchPart1(), launchPart2(), replay(), finishPart1(), finishTour(), skip() }`.
    - `launchPart1()` sets `run=true, part=1`.
    - `finishPart1()` → calls `onStateChange('part1_done')` and sets `run=false, part=null`.
    - `launchPart2()` sets `run=true, part=2`.
    - `finishTour()` → `onStateChange('completed')`, `run=false, part=null`.
    - `skip()` → `onStateChange('skipped')`, `run=false, part=null`.
    - `replay()` sets `run=true, part=1` WITHOUT changing stored state (it drives both parts back-to-back locally; `finishTour` on a replay still calls `onStateChange('completed')`, which the backend accepts as a no-op-legal transition from `completed`).

- [ ] **Step 1: Write the failing test**

```jsx
// react-dashboard/src/hooks/useOnboardingTour.test.jsx
import { describe, it, expect, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useOnboardingTour } from './useOnboardingTour'

describe('useOnboardingTour', () => {
  it('starts idle', () => {
    const { result } = renderHook(() =>
      useOnboardingTour({ tourState: 'unstarted', jobCount: 0, onStateChange: vi.fn() }))
    expect(result.current.run).toBe(false)
    expect(result.current.part).toBe(null)
  })

  it('launchPart1 runs part 1', () => {
    const { result } = renderHook(() =>
      useOnboardingTour({ tourState: 'unstarted', jobCount: 0, onStateChange: vi.fn() }))
    act(() => result.current.launchPart1())
    expect(result.current.run).toBe(true)
    expect(result.current.part).toBe(1)
  })

  it('finishPart1 persists part1_done and stops', () => {
    const onStateChange = vi.fn()
    const { result } = renderHook(() =>
      useOnboardingTour({ tourState: 'unstarted', jobCount: 0, onStateChange }))
    act(() => result.current.launchPart1())
    act(() => result.current.finishPart1())
    expect(onStateChange).toHaveBeenCalledWith('part1_done')
    expect(result.current.run).toBe(false)
  })

  it('finishTour persists completed', () => {
    const onStateChange = vi.fn()
    const { result } = renderHook(() =>
      useOnboardingTour({ tourState: 'part1_done', jobCount: 1, onStateChange }))
    act(() => result.current.launchPart2())
    act(() => result.current.finishTour())
    expect(onStateChange).toHaveBeenCalledWith('completed')
    expect(result.current.run).toBe(false)
  })

  it('skip persists skipped', () => {
    const onStateChange = vi.fn()
    const { result } = renderHook(() =>
      useOnboardingTour({ tourState: 'unstarted', jobCount: 0, onStateChange }))
    act(() => result.current.launchPart1())
    act(() => result.current.skip())
    expect(onStateChange).toHaveBeenCalledWith('skipped')
    expect(result.current.run).toBe(false)
  })

  it('replay runs without changing stored state until finish', () => {
    const onStateChange = vi.fn()
    const { result } = renderHook(() =>
      useOnboardingTour({ tourState: 'completed', jobCount: 2, onStateChange }))
    act(() => result.current.replay())
    expect(result.current.run).toBe(true)
    expect(result.current.part).toBe(1)
    expect(onStateChange).not.toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `react-dashboard/`): `npm run test -- useOnboardingTour`
Expected: FAIL — cannot resolve `./useOnboardingTour`.

- [ ] **Step 3: Write the hook**

```jsx
// react-dashboard/src/hooks/useOnboardingTour.js
import { useCallback, useState } from 'react'

export function useOnboardingTour({ tourState, jobCount, onStateChange }) {
  const [run, setRun] = useState(false)
  const [part, setPart] = useState(null)

  const launchPart1 = useCallback(() => { setPart(1); setRun(true) }, [])
  const launchPart2 = useCallback(() => { setPart(2); setRun(true) }, [])

  const finishPart1 = useCallback(() => {
    setRun(false); setPart(null); onStateChange('part1_done')
  }, [onStateChange])

  const finishTour = useCallback(() => {
    setRun(false); setPart(null); onStateChange('completed')
  }, [onStateChange])

  const skip = useCallback(() => {
    setRun(false); setPart(null); onStateChange('skipped')
  }, [onStateChange])

  // Replay from the Help area: run part 1 immediately without persisting a
  // downgrade; the eventual finishTour writes 'completed' (a legal no-op).
  const replay = useCallback(() => { setPart(1); setRun(true) }, [])

  return { run, part, launchPart1, launchPart2, finishPart1, finishTour, skip, replay,
           tourState, jobCount }
}
```

- [ ] **Step 4: Add the api client + prereqs field**

In `react-dashboard/src/api.js` add near the other exports:

```js
export const setTourState = (state) =>
  _fetch('/api/onboarding/tour', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ state }),
  })
```

In `react-dashboard/src/hooks/usePrerequisites.js`, add `onboardingTour` to the state object set in `refresh`:

```js
      setState({
        llmReady: !!data.llm_configured,
        resumeReady: !!data.resume_parsed,
        onboardingTour: data.onboarding_tour || 'unstarted',
        loaded: true,
        error: null,
      });
```

and add `onboardingTour: 'unstarted'` to the initial `useState({...})` default.

- [ ] **Step 5: Run test to verify it passes**

Run (from `react-dashboard/`): `npm run test -- useOnboardingTour`
Expected: PASS (6 tests).

- [ ] **Step 6: Commit**

```bash
git add react-dashboard/src/hooks/useOnboardingTour.js react-dashboard/src/hooks/useOnboardingTour.test.jsx react-dashboard/src/api.js react-dashboard/src/hooks/usePrerequisites.js
git commit -m "[feat] Add useOnboardingTour hook + tour-state api client"
```

---

### Task 3: Install react-joyride + tour step definitions module

**Files:**
- Modify: `react-dashboard/package.json` (add dependency)
- Create: `react-dashboard/src/components/Onboarding/tourSteps.js`
- Test: `react-dashboard/src/components/Onboarding/tourSteps.test.js`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces:
  - `export const PART1_STEPS` — array of react-joyride step objects (stops 1–7).
  - `export const PART2_STEPS` — array of react-joyride step objects (stops 8–11).
  - Each step: `{ target: '[data-tour="<id>"]', content: '<string>', placement, disableBeacon: true, openEvent?: '<auto-apply:* event name>' }`. `openEvent` is a CUSTOM field (ignored by joyride) the controller uses to open the profile editor / document modal before that step.
  - `data-tour` ids used (consumed by Task 4): `profile-tree`, `profile-section`, `section-lock`, `section-prompt`, `output-format`, `job-inbox`, `add-job`, `job-score`, `generate`, `document-preview`, `credit-balance`.

- [ ] **Step 1: Install react-joyride**

Run (from `react-dashboard/`): `npm install react-joyride@^2.9.3`
Expected: `package.json` dependencies gain `"react-joyride": "^2.9.3"`; `package-lock.json` updated.

- [ ] **Step 2: Write the failing test**

```js
// react-dashboard/src/components/Onboarding/tourSteps.test.js
import { describe, it, expect } from 'vitest'
import { PART1_STEPS, PART2_STEPS } from './tourSteps'

describe('tourSteps', () => {
  it('part 1 covers profile arc + inbox + add-job (7 stops)', () => {
    expect(PART1_STEPS).toHaveLength(7)
    const targets = PART1_STEPS.map((s) => s.target)
    expect(targets).toContain('[data-tour="profile-tree"]')
    expect(targets).toContain('[data-tour="add-job"]')
  })

  it('part 2 covers scoring → generate → preview → credits (4 stops)', () => {
    expect(PART2_STEPS).toHaveLength(4)
    const targets = PART2_STEPS.map((s) => s.target)
    expect(targets).toEqual([
      '[data-tour="job-score"]',
      '[data-tour="generate"]',
      '[data-tour="document-preview"]',
      '[data-tour="credit-balance"]',
    ])
  })

  it('every step disables the beacon and has non-empty content', () => {
    for (const s of [...PART1_STEPS, ...PART2_STEPS]) {
      expect(s.disableBeacon).toBe(true)
      expect(typeof s.content).toBe('string')
      expect(s.content.length).toBeGreaterThan(0)
    }
  })
})
```

- [ ] **Step 3: Run test to verify it fails**

Run (from `react-dashboard/`): `npm run test -- tourSteps`
Expected: FAIL — cannot resolve `./tourSteps`.

- [ ] **Step 4: Write the step definitions**

```js
// react-dashboard/src/components/Onboarding/tourSteps.js
// react-joyride step configs. `openEvent` is a custom field (not read by
// joyride) that TourController dispatches to open the relevant panel/modal
// before the step is shown.

export const PART1_STEPS = [
  {
    target: '[data-tour="profile-tree"]',
    content:
      "Here's your profile, built from your résumé. Take a moment to check that everything parsed correctly.",
    placement: 'right',
    disableBeacon: true,
    openEvent: 'auto-apply:edit-profile',
  },
  {
    target: '[data-tour="profile-section"]',
    content:
      'Your résumé is a tree of sections — Experience, Education, Skills, and more. Rename, reorder, add, or remove them however you like.',
    placement: 'right',
    disableBeacon: true,
  },
  {
    target: '[data-tour="section-lock"]',
    content:
      'Lock a section to keep its wording exactly as written, or hide it from generated documents.',
    placement: 'right',
    disableBeacon: true,
  },
  {
    target: '[data-tour="section-prompt"]',
    content:
      'Give a section or item a prompt to steer how the AI writes it — the baseline facts, what to emphasize, and what never to claim.',
    placement: 'right',
    disableBeacon: true,
  },
  {
    target: '[data-tour="output-format"]',
    content:
      'Choose bullet points or paragraphs per field, and pick a résumé theme that suits you.',
    placement: 'right',
    disableBeacon: true,
  },
  {
    target: '[data-tour="job-inbox"]',
    content:
      "This is your job inbox — where every job you're working lives. It's empty right now, so let's add one.",
    placement: 'left',
    disableBeacon: true,
  },
  {
    target: '[data-tour="add-job"]',
    content:
      'Click here to paste a job posting and add it manually. Go ahead and add your first job — the tour picks back up once you do.',
    placement: 'bottom',
    disableBeacon: true,
  },
]

export const PART2_STEPS = [
  {
    target: '[data-tour="job-score"]',
    content:
      'Nice — your job is in. Each job is automatically scored against your profile so you know if it’s worth pursuing.',
    placement: 'left',
    disableBeacon: true,
  },
  {
    target: '[data-tour="generate"]',
    content:
      'Click here to generate a résumé and cover letter tailored to this specific job.',
    placement: 'left',
    disableBeacon: true,
  },
  {
    target: '[data-tour="document-preview"]',
    content:
      'Review, edit, and refine your documents here, with a live PDF preview side-by-side.',
    placement: 'left',
    disableBeacon: true,
    openEvent: 'auto-apply:open-document',
  },
  {
    target: '[data-tour="credit-balance"]',
    content:
      'Generating documents costs credits. Here’s your balance — and where to buy more when you run low. That’s the tour!',
    placement: 'bottom',
    disableBeacon: true,
  },
]
```

- [ ] **Step 5: Run test to verify it passes**

Run (from `react-dashboard/`): `npm run test -- tourSteps`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add react-dashboard/package.json react-dashboard/package-lock.json react-dashboard/src/components/Onboarding/tourSteps.js react-dashboard/src/components/Onboarding/tourSteps.test.js
git commit -m "[feat] Add react-joyride + onboarding tour step definitions"
```

---

### Task 4: Add `data-tour` target attributes to host elements

**Files:**
- Modify: `react-dashboard/src/components/widgets/ProfileDetail.jsx` (`profile-tree` on the tree container)
- Modify: `react-dashboard/src/components/widgets/profile-tree/TreeNode.jsx` (`profile-section` on a section node's root)
- Modify: `react-dashboard/src/components/widgets/profile-tree/structuralControls.jsx` (`section-lock` on the lock/visibility control group)
- Modify: `react-dashboard/src/components/widgets/profile-tree/PromptField.jsx` (`section-prompt` on the prompt-edit trigger)
- Modify: `react-dashboard/src/components/widgets/profile-tree/fieldWidgets.jsx` (`output-format` on the output-format/theme select)
- Modify: `react-dashboard/src/components/widgets/Pipeline.jsx` (`job-inbox` on the job list container ~L369, `add-job` on the `+ Upload` button ~L334)
- Modify: `react-dashboard/src/components/widgets/Settings.jsx` (`job-score` on the score readout, `generate` on the generate button, `document-preview` on the element that opens `DocumentModal`)
- Modify: `react-dashboard/src/components/widgets/CreditBalance.jsx` (`credit-balance` on the balance widget root)
- Test: `react-dashboard/src/components/Onboarding/tourTargets.test.jsx`

**Interfaces:**
- Consumes: the `data-tour` id list from Task 3.
- Produces: rendered DOM carrying `data-tour="<id>"` on each of the 11 anchor elements.

Implementation note: add ONLY the attribute — e.g. change `<div className="...">` to `<div data-tour="profile-tree" className="...">`. Do not restructure markup. Where a target element only renders conditionally (e.g. `add-job` shows only on the Inbox tab, `job-score`/`generate` only when a job is selected), that is fine — Part 1/Part 2 only run in contexts where the target exists (the controller handles missing targets gracefully, Task 5).

For each anchor pick the smallest stable element:
- `profile-tree`: the scrollable tree container in `ProfileDetail.jsx` that wraps the rendered `ProfileTreeEditor`.
- `profile-section`: the outer wrapper of a single section node in `TreeNode.jsx` (first rendered node is fine; the attribute may repeat — joyride targets the first match).
- `section-lock`: the lock/visibility button cluster in `structuralControls.jsx`.
- `section-prompt`: the "edit prompt" trigger (pencil / prompt button) in `PromptField.jsx`.
- `output-format`: the output-format `<select>` in `fieldWidgets.jsx`.
- `job-inbox`: the `<JobList>` wrapper `<div>` in `Pipeline.jsx` (~L368).
- `add-job`: the `+ Upload` `<button>` in `Pipeline.jsx` (~L334).
- `job-score`: the score badge/number element in the job detail view in `Settings.jsx`.
- `generate`: the résumé/cover generate `<button>` in `Settings.jsx`.
- `document-preview`: the control that opens `DocumentModal` (the ✎ pencil button) in `Settings.jsx`.
- `credit-balance`: the balance container root in `CreditBalance.jsx`.

- [ ] **Step 1: Write the failing test**

This test renders the two simplest, always-available anchors to prove the attribute convention works end-to-end without mounting the whole app. (The remaining anchors are verified by the manual QA in Task 6; unit-mounting every panel with a selected job is out of scope.)

```jsx
// react-dashboard/src/components/Onboarding/tourTargets.test.jsx
import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import CreditBalance from '../widgets/CreditBalance'

describe('tour targets', () => {
  it('CreditBalance carries data-tour="credit-balance"', () => {
    const { container } = render(<CreditBalance />)
    expect(container.querySelector('[data-tour="credit-balance"]')).not.toBeNull()
  })
})
```

If `CreditBalance` requires props/context to render, pass the minimal props its existing tests use (check `CreditBalance` usage in `Navbar`/`UserHome`); keep the assertion the same.

- [ ] **Step 2: Run test to verify it fails**

Run (from `react-dashboard/`): `npm run test -- tourTargets`
Expected: FAIL — no element matches `[data-tour="credit-balance"]`.

- [ ] **Step 3: Add the attributes**

Add each `data-tour="<id>"` attribute to the elements listed above. Example for `CreditBalance.jsx` — add to the widget's outermost element:

```jsx
    <div data-tour="credit-balance" className={/* existing classes unchanged */}>
```

Repeat for the other 10 anchors in their listed files.

- [ ] **Step 4: Run test to verify it passes**

Run (from `react-dashboard/`): `npm run test -- tourTargets`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
git add react-dashboard/src/components/widgets/ProfileDetail.jsx react-dashboard/src/components/widgets/profile-tree/TreeNode.jsx react-dashboard/src/components/widgets/profile-tree/structuralControls.jsx react-dashboard/src/components/widgets/profile-tree/PromptField.jsx react-dashboard/src/components/widgets/profile-tree/fieldWidgets.jsx react-dashboard/src/components/widgets/Pipeline.jsx react-dashboard/src/components/widgets/Settings.jsx react-dashboard/src/components/widgets/CreditBalance.jsx react-dashboard/src/components/Onboarding/tourTargets.test.jsx
git commit -m "[feat] Add data-tour target attributes for the onboarding tour"
```

---

### Task 5: TourController component + App wiring (auto-launch, gating, callbacks)

**Files:**
- Create: `react-dashboard/src/components/Onboarding/TourController.jsx`
- Modify: `react-dashboard/src/App.jsx` (mount controller; pass tour state, job count, wizard-finish trigger)
- Test: `react-dashboard/src/components/Onboarding/TourController.test.jsx`

**Interfaces:**
- Consumes: `useOnboardingTour` (Task 2), `PART1_STEPS`/`PART2_STEPS` (Task 3), `setTourState` (Task 2), `usePrerequisites().onboardingTour` (Task 2). react-joyride's `<Joyride>` default export + `STATUS`, `EVENTS`, `ACTIONS` named exports.
- Produces: `export default function TourController({ tourState, jobCount, refreshPrereqs })`. Renders one controlled `<Joyride>`. Behavior:
  - Listens for `window` event `auto-apply:tour-launch-part1` → `launchPart1()`.
  - Listens for `auto-apply:tour-replay` → `replay()`.
  - When `tourState === 'part1_done'` and `jobCount` transitions from 0 to ≥1 → `launchPart2()`.
  - Before a step with an `openEvent`, dispatches that event (`window.dispatchEvent(new CustomEvent(openEvent))`) so the profile editor / document modal opens.
  - On joyride callback: `SKIPPED`/close → `skip()`; part 1 `FINISHED` → `finishPart1()`; part 2 `FINISHED` → `finishTour()`; after any persist, call `refreshPrereqs()`.
  - Missing targets: pass `<Joyride>` prop `disableScrollParentFix` and rely on joyride skipping a step whose target is absent — but ALSO guard with `spotlightClicks={false}`. On a replay where a target is missing (no job), joyride emits a `target not found` error event; catch it in the callback and advance (`stepIndex + 1`) so the tour doesn't stall.

- [ ] **Step 1: Write the failing test**

```jsx
// react-dashboard/src/components/Onboarding/TourController.test.jsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, act } from '@testing-library/react'

// Mock react-joyride so tests assert our wiring, not the library's rendering.
let lastJoyrideProps = null
vi.mock('react-joyride', () => ({
  __esModule: true,
  default: (props) => { lastJoyrideProps = props; return null },
  STATUS: { FINISHED: 'finished', SKIPPED: 'skipped' },
  EVENTS: { STEP_AFTER: 'step:after', TARGET_NOT_FOUND: 'error:target_not_found' },
  ACTIONS: { CLOSE: 'close' },
}))

import TourController from './TourController'

beforeEach(() => { lastJoyrideProps = null })

describe('TourController', () => {
  it('launches part 1 on the launch event', () => {
    render(<TourController tourState="unstarted" jobCount={0} refreshPrereqs={vi.fn()} />)
    act(() => { window.dispatchEvent(new CustomEvent('auto-apply:tour-launch-part1')) })
    expect(lastJoyrideProps.run).toBe(true)
    expect(lastJoyrideProps.steps.length).toBe(7)
  })

  it('auto-launches part 2 when a job arrives after part1_done', () => {
    const { rerender } = render(
      <TourController tourState="part1_done" jobCount={0} refreshPrereqs={vi.fn()} />)
    expect(lastJoyrideProps.run).toBe(false)
    rerender(<TourController tourState="part1_done" jobCount={1} refreshPrereqs={vi.fn()} />)
    expect(lastJoyrideProps.run).toBe(true)
    expect(lastJoyrideProps.steps.length).toBe(4)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `react-dashboard/`): `npm run test -- TourController`
Expected: FAIL — cannot resolve `./TourController`.

- [ ] **Step 3: Write the controller**

```jsx
// react-dashboard/src/components/Onboarding/TourController.jsx
import { useEffect, useRef } from 'react'
import Joyride, { STATUS, EVENTS, ACTIONS } from 'react-joyride'
import { useOnboardingTour } from '../../hooks/useOnboardingTour'
import { setTourState } from '../../api'
import { PART1_STEPS, PART2_STEPS } from './tourSteps'

const JOYRIDE_STYLES = {
  options: {
    arrowColor: '#0f0f2a',
    backgroundColor: '#0f0f2a',
    primaryColor: '#6d28d9',
    textColor: '#e2e8f0',
    overlayColor: 'rgba(0,0,0,0.6)',
    zIndex: 10000,
  },
}

export default function TourController({ tourState, jobCount, refreshPrereqs }) {
  const persist = (state) => setTourState(state).finally(refreshPrereqs)
  const tour = useOnboardingTour({ tourState, jobCount, onStateChange: persist })
  const { run, part, launchPart1, launchPart2, finishPart1, finishTour, skip, replay } = tour

  // External triggers.
  useEffect(() => {
    const onLaunch = () => launchPart1()
    const onReplay = () => replay()
    window.addEventListener('auto-apply:tour-launch-part1', onLaunch)
    window.addEventListener('auto-apply:tour-replay', onReplay)
    return () => {
      window.removeEventListener('auto-apply:tour-launch-part1', onLaunch)
      window.removeEventListener('auto-apply:tour-replay', onReplay)
    }
  }, [launchPart1, replay])

  // Gate part 2 on the first job arriving after part 1.
  const prevJobCount = useRef(jobCount)
  useEffect(() => {
    if (tourState === 'part1_done' && prevJobCount.current === 0 && jobCount >= 1) {
      launchPart2()
    }
    prevJobCount.current = jobCount
  }, [jobCount, tourState, launchPart2])

  const steps = part === 2 ? PART2_STEPS : PART1_STEPS

  const handleCallback = (data) => {
    const { status, type, action, index, step } = data
    // Open the panel/modal a step needs before it shows.
    if (type === EVENTS.STEP_BEFORE && step?.openEvent) {
      window.dispatchEvent(new CustomEvent(step.openEvent))
    }
    if (type === EVENTS.TARGET_NOT_FOUND) {
      return // joyride advances on its own; nothing to persist
    }
    if (status === STATUS.SKIPPED || action === ACTIONS.CLOSE) {
      skip()
      return
    }
    if (status === STATUS.FINISHED) {
      if (part === 2) finishTour()
      else finishPart1()
    }
  }

  return (
    <Joyride
      run={run}
      steps={steps}
      continuous
      showSkipButton
      showProgress
      disableScrollParentFix
      styles={JOYRIDE_STYLES}
      callback={handleCallback}
    />
  )
}
```

Note: import `EVENTS.STEP_BEFORE` — add it to the mock in the test if the callback references it (it does). Update the test mock's `EVENTS` to include `STEP_BEFORE: 'step:before'`.

- [ ] **Step 4: Wire into App.jsx**

In `react-dashboard/src/App.jsx`:

4a. Import: `import TourController from './components/Onboarding/TourController'`

4b. Trigger Part 1 when the résumé wizard finishes or is skipped. The wizard's `onFinish` currently does `window.location.reload()`. Change it so that on finish it dispatches the launch event AFTER the reload-driven state settles — simplest: instead of reloading, refresh prereqs and dispatch. Replace the `onFinish` prop:

```jsx
            <Wizard
              onFinish={() => {
                prereqs.refresh()
                window.dispatchEvent(new CustomEvent('auto-apply:tour-launch-part1'))
                setWizardSkipped(true)
              }}
              onSkip={() => {
                setWizardSkipped(true)
                if (prereqs.onboardingTour === 'unstarted') {
                  window.dispatchEvent(new CustomEvent('auto-apply:tour-launch-part1'))
                }
              }}
              onManual={handleManualEntry}
              onEdit={handleManualEntry}
            />
```

4c. Mount the controller inside the authed shell (the `path="*"` route `<div>`, near `<Navbar>`), passing live job count:

```jsx
          <TourController
            tourState={prereqs.onboardingTour}
            jobCount={jobs.length}
            refreshPrereqs={prereqs.refresh}
          />
```

- [ ] **Step 5: Run test to verify it passes**

Run (from `react-dashboard/`): `npm run test -- TourController`
Expected: PASS (2 tests).

- [ ] **Step 6: Build to confirm no import/JSX errors**

Run (from `react-dashboard/`): `npm run build`
Expected: build succeeds.

- [ ] **Step 7: Commit**

```bash
git add react-dashboard/src/components/Onboarding/TourController.jsx react-dashboard/src/components/Onboarding/TourController.test.jsx react-dashboard/src/App.jsx
git commit -m "[feat] Add TourController with auto-launch + part-2 gating"
```

---

### Task 6: "Take a tour" replay control in the navbar + DocumentModal open event + manual QA

**Files:**
- Modify: `react-dashboard/src/components/Navbar.jsx` (add "Take a tour" button next to Help)
- Modify: `react-dashboard/src/components/widgets/Settings.jsx` (listen for `auto-apply:open-document` to open `DocumentModal` for tour stop 10)
- Modify: `react-dashboard/CONTEXT.md` (document the tour)
- Test: `react-dashboard/src/components/Navbar.tour.test.jsx`

**Interfaces:**
- Consumes: the `auto-apply:tour-replay` event (Task 5) and `auto-apply:open-document` event (Task 3 `openEvent`).
- Produces: a navbar button that dispatches `auto-apply:tour-replay`; a Settings listener that opens the document modal on `auto-apply:open-document`.

- [ ] **Step 1: Write the failing test**

```jsx
// react-dashboard/src/components/Navbar.tour.test.jsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Navbar from './components/Navbar'

describe('Navbar Take a tour', () => {
  it('dispatches the replay event on click', () => {
    const spy = vi.fn()
    window.addEventListener('auto-apply:tour-replay', spy)
    render(<MemoryRouter><Navbar me={{ email: 'a@b.c' }} /></MemoryRouter>)
    screen.getByRole('button', { name: /take a tour/i }).click()
    expect(spy).toHaveBeenCalled()
    window.removeEventListener('auto-apply:tour-replay', spy)
  })
})
```

Path note: this test file sits in `src/components/` so its import is `./components/Navbar`? No — it sits next to `Navbar.jsx`, so import `./Navbar`. Adjust the import to `import Navbar from './Navbar'` and place the file at `react-dashboard/src/components/Navbar.tour.test.jsx`.

- [ ] **Step 2: Run test to verify it fails**

Run (from `react-dashboard/`): `npm run test -- Navbar.tour`
Expected: FAIL — no button named "Take a tour".

- [ ] **Step 3: Add the navbar button**

In `react-dashboard/src/components/Navbar.jsx`, immediately before the Help `<a>` (~L77), add:

```jsx
        {/* Replay the onboarding tour */}
        <button
          onClick={() => window.dispatchEvent(new CustomEvent('auto-apply:tour-replay'))}
          className="text-sm text-space-dim hover:text-purple-400 transition-colors bg-transparent border-0 p-0 cursor-pointer"
        >
          Take a tour
        </button>
```

- [ ] **Step 4: Run test to verify it passes**

Run (from `react-dashboard/`): `npm run test -- Navbar.tour`
Expected: PASS (1 test).

- [ ] **Step 5: Wire the document-open event in Settings**

In `react-dashboard/src/components/widgets/Settings.jsx`, find the state that controls `DocumentModal` visibility (the `showModal`/`setShowDocument`-style setter used when the ✎ button is clicked). Add an effect that opens it on the tour event:

```jsx
  useEffect(() => {
    const open = () => {
      // Only meaningful when a job is selected; opening the résumé doc modal.
      if (selectedJob) setShowDocumentModal(true) // use the actual setter name in this file
    }
    window.addEventListener('auto-apply:open-document', open)
    return () => window.removeEventListener('auto-apply:open-document', open)
  }, [selectedJob])
```

Match the real state setter name in `Settings.jsx`. If the modal requires a document type, default to the résumé.

- [ ] **Step 6: Update CONTEXT.md**

In `react-dashboard/CONTEXT.md`, add under the components/onboarding section:

```markdown
- **Onboarding tour** (`src/components/Onboarding/`): react-joyride guided tour.
  `TourController.jsx` mounts one controlled `<Joyride>`; `tourSteps.js` holds
  `PART1_STEPS` (profile arc + add-a-job) and `PART2_STEPS` (score → generate →
  preview → credits); `useOnboardingTour.js` is the state machine
  (`unstarted → part1_done → completed`, `skipped`). State persists via
  `PATCH /api/onboarding/tour` and is read from `GET /api/setup-status`
  (`onboardingTour`). Part 1 auto-launches when the résumé wizard finishes/skips;
  Part 2 gates on the first job (jobCount 0→1). Targets are `data-tour="…"`
  attributes. "Take a tour" in the navbar dispatches `auto-apply:tour-replay`.
```

- [ ] **Step 7: Run the full FE suite + build**

Run (from `react-dashboard/`): `npm run test`
Expected: all tests pass (existing + new tour tests).

Run (from `react-dashboard/`): `npm run build`
Expected: build succeeds.

- [ ] **Step 8: Manual QA (real browser, `start.bat dev`)**

Using a profile whose `onboarding_tour` is `unstarted` (a fresh account, or manually PATCH it back for testing):
- Finish/skip the résumé wizard → Part 1 launches; stepping through highlights the profile tree (editor opens), sections, lock, prompt, output-format, then the inbox and the `+ Upload` button. Part 1 ends there.
- Add a job via `+ Upload` → Part 2 auto-launches: score → generate → document preview (modal opens) → credit balance → finishes; balance/state persist (`completed`).
- Reload → tour does not re-run.
- Click **Take a tour** → full sequence replays; with a job present, Part 2 targets resolve; skipping mid-tour sets `skipped` and it doesn't auto-run again.

- [ ] **Step 9: Commit**

```bash
git add react-dashboard/src/components/Navbar.jsx react-dashboard/src/components/Navbar.tour.test.jsx react-dashboard/src/components/widgets/Settings.jsx react-dashboard/CONTEXT.md
git commit -m "[feat] Add Take-a-tour replay control + document-open wiring"
```

---

## Post-implementation

- Update `TODO.md`: note the onboarding guided tour is done under sub-project (4); the remaining (4) work is the automated job-ingestion story (hosted scraping / extension-to-hosted wiring), not the tour.
- Do NOT delete anything or push `main` without explicit user approval (project guardrails).

## Self-Review Notes

- **Spec coverage:** react-joyride controlled mode (Task 5); backend state machine + `setup-status` read + PATCH write (Task 1); two-arc 11-stop content (Task 3); `data-tour` targeting (Task 4); Part 1 auto-launch after wizard + Part 2 gating on first job (Task 5); skip (Tasks 2/5); replay from navbar Help area (Task 6); dark/purple theming (Task 5 `JOYRIDE_STYLES`); tests each task. Open question resolved: state stored in `user_profile.data` JSON, no migration.
- **Placeholders:** none — every code step shows the code. Two spots ("use the actual setter name in Settings.jsx", "match minimal CreditBalance props") are unavoidable local-lookups, each with an explicit instruction on how to resolve; not TBDs.
- **Type consistency:** `onboarding_tour` (backend/JSON) ↔ `onboardingTour` (JS state) used consistently; `useOnboardingTour` return shape (`run`, `part`, `launchPart1/2`, `finishPart1`, `finishTour`, `skip`, `replay`) matches its consumer in `TourController`; `PART1_STEPS`/`PART2_STEPS` names and the `data-tour` id set match across Tasks 3–5; event names (`auto-apply:tour-launch-part1`, `auto-apply:tour-replay`, `auto-apply:edit-profile`, `auto-apply:open-document`) consistent between dispatcher and listener.
