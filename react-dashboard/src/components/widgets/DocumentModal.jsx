import { useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { getDocument, putDocument, submitFeedback } from '../../api'
import DocumentTree from './document/DocumentTree'
import CoverView from './document/CoverView'
import DocumentPreview from './document/DocumentPreview'

// Renders the structured document as an interactive surface: hover-highlight,
// inline edit (PUT), and per-item/cover feedback (regenerate).
export default function DocumentModal({ job, docType, processing, onClose }) {
  const [doc, setDoc] = useState(null)
  const [loadError, setLoadError] = useState(null)
  const [notes, setNotes] = useState({})       // key -> { section, label, note }
  const [submitting, setSubmitting] = useState(false)
  const [actionError, setActionError] = useState(null)
  const [coverFeedback, setCoverFeedback] = useState('')
  const [previewVersion, setPreviewVersion] = useState(0)
  const [refreshing, setRefreshing] = useState(false)
  // Children (CoverView) install a consumer here that exits an
  // open inline edit or feedback box and returns true; if nothing is open it returns
  // false and the modal closes instead.
  const escapeRef = useRef(null)

  // Capture Escape before it reaches the app-level handler (which would deselect the
  // job and jump to the User view). Escape exits an inner edit/feedback mode first,
  // and only closes the modal — back to the job details view — when nothing is open.
  useEffect(() => {
    const onKey = (e) => {
      if (e.key !== 'Escape') return
      e.preventDefault()
      e.stopPropagation()
      if (escapeRef.current && escapeRef.current()) return
      onClose()
    }
    document.addEventListener('keydown', onKey, true)
    return () => document.removeEventListener('keydown', onKey, true)
  }, [onClose])

  const setNote = (key, value) => setNotes((n) => ({ ...n, [key]: value }))
  const collected = docType === 'cover'
    ? (coverFeedback.trim() ? [{ section: 'body', label: 'Letter body', note: coverFeedback.trim() }] : [])
    : Object.values(notes).filter((n) => (n.note || '').trim())

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
      .then((d) => { setDoc(d); setLoadError(null); setPreviewVersion((v) => v + 1) })
      .catch((e) => setLoadError(e?.message || 'Could not load document'))
  }
  useEffect(reload, [job.job_key, docType])

  const isTreeV1 = doc && doc.schema === 'tree-v1'
  const isLegacyResume = doc && docType === 'resume' && !isTreeV1

  const handleTreeSave = async (nextRoot) => {
    setDoc(nextRoot)
    setRefreshing(true)
    try {
      await putDocument(job.job_key, 'resume', nextRoot)
      setLoadError(null)
      setPreviewVersion((v) => v + 1)
    } catch (e) {
      setLoadError(e?.message || 'Failed to save changes')
    } finally {
      setRefreshing(false)
    }
  }

  const title = docType === 'resume' ? 'Resume' : 'Cover Letter'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6">
      <motion.div
        initial={{ opacity: 0, scale: 0.97 }}
        animate={{ opacity: 1, scale: 1 }}
        className="bg-[#0f0f1a] border border-space-border rounded-xl w-full max-w-6xl h-[88vh] flex flex-col shadow-2xl"
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-space-border">
          <p className="text-sm font-semibold text-space-text">{title} — {job.title || job.job_key}</p>
          <button onClick={onClose} className="px-2 py-1 rounded text-space-dim hover:text-space-text" title="Close">✕</button>
        </div>

        <div className="flex-1 overflow-hidden p-5 flex flex-col lg:flex-row gap-4">
          <div className="flex-1 overflow-auto lg:w-1/2">
            {loadError && <p className="text-xs text-red-400">{loadError}</p>}
            {!loadError && !doc && <p className="text-xs text-space-dim">Loading…</p>}
            {doc && docType === 'resume' && isTreeV1 && (
              <DocumentTree doc={doc} onSave={handleTreeSave} notes={notes} setNote={setNote} />
            )}
            {doc && isLegacyResume && (
              <p className="text-sm text-space-dim">
                This résumé was generated before the new editor. Regenerate it to edit inline.
              </p>
            )}
            {doc && docType === 'cover' && (
              <CoverView
                doc={doc}
                escapeRef={escapeRef}
                onSave={async (body) => {
                  const next = { ...doc, body }
                  await putDocument(job.job_key, 'cover', next)
                  reload()
                }}
                feedback={coverFeedback}
                setFeedback={setCoverFeedback}
              />
            )}
          </div>
          <div className="flex-1 lg:w-1/2 min-h-[300px] lg:min-h-0">
            {doc ? (
              <DocumentPreview
                jobKey={job.job_key} docType={docType}
                version={previewVersion} refreshing={refreshing}
              />
            ) : (
              <p className="text-xs text-space-dim">Generate this document to see a preview.</p>
            )}
          </div>
        </div>

        <div className="px-5 py-3 border-t border-space-border flex items-center justify-between gap-3">
          {actionError ? <span className="text-xs text-red-400 break-words">{actionError}</span> : <span />}
          <button
            onClick={submitNotes}
            disabled={submitting || processing || !collected.length || isLegacyResume}
            className="px-4 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold transition-colors"
          >
            {submitting ? 'Submitting…' : processing ? 'Processing…' : `Regenerate with feedback${collected.length ? ` (${collected.length})` : ''}`}
          </button>
        </div>
      </motion.div>
    </div>
  )
}
