import { useState, useEffect, useCallback } from 'react'
import Navbar from './components/Navbar'
import Dashboard from './components/Dashboard'
import Pipeline from './components/widgets/Pipeline'
import Settings from './components/widgets/Settings'
import Wizard from './components/Onboarding/Wizard'
import Docs from './components/Docs'
import { getJobs, getActivePromptStatus, getLlmStatus, markJobSeen } from './api'
import { usePrerequisites } from './hooks/usePrerequisites'

export default function App() {
  const [jobs, setJobs] = useState([])
  const [selectedJob, setSelectedJob] = useState(null)
  const [processingKeys, setProcessingKeys] = useState(new Set())
  const [processingActions, setProcessingActions] = useState({}) // { job_key: Set<action> }
  const [settingsTab, setSettingsTab] = useState('User')
  const [promptStatus, setPromptStatus] = useState({})
  const prereqs = usePrerequisites()
  const [wizardSkipped, setWizardSkipped] = useState(false)
  const showWizard = prereqs.loaded && prereqs.isFirstRun && !wizardSkipped
  const [docsSlug, setDocsSlug] = useState(null)

  useEffect(() => {
    const update = () => {
      const h = window.location.hash
      const m = h.match(/^#\/docs\/(.+)$/)
      if (m) setDocsSlug(m[1])
      else if (h === '#/docs') setDocsSlug('')
      else setDocsSlug(null)
    }
    update()
    window.addEventListener('hashchange', update)
    return () => window.removeEventListener('hashchange', update)
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
  }, [upsertJob])

  // Escape key clears selection
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') {
        setSelectedJob(null)
        setSettingsTab('User')
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  const handleJobDeleted = useCallback((jobKey) => {
    setJobs((prev) => prev.filter((j) => j.job_key !== jobKey))
    setSelectedJob((prev) => (prev?.job_key === jobKey ? null : prev))
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

  return (
    <div className="min-h-screen text-space-text">
      {docsSlug !== null && (
        <Docs
          slug={docsSlug || undefined}
          onClose={() => { window.location.hash = ''; setDocsSlug(null); }}
        />
      )}
      {showWizard && (
        <Wizard
          onFinish={() => { setWizardSkipped(true); prereqs.refresh(); }}
          onSkip={() => setWizardSkipped(true)}
        />
      )}
      <Navbar />
      <Dashboard>
        <div className="col-span-3 overflow-hidden h-full">
          <Pipeline
            jobs={jobs}
            processingKeys={processingKeys}
            selectedJob={selectedJob}
            onJobSelect={handleJobSelect}
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
          />
        </div>
      </Dashboard>
    </div>
  )
}
