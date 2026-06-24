import { useState } from 'react'
import { FieldWidget } from '../profile-tree/fieldWidgets'
import { setFieldValue, anchorLabel, sectionLocked } from './docTreeOps'

function FieldRow({ root, field, onSave, notes, setNote }) {
  const [open, setOpen] = useState(false)
  const locked = sectionLocked(root, field.id)
  const note = notes[field.id]?.note || ''
  return (
    <div className="mb-3">
      <div className="flex items-center justify-between gap-2">
        <label className="text-xs text-space-dim">{field.name}</label>
        {!locked && (
          <button
            type="button" aria-label={`Feedback on ${anchorLabel(root, field.id)}`}
            className="text-space-dim hover:text-purple-300 text-xs"
            onClick={() => setOpen((v) => !v)}
          >💬</button>
        )}
      </div>
      <FieldWidget
        field={field} onChange={locked ? undefined : (v) => onSave(setFieldValue(root, field.id, v))}
        readOnly={locked} valueOnly
      />
      {open && !locked && (
        <textarea
          className="mt-1 w-full bg-white/5 border border-space-border rounded px-2 py-1 text-xs text-space-text"
          placeholder="What should change here?" value={note}
          onChange={(e) => setNote(field.id, {
            section: undefined,
            label: anchorLabel(root, field.id),
            note: e.target.value,
          })}
        />
      )}
    </div>
  )
}

function fieldsOf(node) {
  if (node.type === 'field') return [node]
  if (node.type === 'group') return node.children || []
  if (node.type === 'list') return (node.children || []).flatMap((g) => g.children || [])
  return []
}

function SectionBlock({ root, section, onSave, notes, setNote, sectionNote, setSectionNote }) {
  const locked = !!section.locked
  const [open, setOpen] = useState(false)
  return (
    <section className="mb-6">
      <div className="flex items-center justify-between gap-2 border-b border-space-border mb-2">
        <h3 className="text-sm font-semibold text-space-text">{section.name}</h3>
        {!locked && (
          <button
            type="button" aria-label={`Feedback on ${section.name}`}
            className="text-space-dim hover:text-purple-300 text-xs"
            onClick={() => setOpen((v) => !v)}
          >💬</button>
        )}
      </div>
      {open && !locked && (
        <textarea
          className="mb-2 w-full bg-white/5 border border-space-border rounded px-2 py-1 text-xs text-space-text"
          placeholder="What should change in this section?"
          value={sectionNote?.note || ''}
          onChange={(e) => setSectionNote(section.id, {
            section: section.name, label: section.name, note: e.target.value,
          })}
        />
      )}
      {(section.children || []).flatMap(fieldsOf).map((f) => (
        <FieldRow key={f.id} root={root} field={f} onSave={onSave} notes={notes} setNote={setNote} />
      ))}
    </section>
  )
}

export default function DocumentTree({ doc, onSave, notes, setNote }) {
  return (
    <div>
      {(doc.children || []).map((section) => (
        <SectionBlock
          key={section.id} root={doc} section={section}
          onSave={onSave} notes={notes}
          setNote={(fieldId, n) => setNote(fieldId, { ...n, section: section.name })}
          sectionNote={notes[section.id]}
          setSectionNote={setNote}
        />
      ))}
    </div>
  )
}
