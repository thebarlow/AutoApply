import { useEffect } from 'react'

// Large centered overlay that hosts the full profile editor. Replaces the
// narrow pushed "profileDetail" view so the section tree has room to breathe.
export default function ProfileEditorModal({ children, onClose }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-[120] flex items-start justify-center bg-black/60 p-6 overflow-y-auto" onClick={onClose}>
      <div
        className="bg-[#0f0f1a] border border-space-border rounded-2xl w-[60rem] max-w-[95vw] my-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-space-border">
          <span className="text-xs font-semibold uppercase tracking-widest text-space-dim">Edit Profile</span>
          <button
            type="button" aria-label="Close profile editor" onClick={onClose}
            className="text-space-dim hover:text-space-text text-xl leading-none"
          >×</button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  )
}
