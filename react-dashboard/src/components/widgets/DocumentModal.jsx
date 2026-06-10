import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { getDocument, putDocument, submitFeedback } from '../../api'
import InteractiveResume from './document/InteractiveResume'
import CoverView from './document/CoverView'

const SECTION_FIELD = { summary: 'profile_summary', experience: 'experience', education: 'education', project: 'projects', skills: 'skills' }

// Modal that renders the structured document as an interactive surface.
// Phase 1: read-only render + hover. Edit and feedback wired in later phases.
export default function DocumentModal({ job, docType, processing, onClose }) {
  const [doc, setDoc] = useState(null)
  const [loadError, setLoadError] = useState(null)
  const [notes, setNotes] = useState({})       // key -> { section, label, note }
  const [submitting, setSubmitting] = useState(false)
  const [actionError, setActionError] = useState(null)

  const setNote = (key, value) => setNotes((n) => ({ ...n, [key]: value }))
  const collected = Object.values(notes).filter((n) => (n.note || '').trim())

  const submitNotes = async () => {
    if (!collected.length) return
    setSubmitting(true); setActionError(null)
    try {
      await submitFeedback(job.job_key, docType, collected.map((n) => ({
        section: n.section, label: n.label, note: n.note.trim(),
      })))
      onClose()
    } catch (e) {
      setActionError(e?.message || 'Failed to submit feedback')
      setSubmitting(false)
    }
  }

  const reload = () => {
    setDoc(null)  // clear stale content while the new doc loads (job/tab switch)
    getDocument(job.job_key, docType)
      .then((d) => { setDoc(d); setLoadError(null) })
      .catch((e) => setLoadError(e?.message || 'Could not load document'))
  }
  useEffect(reload, [job.job_key, docType])

  const handleSave = async (section, index, newValue) => {
    if (!doc) return
    const next = JSON.parse(JSON.stringify(doc))
    if (section === 'summary') {
      next.profile_summary = newValue
    } else {
      next[SECTION_FIELD[section]][index] = newValue
    }
    try {
      await putDocument(job.job_key, docType, next)
      setLoadError(null)
      reload()
    } catch (e) {
      setLoadError(e?.message || 'Failed to save changes')
      throw e
    }
  }

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
          {doc && docType === 'resume' && (
            <InteractiveResume doc={doc} onSave={handleSave} notes={notes} setNote={setNote} />
          )}
          {doc && docType === 'cover' && (
            <CoverView doc={doc} onSave={async (body) => {
              const next = { ...doc, body }
              await putDocument(job.job_key, 'cover', next)
              reload()
            }} />
          )}
        </div>

        <div className="px-5 py-3 border-t border-space-border flex items-center justify-between gap-3">
          {actionError ? <span className="text-xs text-red-400 break-words">{actionError}</span> : <span />}
          <button
            onClick={submitNotes}
            disabled={submitting || processing || !collected.length}
            className="px-4 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold transition-colors"
          >
            {submitting ? 'Submitting…' : processing ? 'Processing…' : `Regenerate with feedback${collected.length ? ` (${collected.length})` : ''}`}
          </button>
        </div>
      </motion.div>
    </div>
  )
}
