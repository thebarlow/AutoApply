import { useState, useEffect, useCallback } from 'react'
import Navbar from './components/Navbar'
import Dashboard from './components/Dashboard'
import Pipeline from './components/widgets/Pipeline'
import Settings from './components/widgets/Settings'
import { getJobs } from './api'

export default function App() {
  const [jobs, setJobs] = useState([])
  const [selectedJob, setSelectedJob] = useState(null)
  const [processingKeys, setProcessingKeys] = useState(new Set())
  const [settingsTab, setSettingsTab] = useState('User')

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

    const es = new EventSource('/api/events')
    es.onmessage = (e) => {
      try {
        upsertJob(JSON.parse(e.data))
      } catch { /* malformed event — ignore */ }
    }
    es.onerror = () => {
      getJobs().then(setJobs).catch(console.error)
    }
    return () => es.close()
  }, [upsertJob])

  // Escape key clears selection
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape' && selectedJob) {
        setSelectedJob(null)
        setSettingsTab('User')
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [selectedJob])

  const handleJobSelect = (job) => {
    setSelectedJob(job)
    setSettingsTab('Preview')
  }

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
            jobs={jobs}
            processingKeys={processingKeys}
          />
        </div>
      </Dashboard>
    </div>
  )
}
