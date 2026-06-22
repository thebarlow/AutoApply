import { useState } from 'react'
import {
  DndContext, closestCenter, PointerSensor, KeyboardSensor, useSensor, useSensors,
} from '@dnd-kit/core'
import {
  SortableContext, verticalListSortingStrategy, useSortable, sortableKeyboardCoordinates,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { FieldWidget } from './fieldWidgets'
import { VisibleToggle, RenameLabel, RemoveButton, AddButton, LlmWriteToggle } from './structuralControls'
import { isPresetSection } from './treeOps'
import { PromptEditorModal } from './PromptEditorModal'


const rowWrap = 'flex flex-col gap-1'
const headerRow = 'flex items-center justify-between gap-2'

// A single field: label (renamable only on custom groups) + eye (render) +
// lock (LLM may write) + widget, then the LLM instructions box when unlocked.
// The lock and eye are the two field controls: lock = "can the LLM change this
// value?", eye = "does this value appear in the output document?".
function FieldView({ field, fieldsEditable, ops }) {
  const written = !!field.llm_output
  return (
    <div className={rowWrap}>
      <div className={headerRow}>
        <RenameLabel
          name={field.name} editable={fieldsEditable}
          onRename={(n) => ops.rename(field.id, n)}
        />
        <span className="inline-flex items-center">
          <LlmWriteToggle written={written} onToggle={() => ops.toggleWritten(field.id)} />
          <VisibleToggle visible={field.visible} onToggle={() => ops.toggleVisible(field.id)} label="in output" />
        </span>
      </div>
      <div className={field.visible ? '' : 'opacity-50'}>
        <FieldWidget field={field} onChange={(v) => ops.setValue(field.id, v)} />
      </div>
      {written && (
        <textarea
          aria-label="LLM instructions" rows={2}
          placeholder="How should the LLM write this field?"
          value={field.llm_instructions || ''}
          className="bg-white/5 border border-space-border rounded px-2 py-1 text-sm text-space-text"
          onChange={(e) => ops.setInstructions(field.id, e.target.value)}
        />
      )}
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

// First non-empty field value, used as a collapsed entry's preview label so it
// stays identifiable while reordering.
function entrySummary(item) {
  for (const f of item.children) {
    if (typeof f.value === 'string' && f.value.trim()) return f.value.trim()
    if (Array.isArray(f.value) && f.value.length) return f.value.join(', ')
  }
  return ''
}

// One list entry, made sortable. Collapsed by default; body-click on the
// header bar toggles expand; drag-handle-only reorder.
function SortableEntry({ item, index, count, ops, tree, sectionLocked }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: item.id })
  const [collapsed, setCollapsed] = useState(true)
  const [promptOpen, setPromptOpen] = useState(false)
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  }
  const summary = entrySummary(item)
  const locked = !!item.locked
  const toggle = () => setCollapsed((c) => !c)
  return (
    <div
      ref={setNodeRef} style={style}
      className="border border-space-border/50 rounded-lg p-3 flex flex-col gap-2"
    >
      <div className={`${headerRow} cursor-pointer`} onClick={toggle} aria-label="Toggle entry">
        <span className="inline-flex items-center gap-2 min-w-0" onClick={(e) => e.stopPropagation()}>
          <button
            type="button" aria-label="Drag to reorder item"
            className="cursor-grab active:cursor-grabbing px-1 text-space-dim hover:text-space-text"
            {...attributes} {...listeners}
          >⋮⋮</button>
          <RenameLabel name={item.name || `Entry ${index + 1}`} editable onRename={(n) => ops.rename(item.id, n)} />
          {collapsed && !item.name && summary && (
            <span className="text-xs text-space-text truncate">— {summary}</span>
          )}
        </span>
        <span className="inline-flex items-center" onClick={(e) => e.stopPropagation()}>
          {!sectionLocked && (
            <button
              type="button"
              aria-label={locked ? 'Unlock item for LLM' : 'Lock item from LLM'}
              title={locked ? 'Locked — LLM leaves this entry as typed' : 'LLM may tailor this entry'}
              className="px-1.5 py-0.5 text-space-dim hover:text-space-text transition-colors"
              onClick={() => ops.toggleLocked(item.id)}
            >{locked ? '🔒' : '🔓'}</button>
          )}
          <VisibleToggle visible={item.visible} onToggle={() => ops.toggleVisible(item.id)} label="item in output" />
          {!sectionLocked && (
            <button
              type="button" aria-label="Edit item prompt" title="Item prompt"
              className="px-1.5 py-0.5 text-space-dim hover:text-space-text transition-colors"
              onClick={() => setPromptOpen(true)}
            >✉</button>
          )}
          <RemoveButton onRemove={() => ops.remove(item.id)} label="Remove item" />
        </span>
      </div>
      {!collapsed && <GroupView group={item} fieldsEditable={false} ops={ops} />}
      {promptOpen && (
        <PromptEditorModal
          node={item} isSection={false} tree={tree}
          onChange={(t) => ops.setPrompt(item.id, t)}
          onClose={() => setPromptOpen(false)}
        />
      )}
    </div>
  )
}

// A repeating list: each item is a fixed-shape group (no field add/remove);
// items can be added (clone template), removed, reordered (drag).
function ListView({ list, ops, tree, sectionLocked }) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
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
              tree={tree} sectionLocked={sectionLocked}
            />
          ))}
        </SortableContext>
      </DndContext>
      <AddButton label="+ Add entry" onClick={() => ops.addItem(list.id)} />
    </div>
  )
}

// The single child of a section is a group, list, or field.
function SectionChild({ child, preset, ops, tree, sectionLocked }) {
  if (child.type === 'list') return <ListView list={child} ops={ops} tree={tree} sectionLocked={sectionLocked} />
  if (child.type === 'group') return <GroupView group={child} fieldsEditable={!preset} ops={ops} />
  // bare field child (e.g. summary hero, skills taglist)
  return <FieldView field={child} fieldsEditable={false} ops={ops} />
}

export function SectionView({ section, isFirst, isLast, ops, dragHandle, tree, initialCollapsed = true }) {
  const preset = isPresetSection(section)
  const child = section.children[0]
  const [collapsed, setCollapsed] = useState(initialCollapsed)
  const [promptOpen, setPromptOpen] = useState(false)
  const toggle = () => setCollapsed((c) => !c)
  const locked = !!section.locked
  return (
    <div className={`border border-space-border rounded-xl p-4 flex flex-col gap-3 ${section.visible ? '' : 'opacity-60'}`}>
      <div className={`${headerRow} cursor-pointer`} onClick={toggle}>
        <span className="inline-flex items-center gap-2">
          {dragHandle}
          <RenameLabel name={section.name} editable onRename={(n) => ops.rename(section.id, n)} />
        </span>
        <span className="inline-flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
          <button
            type="button"
            aria-label={locked ? 'Unlock section for LLM' : 'Lock section from LLM'}
            title={locked ? 'Locked — LLM leaves this section as typed' : 'LLM may tailor this section'}
            className="px-1.5 py-0.5 text-space-dim hover:text-space-text transition-colors"
            onClick={() => ops.toggleLocked(section.id)}
          >{locked ? '🔒' : '🔓'}</button>
          <VisibleToggle visible={section.visible} onToggle={() => ops.toggleVisible(section.id)} label="section" />
          <button
            type="button" aria-label="Edit section prompt" title="Section prompt"
            className="px-1.5 py-0.5 text-space-dim hover:text-space-text transition-colors"
            onClick={() => setPromptOpen(true)}
          >✉</button>
          {!preset && <RemoveButton onRemove={() => ops.remove(section.id)} label="Remove section" />}
        </span>
      </div>
      {!collapsed && child && (
        <SectionChild child={child} preset={preset} ops={ops} tree={tree} sectionLocked={locked} />
      )}
      {promptOpen && (
        <PromptEditorModal
          node={section} isSection tree={tree}
          onChange={(t) => ops.setPrompt(section.id, t)}
          onClose={() => setPromptOpen(false)}
        />
      )}
    </div>
  )
}
