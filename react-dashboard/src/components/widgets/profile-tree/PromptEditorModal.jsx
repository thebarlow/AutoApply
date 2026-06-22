import { useEffect } from 'react'
import { PromptField, buildFoldedPreview } from './PromptField'

// The sole surface for editing a section/item/field authoring prompt. Opened by
// the 💬 control on a section, list entry, or LLM-written field. Hosts the pill
// editor + chip tray, and for sections a read-only folded preview mirroring the
// backend build_section_prompt. `value` is the current prompt text (falls back to
// node.prompt for section/item callers); `label` overrides the title noun.
export function PromptEditorModal({ node, isSection, label, value, tree, onChange, onClose }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  const noun = label || (isSection ? 'Section' : 'Item')
  const locked = !!node.locked
  const text = value !== undefined ? value : (node.prompt || '')
  const title = `${noun} prompt — ${node.name || 'Untitled'}`
  const preview = isSection ? buildFoldedPreview(node) : ''

  return (
    <div
      className="fixed inset-0 z-[170] flex items-center justify-center bg-black/60"
      onClick={onClose}
    >
      <div
        className="bg-[#0f0f1a] border border-space-border rounded-2xl p-5 w-[48rem] max-w-[92vw] flex flex-col gap-3"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-space-text">{title}</h2>
          <button
            type="button" aria-label="Close prompt editor" onClick={onClose}
            className="text-space-dim hover:text-space-text text-xl leading-none"
          >×</button>
        </div>
        {locked && (
          <p className="text-xs text-amber-400">
            This prompt is saved but inert while the {noun.toLowerCase()} is
            locked — the LLM skips locked nodes.
          </p>
        )}
        <PromptField
          value={text} tree={tree}
          ariaLabel={title} placeholder="How should the LLM tailor this?"
          onChange={onChange}
        />
        {isSection && (
          <div className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-space-dim">Folded prompt sent to the LLM</span>
            <pre className="text-xs text-space-text bg-white/5 border border-space-border rounded p-2 whitespace-pre-wrap">{preview || '(empty)'}</pre>
          </div>
        )}
      </div>
    </div>
  )
}
