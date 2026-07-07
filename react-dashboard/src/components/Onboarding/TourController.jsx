import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Joyride, { STATUS, EVENTS, ACTIONS } from 'react-joyride'
import { useOnboardingTour } from '../../hooks/useOnboardingTour'
import { setTourState } from '../../api'
import { TOUR_STEPS } from './tourSteps'
import './tour.css'

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

const FIRST_TARGET = '[data-tour="user-name"]'
// Distinct app events that advance a gated step (open profile, expand section,
// open/close prompt, close profile).
const ADVANCE_EVENTS = [...new Set(TOUR_STEPS.map((s) => s.advanceOn).filter(Boolean))]

export default function TourController({
  refreshPrereqs,
  // The tour starts on the dashboard's User home; poll for its first target so
  // Joyride doesn't open before the target exists. Tunable so tests resolve fast.
  readyTimeoutMs = 2000,
  readyPollMs = 100,
}) {
  const navigate = useNavigate()
  const persist = (state) => setTourState(state).finally(refreshPrereqs)
  const { run, start, finish, skip } = useOnboardingTour({ onStateChange: persist })

  const [stepIndex, setStepIndex] = useState(0)
  const pollTimer = useRef(null)
  const stepIndexRef = useRef(0)
  const runRef = useRef(false)
  useEffect(() => { stepIndexRef.current = stepIndex }, [stepIndex])
  useEffect(() => { runRef.current = run }, [run])

  // Reset to the first step whenever a run starts.
  useEffect(() => { if (run) setStepIndex(0) }, [run])

  // Drive the pulsing ring around a step's ringTarget (e.g. the prompt ✕).
  useEffect(() => {
    const ring = run ? (TOUR_STEPS[stepIndex]?.ringTarget || '') : ''
    if (ring) document.body.dataset.tourRing = ring
    else delete document.body.dataset.tourRing
    return () => { delete document.body.dataset.tourRing }
  }, [run, stepIndex])

  // External triggers (new-user launch after the résumé wizard + navbar replay).
  useEffect(() => {
    const beginTour = () => {
      // The tour lives on the dashboard's User home — land there and surface it.
      navigate('/')
      window.dispatchEvent(new CustomEvent('auto-apply:show-user-home'))
      if (pollTimer.current) clearTimeout(pollTimer.current)
      let elapsed = 0
      const tick = () => {
        if (document.querySelector(FIRST_TARGET) || elapsed >= readyTimeoutMs) {
          start()
          return
        }
        window.dispatchEvent(new CustomEvent('auto-apply:show-user-home'))
        elapsed += readyPollMs
        pollTimer.current = setTimeout(tick, readyPollMs)
      }
      tick()
    }
    window.addEventListener('auto-apply:tour-launch-part1', beginTour)
    window.addEventListener('auto-apply:tour-replay', beginTour)
    return () => {
      window.removeEventListener('auto-apply:tour-launch-part1', beginTour)
      window.removeEventListener('auto-apply:tour-replay', beginTour)
      if (pollTimer.current) clearTimeout(pollTimer.current)
    }
  }, [navigate, start, readyTimeoutMs, readyPollMs])

  // Move to a step, but wait for its target to exist first (panels/modals that
  // a preceding action opens render a beat later). Fires the step's openEvent
  // before polling so tab/panel switches happen up front. Falls back to
  // advancing after the timeout so a genuinely-missing target never stalls.
  const goPoll = useRef(null)
  const goToStep = useCallback((nextIndex) => {
    if (goPoll.current) clearTimeout(goPoll.current)
    if (nextIndex >= TOUR_STEPS.length) { setStepIndex(0); finish(); return }
    const step = TOUR_STEPS[nextIndex]
    if (step.openEvent) window.dispatchEvent(new CustomEvent(step.openEvent))
    let elapsed = 0
    const tick = () => {
      if (document.querySelector(step.target) || elapsed >= readyTimeoutMs) {
        setStepIndex(nextIndex)
        return
      }
      elapsed += readyPollMs
      goPoll.current = setTimeout(tick, readyPollMs)
    }
    tick()
  }, [finish, readyTimeoutMs, readyPollMs])

  // Advance a gated step when the user performs its action.
  useEffect(() => {
    const handler = (e) => {
      const i = stepIndexRef.current
      if (runRef.current && TOUR_STEPS[i]?.advanceOn === e.type) {
        goToStep(i + 1)
      }
    }
    ADVANCE_EVENTS.forEach((name) => window.addEventListener(name, handler))
    return () => ADVANCE_EVENTS.forEach((name) => window.removeEventListener(name, handler))
  }, [goToStep])

  const handleCallback = (data) => {
    const { status, type, action, index } = data
    const gated = !!TOUR_STEPS[index]?.advanceOn
    if (type === EVENTS.TARGET_NOT_FOUND) {
      // A gated step waits for its action even if the target isn't up yet;
      // a plain step with a missing target is skipped so the tour doesn't stall.
      if (!gated) goToStep(index + 1)
      return
    }
    if (type === EVENTS.STEP_AFTER) {
      // Gated steps advance via their action event, not the (hidden) Next button.
      if (!gated) goToStep(index + (action === ACTIONS.PREV ? -1 : 1))
      return
    }
    if (status === STATUS.SKIPPED || action === ACTIONS.CLOSE) {
      setStepIndex(0)
      skip()
      return
    }
    if (status === STATUS.FINISHED) {
      setStepIndex(0)
      finish()
    }
  }

  return (
    <Joyride
      run={run}
      steps={TOUR_STEPS}
      stepIndex={stepIndex}
      continuous
      showSkipButton
      showProgress
      disableScrollParentFix
      hideCloseButton
      disableOverlayClose
      disableCloseOnEsc
      styles={JOYRIDE_STYLES}
      callback={handleCallback}
    />
  )
}
