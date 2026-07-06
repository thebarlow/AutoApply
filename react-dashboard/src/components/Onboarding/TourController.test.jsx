import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, act } from '@testing-library/react'

// Mock react-joyride so tests assert our wiring, not the library's rendering.
let lastJoyrideProps = null
vi.mock('react-joyride', () => ({
  __esModule: true,
  default: (props) => { lastJoyrideProps = props; return null },
  STATUS: { FINISHED: 'finished', SKIPPED: 'skipped' },
  EVENTS: { STEP_AFTER: 'step:after', STEP_BEFORE: 'step:before', TARGET_NOT_FOUND: 'error:target_not_found' },
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
