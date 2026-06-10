import { useState } from 'react'
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

// Render the structured résumé. `onSave(section, index, newValue)` persists an
// edit (returns a Promise). `notes`/`setNote` form a controlled per-item feedback
// store owned by the modal (keyed `${section}:${index}`).
export default function InteractiveResume({ doc, onSave, notes, setNote }) {
  // active = { section, index } whose popover is open; editing = same shape when in edit mode.
  const [active, setActive] = useState(null)
  const [editing, setEditing] = useState(null)
  const [feedbackFor, setFeedbackFor] = useState(null) // { section, index } showing a feedback box
  const noteKey = (s, i) => `${s}:${i}`

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
    return (
      <div className="flex flex-col gap-1">
        <ItemRow onClick={() => setActive(isActive(section, index) ? null : { section, index })}>
          <Display value={value} />
        </ItemRow>
        {isActive(section, index) && (
          <ItemPopover
            onEdit={() => {
              if (feedbackFor && feedbackFor.section === section && feedbackFor.index === index) setFeedbackFor(null)
              setEditing({ section, index })
            }}
            onFeedback={() => { setFeedbackFor({ section, index }); setActive(null) }}
            onClose={() => setActive(null)}
          />
        )}
        {(feedbackFor && feedbackFor.section === section && feedbackFor.index === index) || notes[key] ? (
          <textarea
            rows={2}
            autoFocus={!!(feedbackFor && feedbackFor.section === section && feedbackFor.index === index)}
            placeholder="Feedback for regeneration…"
            value={notes[key]?.note || ''}
            onChange={(e) => setNote(key, { section, label: itemLabel(section, index, value), note: e.target.value })}
            className="w-full text-xs rounded bg-[#0a0a1a] border border-space-border text-space-text p-2 focus:border-purple-500 outline-none"
          />
        ) : null}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      {doc.profile_summary ? (
        <ResumeSection title="Profile">{renderItem('summary', 0, doc.profile_summary)}</ResumeSection>
      ) : null}
      {doc.experience?.length ? (
        <ResumeSection title="Experience">
          {doc.experience.map((e, i) => <div key={i}>{renderItem('experience', i, e)}</div>)}
        </ResumeSection>
      ) : null}
      {doc.education?.length ? (
        <ResumeSection title="Education">
          {doc.education.map((ed, i) => <div key={i}>{renderItem('education', i, ed)}</div>)}
        </ResumeSection>
      ) : null}
      {doc.projects?.length ? (
        <ResumeSection title="Projects">
          {doc.projects.map((p, i) => <div key={i}>{renderItem('project', i, p)}</div>)}
        </ResumeSection>
      ) : null}
      {doc.skills?.length ? (
        <ResumeSection title="Skills">
          {doc.skills.map((g, i) => <div key={i}>{renderItem('skills', i, g)}</div>)}
        </ResumeSection>
      ) : null}
    </div>
  )
}
