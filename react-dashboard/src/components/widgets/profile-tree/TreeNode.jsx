import { useState, useEffect } from 'react'
import { getOutputFormats } from '../../../api'
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

// Module-level cache so every field doesn't refetch the small registry.
let _formatsCache = null
function useOutputFormats() {
  const [formats, setFormats] = useState(_formatsCache || [])
  useEffect(() => {
    if (_formatsCache) return
    const p = getOutputFormats()
    if (!p || typeof p.then !== 'function') return
    p.then((f) => { _formatsCache = f; setFormats(f) }).catch(() => {})
  }, [])
  return formats
}

// A single field: label (renamable only on custom groups) + eye (render) +
// lock (LLM may write) + widget. When the LLM may write the field, a 💬 control
// opens the prompt modal (bound to llm_instructions) — same idiom as section/item
// prompts. The lock and eye are the two value controls: lock = "can the LLM
// change this value?", eye = "does this value appear in the output document?".
function FieldView({ field, fieldsEditable, ops, tree }) {
  const written = !!field.llm_output
  const [promptOpen, setPromptOpen] = useState(false)
  const formats = useOutputFormats()
  const isProse = field.kind === 'markdown' || field.kind === 'bullets'
  return (
    <div className={rowWrap}>
      <div className={headerRow}>
        <RenameLabel
          name={field.name} editable={fieldsEditable}
          onRename={(n) => ops.rename(field.id, n)}
        />
        <span className="inline-flex items-center gap-1">
          <LlmWriteToggle written={written} onToggle={() => ops.toggleWritten(field.id)} />
          <VisibleToggle visible={field.visible} onToggle={() => ops.toggleVisible(field.id)} label="in output" />
          {written && isProse && formats.length > 0 && (
            <select
              data-tour="output-format"
              aria-label="Output format"
              className="bg-white/5 border border-space-border rounded text-xs text-space-text px-1 py-0.5"
              value={field.output_format || ''}
              onChange={(e) => {
                const fmt = formats.find((x) => x.id === e.target.value)
                if (fmt) ops.setOutputFormat(field.id, fmt.id, fmt.kind)
              }}
            >
              {!field.output_format && <option value="">Format…</option>}
              {formats.map((f) => (
                <option key={f.id} value={f.id}>{f.label}</option>
              ))}
            </select>
          )}
          {written && (
            <button
              type="button" aria-label="Edit field prompt" title="Field prompt"
              className="px-1.5 py-0.5 text-space-dim hover:text-space-text transition-colors"
              onClick={() => setPromptOpen(true)}
            >💬</button>
          )}
        </span>
      </div>
      <div className={field.visible ? '' : 'opacity-50'}>
        <FieldWidget field={field} onChange={(v) => ops.setValue(field.id, v)} />
      </div>
      {promptOpen && (
        <PromptEditorModal
          node={field} isSection={false} label="Field"
          value={field.llm_instructions || ''} tree={tree}
          onChange={(t) => ops.setInstructions(field.id, t)}
          onClose={() => setPromptOpen(false)}
        />
      )}
    </div>
  )
}

// A group's fields. `fieldsEditable` enables rename + add/remove field (custom
// only). Single-line text fields pack two-to-a-row (Company | Title, Start | End);
// multi-line kinds (markdown/bullets/taglist) span the full width.
function GroupView({ group, fieldsEditable, ops, tree }) {
  return (
    <div className="grid grid-cols-2 gap-x-4 gap-y-3">
      {group.children.map((f) => (
        <div
          key={f.id}
          className={`flex items-start gap-2 ${f.kind === 'text' ? '' : 'col-span-2'}`}
        >
          <div className="flex-1 min-w-0">
            <FieldView field={f} fieldsEditable={fieldsEditable} ops={ops} tree={tree} />
          </div>
          {fieldsEditable && (
            <RemoveButton onRemove={() => ops.remove(f.id)} label="Remove field" />
          )}
        </div>
      ))}
      {fieldsEditable && (
        <div className="col-span-2"><AddFieldForm groupId={group.id} ops={ops} /></div>
      )}
    </div>
  )
}

function AddFieldForm({ groupId, ops }) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [kind, setKind] = useState('text')
  if (!open) return (
    <span data-tour="add-field" className="inline-flex">
      <AddButton label="+ Add field" onClick={() => setOpen(true)} />
    </span>
  )
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
function SortableEntry({ item, index, ops, tree, sectionLocked }) {
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
          <button
            type="button"
            aria-label={locked ? 'Unlock item for LLM' : 'Lock item from LLM'}
            title={locked ? 'Locked — LLM leaves this entry as typed' : 'LLM may tailor this entry'}
            className="px-1.5 py-0.5 text-space-dim hover:text-space-text transition-colors"
            onClick={() => ops.toggleLocked(item.id)}
          >{locked ? '🔒' : '🔓'}</button>
          <VisibleToggle visible={item.visible} onToggle={() => ops.toggleVisible(item.id)} label="item in output" />
          <button
            type="button" aria-label="Edit item prompt" title="Item prompt"
            className="px-1.5 py-0.5 text-space-dim hover:text-space-text transition-colors"
            onClick={() => setPromptOpen(true)}
          >💬</button>
          <RemoveButton onRemove={() => ops.remove(item.id)} label="Remove item" />
        </span>
      </div>
      {!collapsed && <GroupView group={item} fieldsEditable={false} ops={ops} tree={tree} />}
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
              key={item.id} item={item} index={i} ops={ops}
              tree={tree} sectionLocked={sectionLocked}
            />
          ))}
        </SortableContext>
      </DndContext>
      <span data-tour="add-field" className="inline-flex">
        <AddButton label="+ Add entry" onClick={() => ops.addItem(list.id)} />
      </span>
    </div>
  )
}

// The single child of a section is a group, list, or field.
function SectionChild({ child, ops, tree, sectionLocked }) {
  if (child.type === 'list') return <ListView list={child} ops={ops} tree={tree} sectionLocked={sectionLocked} />
  if (child.type === 'group') return <GroupView group={child} fieldsEditable ops={ops} tree={tree} />
  // bare field child (e.g. summary hero, skills taglist)
  return <FieldView field={child} fieldsEditable={false} ops={ops} tree={tree} />
}

// A list section with at least one entry, all of whose entries are locked, is
// effectively locked: the LLM would tailor nothing in it.
function allEntriesLocked(section) {
  const child = section.children?.[0]
  if (!child || child.type !== 'list') return false
  const entries = child.children || []
  return entries.length > 0 && entries.every((e) => e.locked)
}

export function SectionView({ section, isFirst, isLast, ops, dragHandle, tree, initialCollapsed = true }) {
  const preset = isPresetSection(section)
  const child = section.children[0]
  const [collapsed, setCollapsed] = useState(initialCollapsed)
  const [promptOpen, setPromptOpen] = useState(false)
  const toggle = () => setCollapsed((c) => {
    // Announce expansion so the onboarding tour can advance past "open a section".
    if (c) window.dispatchEvent(new CustomEvent('auto-apply:section-expanded'))
    return !c
  })
  const locked = !!section.locked
  // Glyph reflects effective lock (explicit OR every entry locked); the toggle
  // and its aria-label stay bound to the explicit section.locked flag.
  const effLocked = locked || allEntriesLocked(section)
  return (
    <div data-tour="profile-section" className={`border border-space-border rounded-xl p-4 flex flex-col gap-3 ${section.visible ? '' : 'opacity-60'}`}>
      <div className={`${headerRow} cursor-pointer`} onClick={toggle}>
        <span className="inline-flex items-center gap-2">
          {dragHandle}
          <RenameLabel name={section.name} editable onRename={(n) => ops.rename(section.id, n)} />
        </span>
        <span className="inline-flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
          <button
            type="button"
            data-tour="section-lock"
            aria-label={locked ? 'Unlock section for LLM' : 'Lock section from LLM'}
            title={
              locked ? 'Locked — LLM leaves this section as typed'
                : effLocked ? 'All entries are locked — section is effectively locked'
                  : 'LLM may tailor this section'
            }
            className="px-1.5 py-0.5 text-space-dim hover:text-space-text transition-colors"
            onClick={() => ops.toggleLocked(section.id)}
          >{effLocked ? '🔒' : '🔓'}</button>
          <span data-tour="section-visible" className="inline-flex">
            <VisibleToggle visible={section.visible} onToggle={() => ops.toggleVisible(section.id)} label="section" />
          </span>
          <button
            type="button" aria-label="Edit section prompt" title="Section prompt"
            data-tour="section-prompt"
            className="px-1.5 py-0.5 text-space-dim hover:text-space-text transition-colors"
            onClick={() => setPromptOpen(true)}
          >💬</button>
          {!preset && <RemoveButton onRemove={() => ops.remove(section.id)} label="Remove section" />}
        </span>
      </div>
      {!collapsed && child && (
        <SectionChild child={child} ops={ops} tree={tree} sectionLocked={locked} />
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
