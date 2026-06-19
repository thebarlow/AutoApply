import { useState } from 'react'

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

export function VisibleToggle({ visible, onToggle }) {
  return (
    <button
      type="button" aria-label={visible ? 'Hide' : 'Show'} className={iconBtn}
      onClick={onToggle}
    >{visible ? '👁' : '🚫'}</button>
  )
}

export function RenameLabel({ name, editable, onRename }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(name)
  if (!editable) {
    return <span className="text-sm font-semibold text-space-text">{name}</span>
  }
  if (!editing) {
    return (
      <button
        type="button"
        className="text-sm font-semibold text-space-text hover:text-purple-300"
        onClick={() => { setDraft(name); setEditing(true) }}
      >{name}</button>
    )
  }
  const commit = () => { setEditing(false); if (draft !== name) onRename(draft) }
  return (
    <input
      autoFocus type="text" value={draft}
      className="bg-white/5 border border-space-border rounded px-2 py-0.5 text-sm text-space-text"
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
  if (confirm) {
    return (
      <button
        type="button"
        className="text-xs text-red-400 hover:text-red-300 px-1.5"
        onClick={onRemove}
        onMouseLeave={() => setConfirm(false)}
      >Confirm?</button>
    )
  }
  return (
    <button
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
