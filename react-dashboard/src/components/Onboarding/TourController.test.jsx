import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// Mock react-joyride so tests assert our wiring, not the library's rendering.
let lastJoyrideProps = null
vi.mock('react-joyride', () => ({
  __esModule: true,
  default: (props) => { lastJoyrideProps = props; return null },
  STATUS: { FINISHED: 'finished', SKIPPED: 'skipped' },
  EVENTS: { STEP_AFTER: 'step:after', STEP_BEFORE: 'step:before', TARGET_NOT_FOUND: 'error:target_not_found' },
  ACTIONS: { CLOSE: 'close', NEXT: 'next', PREV: 'prev' },
}))

import TourController from './TourController'

// readyTimeoutMs={0} makes the pre-launch "wait for the first target" resolve
// synchronously (the user-name element never exists in jsdom), so the launch
// happens inside the dispatch act() and assertions can stay synchronous.
function renderCtrl(props) {
  return render(
    <MemoryRouter>
      <TourController readyTimeoutMs={0} refreshPrereqs={vi.fn()} {...props} />
    </MemoryRouter>,
  )
}

beforeEach(() => { lastJoyrideProps = null })

describe('TourController', () => {
  it('starts the tour on the launch event', () => {
    renderCtrl()
    act(() => { window.dispatchEvent(new CustomEvent('auto-apply:tour-launch-part1')) })
    expect(lastJoyrideProps.run).toBe(true)
    expect(lastJoyrideProps.stepIndex).toBe(0)
    expect(lastJoyrideProps.steps.length).toBe(15)
  })

  it('starts the tour on the replay event', () => {
    renderCtrl()
    act(() => { window.dispatchEvent(new CustomEvent('auto-apply:tour-replay')) })
    expect(lastJoyrideProps.run).toBe(true)
  })

  it('advances a gated step only when its action event fires', () => {
    renderCtrl()
    act(() => { window.dispatchEvent(new CustomEvent('auto-apply:tour-launch-part1')) })
    expect(lastJoyrideProps.stepIndex).toBe(0)
    // Wrong event does nothing.
    act(() => { window.dispatchEvent(new CustomEvent('auto-apply:section-expanded')) })
    expect(lastJoyrideProps.stepIndex).toBe(0)
    // The step-0 gate is "profile editor opened".
    act(() => { window.dispatchEvent(new CustomEvent('auto-apply:profile-editor-opened')) })
    expect(lastJoyrideProps.stepIndex).toBe(1)
  })

  it('advances a plain step via the Next button (step:after)', () => {
    renderCtrl()
    act(() => { window.dispatchEvent(new CustomEvent('auto-apply:tour-launch-part1')) })
    act(() => { window.dispatchEvent(new CustomEvent('auto-apply:profile-editor-opened')) })
    expect(lastJoyrideProps.stepIndex).toBe(1) // profile-tree (plain)
    act(() => { lastJoyrideProps.callback({ type: 'step:after', action: 'next', index: 1 }) })
    expect(lastJoyrideProps.stepIndex).toBe(2)
  })

  it('does not skip a gated step when its target is missing', () => {
    renderCtrl()
    act(() => { window.dispatchEvent(new CustomEvent('auto-apply:tour-launch-part1')) })
    // Step 0 is gated; a missing target must NOT auto-advance (it waits).
    act(() => { lastJoyrideProps.callback({ type: 'error:target_not_found', index: 0 }) })
    expect(lastJoyrideProps.stepIndex).toBe(0)
  })

  it('skips a plain step when its target is missing', () => {
    renderCtrl()
    act(() => { window.dispatchEvent(new CustomEvent('auto-apply:tour-launch-part1')) })
    act(() => { window.dispatchEvent(new CustomEvent('auto-apply:profile-editor-opened')) })
    expect(lastJoyrideProps.stepIndex).toBe(1) // plain step
    act(() => { lastJoyrideProps.callback({ type: 'error:target_not_found', index: 1 }) })
    expect(lastJoyrideProps.stepIndex).toBe(2)
  })
})
