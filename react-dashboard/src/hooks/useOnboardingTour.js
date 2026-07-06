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
