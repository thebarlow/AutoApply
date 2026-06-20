import { useState, useEffect, useCallback } from 'react'
import { getProfileTree, putProfileTree } from '../../../api'
import { SectionView } from './TreeNode'
import {
  updateNode, removeNode, moveNode, addField, addListItem, addSection, reorderSiblings,
} from './treeOps'
import { SectionGallery } from './SectionGallery'
import { SECTION_TEMPLATES, buildSectionFromTemplate } from './sectionCatalog'
import {
  DndContext, closestCenter, PointerSensor, KeyboardSensor, useSensor, useSensors,
} from '@dnd-kit/core'
import {
  SortableContext, verticalListSortingStrategy, useSortable, sortableKeyboardCoordinates,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'

export default function ProfileTreeEditor({ profileId }) {
  const [tree, setTree] = useState(null)
  const [saved, setSaved] = useState(null) // last-persisted snapshot for Discard
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true); setLoadError(null)
    getProfileTree(profileId)
      .then(({ tree: t }) => { if (!cancelled) { setTree(t); setSaved(t) } })
      .catch(() => { if (!cancelled) setLoadError('Failed to load profile') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [profileId])

  const dirty = tree !== saved

  // Handler bundle passed to SectionView; all address nodes by id.
  const ops = {
    setValue: useCallback((id, value) => setTree((t) => updateNode(t, id, (n) => ({ ...n, value }))), []),
    rename: useCallback((id, name) => setTree((t) => updateNode(t, id, (n) => ({ ...n, name }))), []),
    toggleVisible: useCallback((id) => setTree((t) => updateNode(t, id, (n) => ({ ...n, visible: !n.visible }))), []),
    remove: useCallback((id) => setTree((t) => removeNode(t, id)), []),
    move: useCallback((id, delta) => setTree((t) => moveNode(t, id, delta)), []),
    addItem: useCallback((listId) => setTree((t) => addListItem(t, listId)), []),
    addField: useCallback((groupId, spec) => setTree((t) => addField(t, groupId, spec)), []),
    reorder: useCallback((activeId, overId) => setTree((t) => reorderSiblings(t, activeId, overId)), []),
  }

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )
  const handleDragEnd = ({ active, over }) => {
    if (over && active.id !== over.id) ops.reorder(active.id, over.id)
  }

  const handleSave = async () => {
    setSaving(true); setSaveError(null)
    try {
      const { tree: persisted } = await putProfileTree(profileId, tree)
      setTree(persisted); setSaved(persisted)
    } catch (e) {
      const is422 = String(e?.message || '').includes('422')
      setSaveError(
        is422
          ? 'Your changes could not be saved — the profile structure is invalid (e.g. duplicate field names, size limits, or an unsupported change).'
          : 'Save failed. Please try again.',
      )
    } finally {
      setSaving(false)
    }
  }

  const handleDiscard = () => { setTree(saved); setSaveError(null) }

  if (loading) return <p className="text-xs text-space-dim">Loading…</p>
  if (loadError) return <p className="text-xs text-red-400">{loadError}</p>
  if (!tree) return null

  const sections = tree.children
  return (
    <div className="flex flex-col gap-3">
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={sections.map((s) => s.id)} strategy={verticalListSortingStrategy}>
          {sections.map((section, i) => (
            <SortableSection
              key={section.id} section={section}
              isFirst={i === 0} isLast={i === sections.length - 1} ops={ops}
            />
          ))}
        </SortableContext>
      </DndContext>

      <SectionGallery
        templates={SECTION_TEMPLATES}
        onAdd={(tpl) => setTree((t) => addSection(t, buildSectionFromTemplate(tpl)))}
      />

      {saveError && <p className="text-xs text-red-400">{saveError}</p>}

      <div className="sticky bottom-0 flex items-center gap-2 bg-[#0f0f1a]/90 backdrop-blur py-2">
        <button
          type="button" onClick={handleSave} disabled={!dirty || saving}
          className="px-4 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold transition-colors"
        >{saving ? 'Saving…' : 'Save'}</button>
        <button
          type="button" onClick={handleDiscard} disabled={!dirty || saving}
          className="px-4 py-2 rounded-lg border border-space-border text-sm text-space-dim hover:text-space-text disabled:opacity-40 transition-colors"
        >Discard</button>
        {dirty && <span className="text-xs text-space-dim">Unsaved changes</span>}
      </div>
    </div>
  )
}

function SortableSection({ section, isFirst, isLast, ops }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: section.id })
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  }
  const handle = (
    <button
      type="button" aria-label="Drag to reorder section"
      className="cursor-grab active:cursor-grabbing px-1 text-space-dim hover:text-space-text"
      {...attributes} {...listeners}
    >⋮⋮</button>
  )
  return (
    <div ref={setNodeRef} style={style}>
      <SectionView
        section={section} isFirst={isFirst} isLast={isLast} ops={ops} dragHandle={handle}
      />
    </div>
  )
}
