import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { getDocument, submitFeedback } from '../../api'
import InteractiveResume from './document/InteractiveResume'
import CoverView from './document/CoverView'

// Modal that renders the structured document as an interactive surface.
// Phase 1: read-only render + hover. Edit and feedback wired in later phases.
export default function DocumentModal({ job, docType, processing, onClose }) {
  const [doc, setDoc] = useState(null)
  const [loadError, setLoadError] = useState(null)

  const reload = () => {
    getDocument(job.job_key, docType)
      .then((d) => { setDoc(d); setLoadError(null) })
      .catch((e) => setLoadError(e?.message || 'Could not load document'))
  }
  useEffect(reload, [job.job_key, docType])

  const title = docType === 'resume' ? 'Resume' : 'Cover Letter'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6">
      <motion.div
        initial={{ opacity: 0, scale: 0.97 }}
        animate={{ opacity: 1, scale: 1 }}
        className="bg-[#0f0f1a] border border-space-border rounded-xl w-full max-w-4xl h-[88vh] flex flex-col shadow-2xl"
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-space-border">
          <p className="text-sm font-semibold text-space-text">{title} — {job.title || job.job_key}</p>
          <button onClick={onClose} className="px-2 py-1 rounded text-space-dim hover:text-space-text" title="Close">✕</button>
        </div>

        <div className="flex-1 overflow-auto p-5">
          {loadError && <p className="text-xs text-red-400">{loadError}</p>}
          {!loadError && !doc && <p className="text-xs text-space-dim">Loading…</p>}
          {doc && docType === 'resume' && <InteractiveResume doc={doc} />}
          {doc && docType === 'cover' && <CoverView doc={doc} />}
        </div>
      </motion.div>
    </div>
  )
}
