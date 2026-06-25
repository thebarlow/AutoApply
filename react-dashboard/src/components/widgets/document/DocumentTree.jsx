import { useState } from 'react'
import { FieldWidget } from '../profile-tree/fieldWidgets'
import { setFieldValue } from './docTreeOps'

// First non-empty descendant field value → a collapsed entry's preview label.
function entrySummary(entry) {
  for (const f of entry.children || []) {
    if (typeof f.value === 'string' && f.value.trim()) return f.value.trim()
    if (Array.isArray(f.value) && f.value.length) return f.value.join(', ')
  }
  return ''
}

function FeedbackButton({ label, onToggle }) {
  return (
    <button
      type="button" aria-label={`Feedback on ${label}`}
      className="text-space-dim hover:text-purple-300 text-xs shrink-0"
      onClick={(e) => { e.stopPropagation(); onToggle() }}
    >💬</button>
  )
}

function NoteBox({ value, placeholder, onChange }) {
  return (
    <textarea
      className="mt-1 mb-1 w-full bg-white/5 border border-space-border rounded px-2 py-1 text-xs text-space-text"
      placeholder={placeholder} value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  )
}

// 2-col grid: single-line text fields share rows; multi-line kinds span full width.
function GroupGrid({ root, fields, locked, onSave }) {
  return (
    <div className="grid grid-cols-2 gap-x-4 gap-y-3">
      {fields.map((f) => (
        <div key={f.id} className={f.kind === 'text' ? '' : 'col-span-2'}>
          <label className="text-xs text-space-dim">{f.name}</label>
          <FieldWidget
            field={f}
            onChange={locked ? undefined : (v) => onSave(setFieldValue(root, f.id, v))}
            readOnly={locked} valueOnly
          />
        </div>
      ))}
    </div>
  )
}

// One list entry → its own collapsible sub-card with a summary label + feedback.
function EntryCard({ root, entry, sectionName, locked, onSave, notes, setNote }) {
  const [collapsed, setCollapsed] = useState(true)
  const [fbOpen, setFbOpen] = useState(false)
  const label = entry.name || entrySummary(entry) || 'Entry'
  const note = notes[entry.id]?.note || ''
  return (
    <div className="border border-space-border/50 rounded-lg p-3 flex flex-col gap-2">
      <div
        className="flex items-center justify-between gap-2 cursor-pointer"
        onClick={() => setCollapsed((c) => !c)}
      >
        <span className="text-xs text-space-text truncate">{label}</span>
        {!locked && <FeedbackButton label={label} onToggle={() => setFbOpen((v) => !v)} />}
      </div>
      {fbOpen && !locked && (
        <NoteBox
          value={note} placeholder="What should change in this entry?"
          onChange={(t) => setNote(entry.id, { section: sectionName, label, note: t })}
        />
      )}
      {!collapsed && <GroupGrid root={root} fields={entry.children || []} locked={locked} onSave={onSave} />}
    </div>
  )
}

// A section's single child: bare field, group, or list of entries.
function SectionBody({ root, section, locked, onSave, notes, setNote }) {
  const child = (section.children || [])[0]
  if (!child) return null
  if (child.type === 'list') {
    return (
      <div className="flex flex-col gap-3">
        {(child.children || []).map((entry) => (
          <EntryCard
            key={entry.id} root={root} entry={entry} sectionName={section.name}
            locked={locked || !!entry.locked} onSave={onSave} notes={notes} setNote={setNote}
          />
        ))}
      </div>
    )
  }
  if (child.type === 'group') {
    return <GroupGrid root={root} fields={child.children || []} locked={locked} onSave={onSave} />
  }
  return <GroupGrid root={root} fields={[child]} locked={locked} onSave={onSave} />
}

function SectionCard({ root, section, onSave, notes, setNote }) {
  const [collapsed, setCollapsed] = useState(true)
  const [fbOpen, setFbOpen] = useState(false)
  const locked = !!section.locked
  const note = notes[section.id]?.note || ''
  return (
    <div className="border border-space-border rounded-xl p-4 flex flex-col gap-3 mb-4">
      <div
        className="flex items-center justify-between gap-2 cursor-pointer border-b border-space-border pb-2"
        onClick={() => setCollapsed((c) => !c)}
      >
        <h3 className="text-sm font-semibold text-space-text">{section.name}</h3>
        {!locked && <FeedbackButton label={section.name} onToggle={() => setFbOpen((v) => !v)} />}
      </div>
      {fbOpen && !locked && (
        <NoteBox
          value={note} placeholder="What should change in this section?"
          onChange={(t) => setNote(section.id, { section: section.name, label: section.name, note: t })}
        />
      )}
      {!collapsed && (
        <SectionBody root={root} section={section} locked={locked} onSave={onSave} notes={notes} setNote={setNote} />
      )}
    </div>
  )
}

export default function DocumentTree({ doc, onSave, notes, setNote }) {
  return (
    <div>
      {(doc.children || []).map((section) => (
        <SectionCard
          key={section.id} root={doc} section={section}
          onSave={onSave} notes={notes} setNote={setNote}
        />
      ))}
    </div>
  )
}
