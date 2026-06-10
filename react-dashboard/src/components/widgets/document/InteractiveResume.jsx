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
// edit (returns a Promise). `onAddFeedback(section, index, value)` opens feedback
// for an item (Phase 3; may be undefined in Phase 2).
export default function InteractiveResume({ doc, onSave, onAddFeedback }) {
  // active = { section, index } whose popover is open; editing = same shape when in edit mode.
  const [active, setActive] = useState(null)
  const [editing, setEditing] = useState(null)

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
            } catch {
              // Save failed — keep the editor open so the user doesn't lose their edit.
            }
          }}
        />
      )
    }
    return (
      <div className="flex flex-col gap-1">
        <ItemRow onClick={() => setActive(isActive(section, index) ? null : { section, index })}>
          <Display value={value} />
        </ItemRow>
        {isActive(section, index) && (
          <ItemPopover
            onEdit={() => setEditing({ section, index })}
            onFeedback={() => { onAddFeedback && onAddFeedback(section, index, value, itemLabel(section, index, value)); setActive(null) }}
            onClose={() => setActive(null)}
          />
        )}
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
