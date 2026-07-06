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

// readyTimeoutMs={0} makes the pre-launch "wait for the profile target" resolve
// synchronously (the profile-tree element never exists in jsdom), so the launch
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
  it('launches part 1 on the launch event', () => {
    renderCtrl({ tourState: 'unstarted', jobCount: 0 })
    act(() => { window.dispatchEvent(new CustomEvent('auto-apply:tour-launch-part1')) })
    expect(lastJoyrideProps.run).toBe(true)
    expect(lastJoyrideProps.steps.length).toBe(7)
  })

  it('auto-launches part 2 when a job arrives after part1_done', () => {
    const { rerender } = renderCtrl({ tourState: 'part1_done', jobCount: 0 })
    expect(lastJoyrideProps.run).toBe(false)
    rerender(
      <MemoryRouter>
        <TourController readyTimeoutMs={0} refreshPrereqs={vi.fn()} tourState="part1_done" jobCount={1} />
      </MemoryRouter>,
    )
    expect(lastJoyrideProps.run).toBe(true)
    expect(lastJoyrideProps.steps.length).toBe(4)
  })

  it('advances stepIndex past a missing target instead of stalling', () => {
    renderCtrl({ tourState: 'unstarted', jobCount: 0 })
    act(() => { window.dispatchEvent(new CustomEvent('auto-apply:tour-launch-part1')) })
    expect(lastJoyrideProps.stepIndex).toBe(0)
    act(() => { lastJoyrideProps.callback({ type: 'error:target_not_found', index: 0 }) })
    expect(lastJoyrideProps.stepIndex).toBe(1)
  })

  it('advances stepIndex on normal next step', () => {
    renderCtrl({ tourState: 'unstarted', jobCount: 0 })
    act(() => { window.dispatchEvent(new CustomEvent('auto-apply:tour-launch-part1')) })
    expect(lastJoyrideProps.stepIndex).toBe(0)
    act(() => { lastJoyrideProps.callback({ type: 'step:after', action: 'next', index: 0 }) })
    expect(lastJoyrideProps.stepIndex).toBe(1)
  })

  it('chains replay directly into Part 2 when Part 1 finishes during replay', () => {
    renderCtrl({ tourState: 'completed', jobCount: 1 })
    // Trigger replay — should start Part 1.
    act(() => { window.dispatchEvent(new CustomEvent('auto-apply:tour-replay')) })
    expect(lastJoyrideProps.run).toBe(true)
    expect(lastJoyrideProps.steps.length).toBe(7)
    // Part 1 finishes — should chain into Part 2, not call finishPart1.
    // Use type 'tour:end' (not 'step:after') so the STEP_AFTER guard doesn't intercept.
    act(() => { lastJoyrideProps.callback({ status: 'finished', type: 'tour:end', index: 6 }) })
    expect(lastJoyrideProps.steps.length).toBe(4)
  })
})
