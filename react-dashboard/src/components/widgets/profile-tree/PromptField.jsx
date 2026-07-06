import { useRef, useEffect, useMemo, useState } from 'react'

const JOB_CHIPS = [
  { label: 'title', token: '{job.title}' },
  { label: 'company', token: '{job.company}' },
  { label: 'location', token: '{job.location}' },
  { label: 'salary', token: '{job.salary}' },
  { label: 'description', token: '{job.description}' },
  { label: 'processed description', token: '{job.extracted_description}' },
]

function sectionFields(section) {
  const out = []
  const walk = (n) => {
    if (n.type === 'field') { out.push(n); return }
    for (const c of n.children || []) walk(c)
  }
  for (const c of section.children || []) walk(c)
  return out
}

export function entryLabel(entry) {
  if (entry?.name && entry.name.trim()) return entry.name.trim()
  for (const f of entry?.children || []) {
    const v = f.value
    const s = Array.isArray(v) ? v.map(String).join(', ') : (v == null ? '' : String(v))
    if (s.trim()) return s.trim()
  }
  return 'Entry'
}

export function buildFoldedPreview(section) {
  if (!section || section.locked) return ''
  const parts = []
  if (section.prompt && section.prompt.trim()) parts.push(section.prompt.trim())
  const child = (section.children || [])[0]
  if (child && child.type === 'list') {
    for (const entry of child.children || []) {
      if (entry.locked || !(entry.prompt && entry.prompt.trim())) continue
      parts.push(`[${entryLabel(entry)}: ${entry.prompt.trim()}]`)
    }
  }
  if (!parts.length) return ''
  return `[${section.name}: ${parts.join(' ')}]`
}

// Chip groups. Profile chips carry a node-id token ({profile:<id>}) so they are
// rename-safe; `display` is the human-readable label shown in the editor pill.
// A profile folder (section or list entry) carries its own `token`, so the folder
// header itself is draggable to inject the whole node's data — there is no
// separate "(whole section)" / "(whole entry)" pill.
export function buildChipGroups(tree) {
  const groups = [{
    label: 'Job',
    chips: JOB_CHIPS.map((c) => ({ token: c.token, label: c.label, display: `Job: ${c.label}` })),
  }]
  for (const section of tree?.children || []) {
    const name = section.name || 'Section'
    const child = (section.children || [])[0]
    if (child && child.type === 'list') {
      const subfolders = (child.children || []).map((entry) => {
        const elabel = entryLabel(entry)
        const chips = (entry.children || []).map((f) => ({
          token: `{profile:${f.id}}`, label: f.name || f.key,
          display: `${name} › ${elabel} › ${f.name || f.key}`,
        }))
        return { label: elabel, token: `{profile:${entry.id}}`, display: `${name} › ${elabel}`, chips }
      })
      groups.push({ label: name, token: `{profile:${section.id}}`, display: name, subfolders })
    } else {
      const chips = sectionFields(section).map((f) => ({
        token: `{profile:${f.id}}`, label: f.name || f.key, display: `${name} › ${f.name || f.key}`,
      }))
      groups.push({ label: name, token: `{profile:${section.id}}`, display: name, chips })
    }
  }
  return groups
}

// token -> display label, for rendering stored tokens as pills. Includes the
// folder tokens (so a dragged-in section/entry folder renders as a labelled pill).
export function buildLabelMap(tree) {
  const map = {}
  const add = (chips) => { for (const c of chips || []) map[c.token] = c.display }
  for (const g of buildChipGroups(tree)) {
    if (g.token) map[g.token] = g.display
    add(g.chips)
    for (const sf of g.subfolders || []) {
      if (sf.token) map[sf.token] = sf.display
      add(sf.chips)
    }
  }
  return map
}

const TOKEN_RE = /\{profile:[\w-]+\}|\{job\.[\w]+\}/g

// Split a stored string into ordered text/token segments.
export function splitSegments(value) {
  const out = []
  let last = 0
  const s = value || ''
  for (const m of s.matchAll(TOKEN_RE)) {
    if (m.index > last) out.push({ type: 'text', value: s.slice(last, m.index) })
    out.push({ type: 'token', value: m[0] })
    last = m.index + m[0].length
  }
  if (last < s.length) out.push({ type: 'text', value: s.slice(last) })
  return out
}

const escapeHtml = (s) =>
  s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

function pillHtml(token, label) {
  return `<span class="prompt-chip" contenteditable="false" data-token="${escapeHtml(token)}">${escapeHtml(label || token)}</span>`
}

// Stored string -> editor innerHTML (text + non-editable pill spans).
export function renderHtml(value, labels) {
  return splitSegments(value).map((seg) => (
    seg.type === 'token'
      ? pillHtml(seg.value, labels[seg.value] || seg.value)
      : escapeHtml(seg.value).replace(/\n/g, '<br>')
  )).join('')
}

// Editor DOM -> stored string (pills become their data-token, <br>/<div> -> \n).
export function serializeNode(root) {
  let out = ''
  const visit = (node) => {
    node.childNodes.forEach((n) => {
      if (n.nodeType === Node.TEXT_NODE) {
        out += n.textContent
      } else if (n.nodeType === Node.ELEMENT_NODE) {
        const tok = n.getAttribute && n.getAttribute('data-token')
        if (tok) { out += tok; return }
        if (n.tagName === 'BR') { out += '\n'; return }
        if (n.tagName === 'DIV' && out && !out.endsWith('\n')) out += '\n'
        visit(n)
      }
    })
  }
  if (root) visit(root)
  return out
}

// Insert a pill (+ trailing nbsp) at the caret if it is inside `root`, else append.
function insertPillAtCaret(root, token, label) {
  if (!root) return
  const span = document.createElement('span')
  span.className = 'prompt-chip'
  span.setAttribute('contenteditable', 'false')
  span.setAttribute('data-token', token)
  span.textContent = label || token
  const space = document.createTextNode(' ')
  const sel = window.getSelection && window.getSelection()
  if (sel && sel.rangeCount && root.contains(sel.anchorNode)) {
    const range = sel.getRangeAt(0)
    range.deleteContents()
    range.insertNode(space)
    range.insertNode(span)
    range.setStartAfter(space)
    range.collapse(true)
    sel.removeAllRanges()
    sel.addRange(range)
  } else {
    root.appendChild(span)
    root.appendChild(space)
  }
}

function ChipFolder({ group, onInsert }) {
  const [open, setOpen] = useState(false)
  const draggable = !!group.token
  return (
    <div className="flex flex-col">
      <button
        type="button"
        draggable={draggable}
        title={draggable ? `Drag to inject all of ${group.label}` : undefined}
        onDragStart={draggable ? (e) => {
          e.dataTransfer.setData('text/plain', group.token)
          e.dataTransfer.setData('application/x-chip-label', group.display)
        } : undefined}
        className={`text-left text-xs font-semibold text-space-dim hover:text-space-text ${draggable ? 'cursor-grab active:cursor-grabbing' : ''}`}
        onClick={() => setOpen((o) => !o)}
      ><span aria-hidden="true">{open ? '▾' : '▸'} </span>{group.label}</button>
      {open && group.chips && (
        <div className="flex flex-wrap gap-1.5 pl-3 py-1">
          {group.chips.map((c) => (
            <button
              key={c.token}
              type="button"
              draggable
              onDragStart={(e) => {
                e.dataTransfer.setData('text/plain', c.token)
                e.dataTransfer.setData('application/x-chip-label', c.display)
              }}
              onClick={() => onInsert(c.token, c.display)}
              className="px-2 py-0.5 rounded-full border border-emerald-500/40 bg-emerald-500/10 text-xs text-emerald-300 cursor-grab active:cursor-grabbing select-none"
            >{c.label}</button>
          ))}
        </div>
      )}
      {open && group.subfolders && (
        <div className="flex flex-col pl-3">
          {group.subfolders.map((sf) => (
            <ChipFolder key={sf.label} group={sf} onInsert={onInsert} />
          ))}
        </div>
      )}
    </div>
  )
}

export function ChipTray({ groups, onInsert }) {
  return (
    <div className="flex flex-col gap-1 border border-space-border rounded-lg p-2">
      {groups.map((g) => <ChipFolder key={g.label} group={g} onInsert={onInsert} />)}
    </div>
  )
}

// The contenteditable surface. `value` is the canonical token string; the DOM is
// re-rendered from it only when it changes from what we last serialized, so typing
// does not clobber the caret.
function Editor({ value, onChange, tree, ariaLabel, editorRef, extraClass = '' }) {
  const innerRef = useRef(null)
  const ref = editorRef || innerRef
  const labels = useMemo(() => buildLabelMap(tree), [tree])
  const last = useRef(null)

  useEffect(() => {
    if (ref.current && (last.current === null || value !== last.current)) {
      ref.current.innerHTML = renderHtml(value, labels)
      last.current = value
    }
  }, [value, labels, ref])

  const emit = () => {
    const s = serializeNode(ref.current)
    last.current = s
    onChange(s)
  }
  const onDrop = (e) => {
    e.preventDefault()
    const token = e.dataTransfer.getData('text/plain')
    const label = e.dataTransfer.getData('application/x-chip-label')
    if (!token) return
    const root = ref.current
    let range = null
    if (document.caretRangeFromPoint) {
      range = document.caretRangeFromPoint(e.clientX, e.clientY)
    } else if (document.caretPositionFromPoint) {
      const pos = document.caretPositionFromPoint(e.clientX, e.clientY)
      if (pos) { range = document.createRange(); range.setStart(pos.offsetNode, pos.offset); range.collapse(true) }
    }
    if (range && root && root.contains(range.startContainer)) {
      const sel = window.getSelection()
      sel.removeAllRanges()
      sel.addRange(range)
    }
    insertPillAtCaret(root, token, label || labels[token] || token)
    emit()
  }
  return (
    <div
      ref={ref}
      role="textbox"
      aria-label={ariaLabel}
      contentEditable
      suppressContentEditableWarning
      onInput={emit}
      onBlur={emit}
      onDrop={onDrop}
      onDragOver={(e) => e.preventDefault()}
      className={`flex-1 bg-white/5 border border-space-border rounded px-2 py-1 text-sm text-space-text ${extraClass}`}
      style={{ whiteSpace: 'pre-wrap', minHeight: '2.5rem' }}
    />
  )
}

// Two-column prompt editor (3:1): the contenteditable surface on the left, the
// context-injection folder tray on the right. No pop-out — the host modal is the
// full-size surface. Chips/folders insert on click or drag into the editor.
export function PromptField({ value, onChange, tree, ariaLabel, placeholder }) {
  const ref = useRef(null)
  const labels = useMemo(() => buildLabelMap(tree), [tree])
  const groups = useMemo(() => buildChipGroups(tree), [tree])
  const insert = (token, display) => {
    insertPillAtCaret(ref.current, token, display || labels[token] || token)
    onChange(serializeNode(ref.current))
  }
  return (
    <div data-tour="section-prompt" className="grid grid-cols-4 gap-3 items-start">
      <div className="col-span-3 flex flex-col gap-1.5">
        <Editor
          value={value} onChange={onChange} tree={tree}
          ariaLabel={ariaLabel} editorRef={ref} extraClass="min-h-[16rem]"
        />
        {placeholder && !value && <p className="text-xs text-space-dim/70">{placeholder}</p>}
      </div>
      <div className="col-span-1">
        <ChipTray groups={groups} onInsert={insert} />
      </div>
    </div>
  )
}
