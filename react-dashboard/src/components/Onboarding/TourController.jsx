import { useEffect, useRef, useState } from 'react'
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

  const [stepIndex, setStepIndex] = useState(0)
  const replaying = useRef(false)

  // Reset step index whenever a run starts or the part changes mid-run (replay chains part1→part2).
  useEffect(() => {
    if (run) setStepIndex(0)
  }, [run, part])

  // External triggers.
  useEffect(() => {
    const onLaunch = () => launchPart1()
    const onReplay = () => { replaying.current = true; replay() }
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
      // Skip the missing step — Joyride stalls when a target is absent, so we advance manually.
      setStepIndex(index + 1)
      return
    }
    if (type === EVENTS.STEP_AFTER) {
      setStepIndex(index + (action === ACTIONS.PREV ? -1 : 1))
      return
    }
    if (status === STATUS.SKIPPED || action === ACTIONS.CLOSE) {
      replaying.current = false
      setStepIndex(0)
      skip()
      return
    }
    if (status === STATUS.FINISHED) {
      setStepIndex(0)
      if (part === 2) {
        finishTour()
        replaying.current = false
      } else if (replaying.current) {
        // Replay: chain directly into Part 2 without persisting part1_done.
        launchPart2()
      } else {
        finishPart1()
      }
    }
  }

  return (
    <Joyride
      run={run}
      steps={steps}
      stepIndex={stepIndex}
      continuous
      showSkipButton
      showProgress
      disableScrollParentFix
      spotlightClicks={false}
      styles={JOYRIDE_STYLES}
      callback={handleCallback}
    />
  )
}
