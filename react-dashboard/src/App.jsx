import { useState, useEffect, useCallback } from 'react'
import Navbar from './components/Navbar'
import Dashboard from './components/Dashboard'
import Pipeline from './components/widgets/Pipeline'
import Settings from './components/widgets/Settings'
import { getJobs, getActivePromptStatus, getLlmStatus, markJobSeen } from './api'

export default function App() {
  const [jobs, setJobs] = useState([])
  const [selectedJob, setSelectedJob] = useState(null)
  const [processingKeys, setProcessingKeys] = useState(new Set())
  const [settingsTab, setSettingsTab] = useState('User')
  const [promptStatus, setPromptStatus] = useState({})

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
    getLlmStatus().then((res) => setProcessingKeys(new Set(res?.processing || []))).catch(console.error)

    const es = new EventSource('/api/events')
    es.onmessage = (e) => {
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
        }
      } catch { /* malformed event — ignore */ }
    }
    let refetchScheduled = false
    es.onerror = () => {
      if (!refetchScheduled) {
        refetchScheduled = true
        getJobs().then(setJobs).catch(console.error).finally(() => { refetchScheduled = false })
        getLlmStatus().then((res) => setProcessingKeys(new Set(res?.processing || []))).catch(console.error)
      }
    }
    return () => es.close()
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

  const handleJobSelect = useCallback((job) => {
    setSelectedJob(job)
    setSettingsTab('Preview')
    if (job?.unread_indicator) {
      markJobSeen(job.job_key).catch(() => {})
    }
  }, [])

  return (
    <div className="min-h-screen text-space-text">
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
          />
        </div>
      </Dashboard>
    </div>
  )
}
