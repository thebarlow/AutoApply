import { useState } from 'react'
import { FieldWidget } from './fieldWidgets'
import { MoveButtons, VisibleToggle, RenameLabel, RemoveButton, AddButton } from './structuralControls'
import { isPresetSection } from './treeOps'

const rowWrap = 'flex flex-col gap-1'
const headerRow = 'flex items-center justify-between gap-2'

// A single field: label (renamable only on custom groups) + visible + widget.
function FieldView({ field, fieldsEditable, ops }) {
  return (
    <div className={rowWrap}>
      <div className={headerRow}>
        <RenameLabel
          name={field.name} editable={fieldsEditable}
          onRename={(n) => ops.rename(field.id, n)}
        />
        <VisibleToggle visible={field.visible} onToggle={() => ops.toggleVisible(field.id)} />
      </div>
      <div className={field.visible ? '' : 'opacity-50'}>
        <FieldWidget field={field} onChange={(v) => ops.setValue(field.id, v)} />
      </div>
    </div>
  )
}

// A group's fields. `fieldsEditable` enables rename + add/remove field (custom only).
function GroupView({ group, fieldsEditable, ops }) {
  return (
    <div className="flex flex-col gap-3">
      {group.children.map((f) => (
        <div key={f.id} className="flex items-start gap-2">
          <div className="flex-1">
            <FieldView field={f} fieldsEditable={fieldsEditable} ops={ops} />
          </div>
          {fieldsEditable && (
            <RemoveButton onRemove={() => ops.remove(f.id)} label="Remove field" />
          )}
        </div>
      ))}
      {fieldsEditable && <AddFieldForm groupId={group.id} ops={ops} />}
    </div>
  )
}

function AddFieldForm({ groupId, ops }) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [kind, setKind] = useState('text')
  if (!open) return <AddButton label="+ Add field" onClick={() => setOpen(true)} />
  return (
    <div className="flex items-center gap-2">
      <input
        type="text" placeholder="Field name" value={name}
        className="bg-white/5 border border-space-border rounded px-2 py-1 text-sm text-space-text"
        onChange={(e) => setName(e.target.value)}
      />
      <select
        value={kind} onChange={(e) => setKind(e.target.value)}
        className="bg-white/5 border border-space-border rounded px-2 py-1 text-sm text-space-text"
      >
        <option value="text">text</option>
        <option value="markdown">markdown</option>
        <option value="bullets">bullets</option>
        <option value="taglist">taglist</option>
      </select>
      <button
        type="button" className="text-xs text-purple-400 hover:text-purple-300"
        onClick={() => { if (name.trim()) { ops.addField(groupId, { name: name.trim(), kind }); setName(''); setOpen(false) } }}
      >Add</button>
      <button
        type="button" className="text-xs text-space-dim hover:text-space-text"
        onClick={() => { setName(''); setOpen(false) }}
      >Cancel</button>
    </div>
  )
}

// A repeating list: each item is a fixed-shape group (no field add/remove);
// items can be added (clone template), removed, and reordered.
function ListView({ list, ops }) {
  return (
    <div className="flex flex-col gap-4">
      {list.children.map((item, i) => (
        <div key={item.id} className="border border-space-border/50 rounded-lg p-3 flex flex-col gap-2">
          <div className={headerRow}>
            <span className="text-xs text-space-dim">Entry {i + 1}</span>
            <span className="inline-flex items-center">
              <MoveButtons
                canUp={i > 0} canDown={i < list.children.length - 1}
                onUp={() => ops.move(item.id, -1)} onDown={() => ops.move(item.id, 1)}
              />
              <RemoveButton onRemove={() => ops.remove(item.id)} label="Remove item" />
            </span>
          </div>
          <GroupView group={item} fieldsEditable={false} ops={ops} />
        </div>
      ))}
      <AddButton label="+ Add entry" onClick={() => ops.addItem(list.id)} />
    </div>
  )
}

// The single child of a section is a group, list, or field.
function SectionChild({ child, preset, ops }) {
  if (child.type === 'list') return <ListView list={child} ops={ops} />
  if (child.type === 'group') return <GroupView group={child} fieldsEditable={!preset} ops={ops} />
  // bare field child (e.g. summary hero, skills taglist)
  return <FieldView field={child} fieldsEditable={false} ops={ops} />
}

export function SectionView({ section, isFirst, isLast, ops }) {
  const preset = isPresetSection(section)
  const child = section.children[0]
  return (
    <div className={`border border-space-border rounded-xl p-4 flex flex-col gap-3 ${section.visible ? '' : 'opacity-60'}`}>
      <div className={headerRow}>
        <RenameLabel
          name={section.name} editable
          onRename={(n) => ops.rename(section.id, n)}
        />
        <span className="inline-flex items-center gap-1">
          <MoveButtons
            canUp={!isFirst} canDown={!isLast}
            onUp={() => ops.move(section.id, -1)} onDown={() => ops.move(section.id, 1)}
          />
          <VisibleToggle visible={section.visible} onToggle={() => ops.toggleVisible(section.id)} />
          {!preset && <RemoveButton onRemove={() => ops.remove(section.id)} label="Remove section" />}
        </span>
      </div>
      {child && <SectionChild child={child} preset={preset} ops={ops} />}
    </div>
  )
}
