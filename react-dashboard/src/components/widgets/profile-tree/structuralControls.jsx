import { useState, useEffect, useRef } from 'react'

const iconBtn = 'px-1.5 py-0.5 text-space-dim hover:text-space-text disabled:opacity-30 disabled:cursor-not-allowed transition-colors'

export function MoveButtons({ canUp, canDown, onUp, onDown }) {
  return (
    <span className="inline-flex">
      <button type="button" aria-label="Move up" className={iconBtn}
        disabled={!canUp} onClick={() => canUp && onUp()}>↑</button>
      <button type="button" aria-label="Move down" className={iconBtn}
        disabled={!canDown} onClick={() => canDown && onDown()}>↓</button>
    </span>
  )
}

export function VisibleToggle({ visible, onToggle, label }) {
  const base = visible ? 'Hide' : 'Show'
  const ariaLabel = label ? `${base} ${label}`.trim() : base
  return (
    <button
      type="button" aria-label={ariaLabel} className={iconBtn}
      onClick={onToggle}
    >{visible ? '👁' : '🚫'}</button>
  )
}

// Lock control for a field: open padlock = the LLM may rewrite this value,
// closed padlock = the LLM leaves it as typed. Pairs with VisibleToggle (eye).
export function LlmWriteToggle({ written, onToggle }) {
  return (
    <button
      data-tour="section-lock"
      type="button"
      aria-label={written ? 'Lock from LLM (keep as typed)' : 'Unlock for LLM to write'}
      title={written ? 'LLM writes this field — click to lock' : 'Locked — click to let the LLM write it'}
      className={iconBtn}
      onClick={onToggle}
    >{written ? '🔓' : '🔒'}</button>
  )
}

export function RenameLabel({ name, editable, onRename }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(name)
  if (!editable) {
    return <span className="text-sm font-semibold text-space-text">{name}</span>
  }
  if (!editing) {
    // Double-click to edit; a single click is left to bubble (e.g. to toggle a
    // section's collapse) rather than entering rename mode.
    return (
      <span
        className="text-sm font-semibold text-space-text hover:text-purple-300 cursor-text select-none"
        title="Double-click to rename"
        onDoubleClick={() => { setDraft(name); setEditing(true) }}
      >{name}</span>
    )
  }
  const commit = () => { setEditing(false); if (draft !== name) onRename(draft) }
  return (
    <input
      autoFocus type="text" value={draft}
      className="bg-white/5 border border-space-border rounded px-2 py-0.5 text-sm text-space-text"
      onClick={(e) => e.stopPropagation()}
      onChange={(e) => setDraft(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === 'Enter') commit()
        else if (e.key === 'Escape') setEditing(false)
      }}
      onBlur={commit}
    />
  )
}

export function RemoveButton({ onRemove, label }) {
  const [confirm, setConfirm] = useState(false)
  const ref = useRef(null)

  // While confirming, dismiss when the user clicks (or focuses) anywhere
  // outside this control — not merely on mouse-leave, so the button has clear
  // edges and stays put until an intentional action elsewhere.
  useEffect(() => {
    if (!confirm) return undefined
    const dismiss = (e) => { if (ref.current && !ref.current.contains(e.target)) setConfirm(false) }
    document.addEventListener('pointerdown', dismiss)
    return () => document.removeEventListener('pointerdown', dismiss)
  }, [confirm])

  if (confirm) {
    return (
      <button
        ref={ref}
        type="button" aria-label={`Confirm ${label || 'remove'}`}
        className="text-xs font-semibold text-red-400 hover:text-red-300 border border-red-400/60 hover:border-red-300 rounded px-2 py-0.5 transition-colors"
        onClick={onRemove}
      >Confirm?</button>
    )
  }
  return (
    <button
      ref={ref}
      type="button" aria-label={label} className={iconBtn}
      onClick={() => setConfirm(true)}
    >✕</button>
  )
}

export function AddButton({ label, onClick }) {
  return (
    <button
      type="button"
      className="self-start text-xs text-purple-400 hover:text-purple-300"
      onClick={onClick}
    >{label}</button>
  )
}
