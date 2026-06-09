import ResumeSection, { ItemRow } from './ResumeSection'
import {
  ProfileDisplay, ExperienceDisplay, EducationDisplay, ProjectDisplay, SkillsGroupDisplay,
} from './items'
import './highlight.css'

// Render the structured résumé as interactive HTML in canonical section order.
// `onItemClick(section, index, value, anchorEl)` is invoked when an item is clicked
// (used in later phases for the popover); in Phase 1 it may be undefined.
export default function InteractiveResume({ doc, onItemClick }) {
  if (!doc) return null
  const click = (section, index, value) => (e) =>
    onItemClick && onItemClick(section, index, value, e.currentTarget)

  return (
    <div className="flex flex-col gap-4">
      {doc.profile_summary ? (
        <ResumeSection title="Profile">
          <ItemRow onClick={click('summary', 0, doc.profile_summary)}>
            <ProfileDisplay value={doc.profile_summary} />
          </ItemRow>
        </ResumeSection>
      ) : null}

      {doc.experience?.length ? (
        <ResumeSection title="Experience">
          {doc.experience.map((e, i) => (
            <ItemRow key={i} onClick={click('experience', i, e)}>
              <ExperienceDisplay value={e} />
            </ItemRow>
          ))}
        </ResumeSection>
      ) : null}

      {doc.education?.length ? (
        <ResumeSection title="Education">
          {doc.education.map((ed, i) => (
            <ItemRow key={i} onClick={click('education', i, ed)}>
              <EducationDisplay value={ed} />
            </ItemRow>
          ))}
        </ResumeSection>
      ) : null}

      {doc.projects?.length ? (
        <ResumeSection title="Projects">
          {doc.projects.map((p, i) => (
            <ItemRow key={i} onClick={click('project', i, p)}>
              <ProjectDisplay value={p} />
            </ItemRow>
          ))}
        </ResumeSection>
      ) : null}

      {doc.skills?.length ? (
        <ResumeSection title="Skills">
          {doc.skills.map((g, i) => (
            <ItemRow key={i} onClick={click('skills', i, g)}>
              <SkillsGroupDisplay value={g} />
            </ItemRow>
          ))}
        </ResumeSection>
      ) : null}
    </div>
  )
}
