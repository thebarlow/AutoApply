import { useState, useEffect, useCallback } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import Navbar from './components/Navbar'
import Dashboard from './components/Dashboard'
import Pipeline from './components/widgets/Pipeline'
import Settings from './components/widgets/Settings'
import Wizard from './components/Onboarding/Wizard'
import TourController from './components/Onboarding/TourController'
import Docs from './components/Docs'
import AdminPage from './components/AdminPage'
import LandingPage from './components/landing/LandingPage'
import { getJobs, getActivePromptStatus, getLlmStatus, markJobSeen, getMe, stopImpersonation } from './api'
import { usePrerequisites } from './hooks/usePrerequisites'

export default function App() {
  const [me, setMe] = useState(undefined) // undefined=loading, null=logged out
  const [jobs, setJobs] = useState([])
  const [selectedJob, setSelectedJob] = useState(null)
  const [skillFilter, setSkillFilter] = useState(null) // { skill: string, jobKeys: Set<string> } | null
  const [processingKeys, setProcessingKeys] = useState(new Set())
  const [processingActions, setProcessingActions] = useState({}) // { job_key: Set<action> }
  const [settingsTab, setSettingsTab] = useState('User')
  const [promptStatus, setPromptStatus] = useState({})
  const prereqs = usePrerequisites()
  const [wizardSkipped, setWizardSkipped] = useState(false)
  const [toasts, setToasts] = useState([]) // { id, message }

  const dismissToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const pushToast = useCallback((message) => {
    const id = Date.now() + Math.random()
    setToasts((prev) => [...prev, { id, message }])
    setTimeout(() => dismissToast(id), 8000)
  }, [dismissToast])
  const showWizard = prereqs.loaded && prereqs.isFirstRun && !wizardSkipped

  useEffect(() => {
    getMe().then(setMe).catch(() => setMe(null))
  }, [])

  const refetchPromptStatus = useCallback(() => {
    getActivePromptStatus().then(setPromptStatus).catch(() => setPromptStatus({}))
  }, [])

  useEffect(() => {
    refetchPromptStatus()
    const handler = () => refetchPromptStatus()
    window.addEventListener('auto-apply:prompt-status-stale', handler)
    return () => window.removeEventListener('auto-apply:prompt-status-stale', handler)
  }, [refetchPromptStatus])

  // Out-of-credits signal (dispatched from api.js on HTTP 402)
  useEffect(() => {
    const handler = () =>
      pushToast("You're out of credits — purchase more to continue.")
    window.addEventListener('auto-apply:credits-error', handler)
    return () => window.removeEventListener('auto-apply:credits-error', handler)
  }, [pushToast])

  // Purchase success signal (dispatched from Navbar after Stripe Checkout redirect)
  useEffect(() => {
    const handler = () => pushToast('Payment received — credits added.')
    window.addEventListener('auto-apply:purchase-success', handler)
    return () => window.removeEventListener('auto-apply:purchase-success', handler)
  }, [pushToast])

  // "your profile" button in UserHome re-shows a skipped onboarding wizard.
  useEffect(() => {
    const handler = () => setWizardSkipped(false)
    window.addEventListener('auto-apply:open-wizard', handler)
    return () => window.removeEventListener('auto-apply:open-wizard', handler)
  }, [])

  // "Try it out" under the wizard's Manual Entry tab: close the wizard and
  // open the manual profile editor (Settings listens for the event).
  const handleManualEntry = useCallback(() => {
    setWizardSkipped(true)
    setSettingsTab('User')
    window.dispatchEvent(new CustomEvent('auto-apply:edit-profile'))
  }, [])

  // Upsert a single job into the jobs list
  const upsertJob = useCallback((job) => {
    setJobs((prev) => {
      const idx = prev.findIndex((j) => j.job_key === job.job_key)
      if (idx === -1) return [...prev, job]
      const next = [...prev]
      next[idx] = job
      return next
    })
    // Keep selectedJob in sync
    setSelectedJob((prev) => (prev?.job_key === job.job_key ? job : prev))
  }, [])

  // Initial load + SSE subscription
  useEffect(() => {
    getJobs().then(setJobs).catch(console.error)

    let es = null
    let cancelled = false
    let refetchScheduled = false

    const onMessage = (e) => {
      try {
        const payload = JSON.parse(e.data)
        if (payload.type === 'job') {
          upsertJob(payload.data)
        } else if (payload.type === 'llm_status') {
          setProcessingKeys((prev) => {
            const next = new Set(prev)
            if (payload.data.processing) next.add(payload.data.job_key)
            else next.delete(payload.data.job_key)
            return next
          })
        } else if (payload.type === 'prompt_reset') {
          pushToast(payload.data?.message || 'A prompt was reset to its default.')
          refetchPromptStatus()
        } else if (payload.type === 'llm_action') {
          const { job_key, action, processing } = payload.data
          setProcessingActions((prev) => {
            const next = { ...prev }
            const cur = new Set(next[job_key] || [])
            if (processing) cur.add(action)
            else cur.delete(action)
            if (cur.size === 0) delete next[job_key]
            else next[job_key] = cur
            return next
          })
        }
      } catch { /* malformed event — ignore */ }
    }

    const seedFromStatus = (res) => {
      setProcessingKeys(new Set(res?.processing || []))
      const actionsMap = {}
      for (const [jk, list] of Object.entries(res?.actions || {})) {
        actionsMap[jk] = new Set(list)
      }
      setProcessingActions(actionsMap)
    }

    const onError = () => {
      if (!refetchScheduled) {
        refetchScheduled = true
        Promise.allSettled([
          getJobs().then(setJobs),
          getLlmStatus().then(seedFromStatus),
        ]).finally(() => { refetchScheduled = false })
      }
    }

    // Seed processing state BEFORE attaching the SSE stream so a concurrent
    // event can't be overwritten by a late-arriving seed.
    getLlmStatus()
      .then(seedFromStatus)
      .catch(console.error)
      .finally(() => {
        if (cancelled) return
        es = new EventSource('/api/events')
        es.onmessage = onMessage
        es.onerror = onError
      })

    return () => {
      cancelled = true
      if (es) es.close()
    }
  }, [upsertJob, pushToast, refetchPromptStatus])

  // Escape key clears selection
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') {
        setSelectedJob(null)
        setSettingsTab('User')
        setSkillFilter(null)
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  const handleJobDeleted = useCallback((jobKey) => {
    // Job is soft-deleted: SSE will upsert it with state='deleted'; just deselect.
    setSelectedJob((prev) => (prev?.job_key === jobKey ? null : prev))
    setSettingsTab('User')
  }, [])

  const handleJobSelect = useCallback((job) => {
    setSelectedJob(job)
    setSettingsTab('Preview')
    // Auto-dismiss only for errors (so the warning banner clears on view).
    // "ok"/pending-review state clears per-subtab when the user views each one.
    if (job?.unread_indicator === 'error') {
      markJobSeen(job.job_key).catch(() => {})
    }
  }, [])

  if (me === undefined) return null

  if (me === null) {
    const betaClosed = new URLSearchParams(window.location.search).get('beta') === 'closed'
    return (
      <Routes>
        <Route path="/about" element={<LandingPage me={null} betaClosed={betaClosed} />} />
        <Route path="*" element={<Navigate to="/about" replace />} />
      </Routes>
    )
  }

  return (
    <Routes>
      <Route path="/about" element={
        <div className="min-h-screen text-space-text">
          <Navbar me={me} />
          <LandingPage me={me} />
        </div>
      } />
      <Route path="/docs" element={<Docs />} />
      <Route path="/admin" element={<AdminPage />} />
      <Route path="*" element={
        <div className="min-h-screen text-space-text">
          {showWizard && (
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
          )}
          {me?.impersonating && (
            <div className="sticky top-0 z-[120] flex items-center justify-center gap-3 bg-amber-400 text-black text-sm font-semibold px-4 py-2">
              <span>Viewing as {me.impersonating.email}</span>
              <button
                onClick={() => { stopImpersonation().finally(() => { window.location.href = '/' }) }}
                className="underline hover:no-underline"
              >
                Exit
              </button>
            </div>
          )}
          <TourController
            tourState={prereqs.onboardingTour}
            jobCount={jobs.length}
            refreshPrereqs={prereqs.refresh}
          />
          <Navbar me={me} />
          {toasts.length > 0 && (
            <div className="fixed top-4 right-4 z-[200] flex flex-col gap-2 max-w-sm">
              {toasts.map((t) => (
                <div
                  key={t.id}
                  className="flex items-start gap-2 bg-[#1a1414] border border-yellow-500/40 rounded-lg px-3 py-2 shadow-xl"
                >
                  <span className="text-yellow-400 mt-0.5 shrink-0">⚠</span>
                  <p className="text-xs text-space-text flex-1">{t.message}</p>
                  <button
                    onClick={() => dismissToast(t.id)}
                    className="text-space-dim hover:text-space-text text-sm leading-none shrink-0"
                    aria-label="Dismiss"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          )}
          <Dashboard>
            <div className="col-span-3 overflow-hidden h-full">
              <Pipeline
                jobs={jobs}
                processingKeys={processingKeys}
                selectedJob={selectedJob}
                onJobSelect={handleJobSelect}
                skillFilter={skillFilter}
                onClearSkillFilter={() => setSkillFilter(null)}
              />
            </div>
            <div className="col-span-2 overflow-hidden h-full">
              <Settings
                selectedJob={selectedJob}
                activeTab={settingsTab}
                onTabChange={setSettingsTab}
                promptStatus={promptStatus}
                jobActionsInFlight={selectedJob ? (processingActions[selectedJob.job_key] || new Set()) : new Set()}
                onJobDeleted={handleJobDeleted}
                onSkillFilter={({ skill, jobKeys }) => setSkillFilter({ skill, jobKeys: new Set(jobKeys) })}
                activeSkill={skillFilter?.skill ?? null}
              />
            </div>
          </Dashboard>
        </div>
      } />
    </Routes>
  )
}
