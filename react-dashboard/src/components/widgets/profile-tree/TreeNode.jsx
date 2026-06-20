import { useState } from 'react'
import {
  DndContext, closestCenter, PointerSensor, KeyboardSensor, useSensor, useSensors,
} from '@dnd-kit/core'
import {
  SortableContext, verticalListSortingStrategy, useSortable, sortableKeyboardCoordinates,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
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
        <option className="bg-white text-black" value="text">text</option>
        <option className="bg-white text-black" value="markdown">markdown</option>
        <option className="bg-white text-black" value="bullets">bullets</option>
        <option className="bg-white text-black" value="taglist">taglist</option>
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

// One list entry, made sortable. Keeps the ↑/↓ buttons as the a11y fallback.
function SortableEntry({ item, index, count, ops }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: item.id })
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  }
  return (
    <div
      ref={setNodeRef} style={style}
      className="border border-space-border/50 rounded-lg p-3 flex flex-col gap-2"
    >
      <div className={headerRow}>
        <span className="inline-flex items-center gap-2">
          <button
            type="button" aria-label="Drag to reorder item"
            className="cursor-grab active:cursor-grabbing px-1 text-space-dim hover:text-space-text"
            {...attributes} {...listeners}
          >⋮⋮</button>
          <span className="text-xs text-space-dim">Entry {index + 1}</span>
        </span>
        <span className="inline-flex items-center">
          <MoveButtons
            canUp={index > 0} canDown={index < count - 1}
            onUp={() => ops.move(item.id, -1)} onDown={() => ops.move(item.id, 1)}
          />
          <RemoveButton onRemove={() => ops.remove(item.id)} label="Remove item" />
        </span>
      </div>
      <GroupView group={item} fieldsEditable={false} ops={ops} />
    </div>
  )
}

// A repeating list: each item is a fixed-shape group (no field add/remove);
// items can be added (clone template), removed, reordered (drag or ↑/↓).
function ListView({ list, ops }) {
  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )
  const handleDragEnd = ({ active, over }) => {
    if (over && active.id !== over.id) ops.reorder(active.id, over.id)
  }
  return (
    <div className="flex flex-col gap-4">
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={list.children.map((i) => i.id)} strategy={verticalListSortingStrategy}>
          {list.children.map((item, i) => (
            <SortableEntry
              key={item.id} item={item} index={i} count={list.children.length} ops={ops}
            />
          ))}
        </SortableContext>
      </DndContext>
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

export function SectionView({ section, isFirst, isLast, ops, dragHandle }) {
  const preset = isPresetSection(section)
  const child = section.children[0]
  const [collapsed, setCollapsed] = useState(true)
  return (
    <div className={`border border-space-border rounded-xl p-4 flex flex-col gap-3 ${section.visible ? '' : 'opacity-60'}`}>
      <div className={headerRow}>
        <span className="inline-flex items-center gap-2">
          {dragHandle}
          <button
            type="button"
            aria-label={collapsed ? 'Expand section' : 'Collapse section'}
            className="px-1 text-space-dim hover:text-space-text transition-colors"
            onClick={() => setCollapsed((c) => !c)}
          >{collapsed ? '▸' : '▾'}</button>
          <RenameLabel
            name={section.name} editable
            onRename={(n) => ops.rename(section.id, n)}
          />
        </span>
        <span className="inline-flex items-center gap-1">
          <MoveButtons
            canUp={!isFirst} canDown={!isLast}
            onUp={() => ops.move(section.id, -1)} onDown={() => ops.move(section.id, 1)}
          />
          <VisibleToggle visible={section.visible} onToggle={() => ops.toggleVisible(section.id)} label="section" />
          {!preset && <RemoveButton onRemove={() => ops.remove(section.id)} label="Remove section" />}
        </span>
      </div>
      {!collapsed && child && <SectionChild child={child} preset={preset} ops={ops} />}
    </div>
  )
}
