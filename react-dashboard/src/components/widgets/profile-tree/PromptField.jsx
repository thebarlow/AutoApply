import { useState, useRef, useCallback } from 'react'

const JOB_CHIPS = [
  { label: 'title', token: '{job.title}' },
  { label: 'company', token: '{job.company}' },
  { label: 'location', token: '{job.location}' },
  { label: 'salary', token: '{job.salary}' },
  { label: 'description', token: '{job.description}' },
  { label: 'processed description', token: '{job.extracted_description}' },
]

const slug = (s) => String(s || '').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '')
const sectionKey = (section) => section.role || slug(section.name)

function sectionFields(section) {
  const out = []
  const walk = (n) => {
    if (n.type === 'field') { out.push(n); return }
    for (const c of n.children || []) walk(c)
  }
  for (const c of section.children || []) walk(c)
  return out
}

// A Job group plus one folder per profile section (section-level chip + a chip
// per field). Mirrors the backend token scheme in resolve_profile_tokens.
export function buildChipGroups(tree) {
  const groups = [{ label: 'Job', chips: JOB_CHIPS }]
  for (const section of tree?.children || []) {
    const key = sectionKey(section)
    const chips = [{ label: `(whole section)`, token: `{profile.${key}}` }]
    for (const f of sectionFields(section)) {
      chips.push({ label: f.name || f.key, token: `{profile.${key}.${f.key}}` })
    }
    groups.push({ label: section.name || key, chips })
  }
  return groups
}

function ChipFolder({ group, onInsert }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="flex flex-col">
      <button
        type="button"
        className="text-left text-xs font-semibold text-space-dim hover:text-space-text"
        onClick={() => setOpen((o) => !o)}
      ><span aria-hidden="true">{open ? '▾' : '▸'} </span>{group.label}</button>
      {open && (
        <div className="flex flex-wrap gap-1.5 pl-3 py-1">
          {group.chips.map((c) => (
            <button
              key={c.token}
              type="button"
              draggable
              onDragStart={(e) => e.dataTransfer.setData('text/plain', c.token)}
              onClick={() => onInsert(c.token)}
              className="px-2 py-0.5 rounded-full border border-purple-500/40 bg-purple-500/10 text-xs text-purple-300 cursor-grab active:cursor-grabbing select-none"
            >{c.label}</button>
          ))}
        </div>
      )}
    </div>
  )
}

export function ChipTray({ groups, onInsert }) {
  return (
    <div className="flex flex-col gap-1 border border-space-border rounded-lg p-2">
      {groups.map((g) => (
        <ChipFolder key={g.label} group={g} onInsert={onInsert} />
      ))}
    </div>
  )
}

// Insert `token` at the textarea's caret (or end), returning the new string.
function insertAtCaret(ref, value, token) {
  const ta = ref.current
  // Use caret position only when the textarea is focused; otherwise append.
  const hasFocus = ta && document.activeElement === ta
  const offset = hasFocus && ta.selectionStart != null ? ta.selectionStart : value.length
  const next = value.slice(0, offset) + token + value.slice(offset)
  if (ta) {
    requestAnimationFrame(() => {
      ta.focus()
      ta.setSelectionRange(offset + token.length, offset + token.length)
    })
  }
  return next
}

export function PromptField({ value, onChange, tree, ariaLabel, placeholder, rows = 3 }) {
  const ref = useRef(null)
  const [popOut, setPopOut] = useState(false)
  const groups = buildChipGroups(tree)

  const insert = useCallback((token) => {
    onChange(insertAtCaret(ref, value ?? '', token))
  }, [value, onChange])

  const onDrop = (e) => {
    e.preventDefault()
    const token = e.dataTransfer.getData('text/plain')
    if (token) insert(token)
  }

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-start gap-1.5">
        <textarea
          ref={ref} aria-label={ariaLabel} rows={rows} placeholder={placeholder}
          value={value ?? ''}
          className="flex-1 bg-white/5 border border-space-border rounded px-2 py-1 text-sm text-space-text resize-y"
          onChange={(e) => onChange(e.target.value)}
          onDrop={onDrop} onDragOver={(e) => e.preventDefault()}
        />
        <button
          type="button" aria-label="Expand editor" title="Pop out"
          className="px-1.5 py-0.5 text-space-dim hover:text-space-text"
          onClick={() => setPopOut(true)}
        >⤢</button>
      </div>
      <ChipTray groups={groups} onInsert={insert} />
      {popOut && (
        <PopOutEditor
          value={value} onChange={onChange} tree={tree}
          title={ariaLabel} onClose={() => setPopOut(false)}
        />
      )}
    </div>
  )
}

export function PopOutEditor({ value, onChange, tree, title, onClose }) {
  const ref = useRef(null)
  const groups = buildChipGroups(tree)
  const insert = (token) => onChange(insertAtCaret(ref, value ?? '', token))
  const onDrop = (e) => {
    e.preventDefault()
    const token = e.dataTransfer.getData('text/plain')
    if (token) insert(token)
  }
  return (
    <div className="fixed inset-0 z-[160] flex items-center justify-center bg-black/60" onClick={onClose}>
      <div
        className="bg-[#0f0f1a] border border-space-border rounded-2xl p-5 w-[48rem] max-w-[92vw] flex flex-col gap-3"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-space-text">{title}</h2>
          <button
            type="button" aria-label="Close editor" onClick={onClose}
            className="text-space-dim hover:text-space-text text-xl leading-none"
          >×</button>
        </div>
        <textarea
          ref={ref} aria-label={`${title} (expanded)`} rows={16} value={value ?? ''}
          className="bg-white/5 border border-space-border rounded px-3 py-2 text-sm text-space-text resize-y"
          onChange={(e) => onChange(e.target.value)}
          onDrop={onDrop} onDragOver={(e) => e.preventDefault()}
        />
        <ChipTray groups={groups} onInsert={insert} />
      </div>
    </div>
  )
}
