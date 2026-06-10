import { useEffect, useState } from 'react'
import ResumeSection, { ItemRow } from './ResumeSection'
import {
  ProfileDisplay, ExperienceDisplay, EducationDisplay, ProjectDisplay, SkillsGroupDisplay, itemLabel,
} from './items'
import ItemPopover from './ItemPopover'
import ItemEditor from './ItemEditor'
import './highlight.css'

const DISPLAY = {
  summary: ProfileDisplay,
  experience: ExperienceDisplay,
  education: EducationDisplay,
  project: ProjectDisplay,
  skills: SkillsGroupDisplay,
}

const FEEDBACK_CLS =
  'w-full text-xs rounded bg-[#0a0a1a] border border-space-border text-space-text p-2 focus:border-purple-500 outline-none'

// Render the structured résumé. `onSave(section, index, newValue)` persists an
// edit (returns a Promise). `notes`/`setNote` form a controlled per-item feedback
// store owned by the modal (keyed `${section}:${index}`).
export default function InteractiveResume({ doc, onSave, notes, setNote, escapeRef }) {
  // active = { section, index } whose popover is open; editing = same shape when in edit mode.
  const [active, setActive] = useState(null)
  const [editing, setEditing] = useState(null)
  const [feedbackFor, setFeedbackFor] = useState(null) // { section, index } showing a feedback box
  const noteKey = (s, i) => `${s}:${i}`

  // Let the modal's Escape handler exit an open editor or feedback box before it
  // falls back to closing the modal.
  useEffect(() => {
    if (!escapeRef) return undefined
    escapeRef.current = () => {
      if (editing) { setEditing(null); return true }
      if (feedbackFor) { setFeedbackFor(null); return true }
      return false
    }
    return () => { if (escapeRef) escapeRef.current = null }
  }, [escapeRef, editing, feedbackFor])

  if (!doc) return null

  const isActive = (s, i) => active && active.section === s && active.index === i
  const isEditing = (s, i) => editing && editing.section === s && editing.index === i

  const renderItem = (section, index, value) => {
    const Display = DISPLAY[section]
    if (isEditing(section, index)) {
      return (
        <ItemEditor
          section={section}
          value={value}
          onCancel={() => setEditing(null)}
          onCommit={async (newValue) => {
            try {
              await onSave(section, index, newValue)
              setEditing(null)
              setActive(null)
              setFeedbackFor((f) => (f && f.section === section && f.index === index ? null : f))
            } catch {
              // Save failed — keep the editor open so the user doesn't lose their edit.
            }
          }}
        />
      )
    }
    const key = noteKey(section, index)
    const feedbackOpen = feedbackFor && feedbackFor.section === section && feedbackFor.index === index
    return (
      <div className="flex flex-col gap-1">
        {/* Popover sits to the RIGHT of the item, not below it. */}
        <div className="flex items-start gap-2">
          <div className="flex-1 min-w-0">
            <ItemRow onClick={() => setActive(isActive(section, index) ? null : { section, index })}>
              <Display value={value} />
            </ItemRow>
          </div>
          {isActive(section, index) && (
            <ItemPopover
              onEdit={() => {
                if (feedbackOpen) setFeedbackFor(null)
                setEditing({ section, index })
              }}
              onFeedback={() => { setFeedbackFor({ section, index }); setActive(null) }}
              onClose={() => setActive(null)}
            />
          )}
        </div>
        {feedbackOpen || notes[key] ? (
          <textarea
            rows={2}
            autoFocus={!!feedbackOpen}
            placeholder="Feedback for regeneration…"
            value={notes[key]?.note || ''}
            onChange={(e) => setNote(key, { section, label: itemLabel(section, index, value), note: e.target.value })}
            className={FEEDBACK_CLS}
          />
        ) : null}
      </div>
    )
  }

  // A section whose title is clickable for section-level (Feedback-only) notes.
  const renderSection = (sectionKey, title, children) => {
    const skey = noteKey(sectionKey, 'section')
    const sActive = isActive(sectionKey, 'section')
    const sFeedbackOpen = feedbackFor && feedbackFor.section === sectionKey && feedbackFor.index === 'section'
    return (
      <ResumeSection
        title={title}
        onTitleClick={() => setActive(sActive ? null : { section: sectionKey, index: 'section' })}
        titlePopover={sActive ? (
          <ItemPopover
            onFeedback={() => { setFeedbackFor({ section: sectionKey, index: 'section' }); setActive(null) }}
            onClose={() => setActive(null)}
          />
        ) : null}
        feedbackBox={sFeedbackOpen || notes[skey] ? (
          <textarea
            rows={2}
            autoFocus={!!sFeedbackOpen}
            placeholder={`Feedback for the whole ${title} section…`}
            value={notes[skey]?.note || ''}
            onChange={(e) => setNote(skey, { section: sectionKey, label: `${title} section`, note: e.target.value })}
            className={`${FEEDBACK_CLS} mb-2`}
          />
        ) : null}
      >
        {children}
      </ResumeSection>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      {doc.profile_summary ? (
        <ResumeSection title="Profile">{renderItem('summary', 0, doc.profile_summary)}</ResumeSection>
      ) : null}
      {doc.experience?.length ? renderSection('experience', 'Experience',
        doc.experience.map((e, i) => <div key={i}>{renderItem('experience', i, e)}</div>)
      ) : null}
      {doc.education?.length ? renderSection('education', 'Education',
        doc.education.map((ed, i) => <div key={i}>{renderItem('education', i, ed)}</div>)
      ) : null}
      {doc.projects?.length ? renderSection('project', 'Projects',
        doc.projects.map((p, i) => <div key={i}>{renderItem('project', i, p)}</div>)
      ) : null}
      {doc.skills?.length ? renderSection('skills', 'Skills',
        doc.skills.map((g, i) => <div key={i}>{renderItem('skills', i, g)}</div>)
      ) : null}
    </div>
  )
}
