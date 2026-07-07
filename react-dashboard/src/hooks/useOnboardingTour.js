import { useCallback, useState } from 'react'

// Minimal run-state + terminal persistence for the guided tour. Step
// sequencing and action-gating live in TourController; this only tracks whether
// the tour is running and persists the terminal state (completed / skipped).
export function useOnboardingTour({ onStateChange }) {
  const [run, setRun] = useState(false)

  const start = useCallback(() => setRun(true), [])

  const finish = useCallback(() => {
    setRun(false)
    onStateChange('completed')
  }, [onStateChange])

  const skip = useCallback(() => {
    setRun(false)
    onStateChange('skipped')
  }, [onStateChange])

  return { run, start, finish, skip }
}
