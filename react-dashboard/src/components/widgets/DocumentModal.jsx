import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { getDocument, submitFeedback } from '../../api'
import { SubToggle, MarkdownView } from './Settings'

// Build the anchorable section list from a structured document.
function buildSections(docType, doc) {
  if (!doc) return []
  if (docType === 'cover') {
    return [{ section: 'body', label: 'Letter body' }]
  }
  const out = [{ section: 'summary', label: 'Profile summary' }]
  ;(doc.experience || []).forEach((e, i) => {
    const who = [e.title, e.company].filter(Boolean).join(' at ')
    out.push({ section: `experience:${i}`, label: `Experience [${i}]${who ? ` (${who})` : ''}` })
  })
  ;(doc.projects || []).forEach((p, i) => {
    out.push({ section: `project:${i}`, label: `Project [${i}]${p.name ? ` (${p.name})` : ''}` })
  })
  out.push({ section: 'skills', label: 'Skills' })
  return out
}

export default function DocumentModal({ job, docType, cacheKey, processing, onEdit, onClose }) {
  const [artifactView, setArtifactView] = useState('pdf')
  const [sections, setSections] = useState([])
  const [notes, setNotes] = useState({})       // section -> text
  const [open, setOpen] = useState({})         // section -> bool (note input shown)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    let alive = true
    getDocument(job.job_key, docType)
      .then((doc) => { if (alive) setSections(buildSections(docType, doc)) })
      .catch(() => { if (alive) setSections(buildSections(docType, null)) })
    return () => { alive = false }
  }, [job.job_key, docType, cacheKey])

  const hasNotes = Object.values(notes).some((t) => (t || '').trim())
  const docUrl = (ext) =>
    `/api/jobs/${job.job_key}/${docType}${ext}?v=${cacheKey}`

  const handleSubmit = async () => {
    const payload = sections
      .filter((s) => (notes[s.section] || '').trim())
      .map((s) => ({ section: s.section, label: s.label, note: notes[s.section].trim() }))
    if (!payload.length) return
    setSubmitting(true)
    setError(null)
    try {
      await submitFeedback(job.job_key, docType, payload)
      onClose()   // results stream in via SSE; parent shows processing
    } catch (e) {
      setError(e?.message || 'Failed to submit feedback')
      setSubmitting(false)
    }
  }

  const title = docType === 'resume' ? 'Resume' : 'Cover Letter'
  const regenDisabled = submitting || processing || !hasNotes

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6">
      <motion.div
        initial={{ opacity: 0, scale: 0.97 }}
        animate={{ opacity: 1, scale: 1 }}
        className="bg-[#0f0f1a] border border-space-border rounded-xl w-full max-w-6xl h-[88vh] flex flex-col shadow-2xl"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-space-border">
          <p className="text-sm font-semibold text-space-text">
            {title} — {job.title || job.job_key}
          </p>
          <div className="flex items-center gap-2">
            <SubToggle
              options={[{ key: 'pdf', label: 'PDF' }, { key: 'markdown', label: 'Markdown' }]}
              value={artifactView}
              onChange={setArtifactView}
            />
            <button
              onClick={onEdit}
              className="px-3 py-1 rounded text-xs font-semibold border border-space-border text-space-dim hover:text-space-text transition-colors"
            >
              Edit
            </button>
            <button
              onClick={onClose}
              className="px-2 py-1 rounded text-space-dim hover:text-space-text transition-colors"
              title="Close"
            >
              ✕
            </button>
          </div>
        </div>

        {/* Body: side-by-side */}
        <div className="flex flex-1 min-h-0">
          {/* Document */}
          <div className="flex-1 min-w-0 overflow-auto p-4">
            {artifactView === 'pdf' ? (
              <iframe
                src={docUrl('')}
                className="w-full h-full min-h-[70vh] rounded border border-space-border"
                title={`${title} PDF`}
              />
            ) : (
              <MarkdownView url={docUrl('/markdown')} />
            )}
          </div>

          {/* Feedback panel */}
          <div className="w-80 shrink-0 border-l border-space-border flex flex-col">
            <div className="px-4 py-3 border-b border-space-border">
              <p className="text-xs font-semibold uppercase tracking-widest text-space-dim">
                Feedback for regeneration
              </p>
            </div>
            <div className="flex-1 overflow-auto p-4 flex flex-col gap-3">
              {sections.map((s) => {
                const isOpen = !!open[s.section]
                const val = notes[s.section] || ''
                return (
                  <div key={s.section} className="flex flex-col gap-1">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs text-space-text truncate" title={s.label}>{s.label}</span>
                      {!isOpen && (
                        <button
                          onClick={() => setOpen((o) => ({ ...o, [s.section]: true }))}
                          className="text-xs text-purple-400 hover:text-purple-300 shrink-0"
                        >
                          + note
                        </button>
                      )}
                    </div>
                    {isOpen && (
                      <textarea
                        autoFocus
                        rows={2}
                        value={val}
                        onChange={(e) => setNotes((n) => ({ ...n, [s.section]: e.target.value }))}
                        placeholder="What should change?"
                        className="w-full text-xs rounded bg-[#0a0a1a] border border-space-border text-space-text p-2 resize-y focus:border-purple-500 outline-none"
                      />
                    )}
                  </div>
                )
              })}
            </div>
            <div className="px-4 py-3 border-t border-space-border flex flex-col gap-2">
              {error && <p className="text-xs text-red-400 break-words">{error}</p>}
              <button
                onClick={handleSubmit}
                disabled={regenDisabled}
                className="w-full py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold transition-colors"
              >
                {submitting ? 'Submitting…' : processing ? 'Processing…' : 'Regenerate with feedback'}
              </button>
              {hasNotes && !submitting && (
                <button
                  onClick={() => { setNotes({}); setOpen({}) }}
                  className="text-xs text-space-dim hover:text-space-text transition-colors"
                >
                  Clear all
                </button>
              )}
            </div>
          </div>
        </div>
      </motion.div>
    </div>
  )
}
