// Pure display renderers for résumé items + the label used for feedback notes.
// Each item renderer receives { value } (the structured sub-object) and renders
// read-only content. Interactivity (hover/click) is handled by the wrappers.

export function itemLabel(section, index, value) {
  switch (section) {
    case 'summary': return 'Profile summary'
    case 'skills': return 'Skills'
    case 'experience': {
      const who = [value?.title, value?.company].filter(Boolean).join(' at ')
      return `Experience [${index}]${who ? ` (${who})` : ''}`
    }
    case 'project': return `Project [${index}]${value?.name ? ` (${value.name})` : ''}`
    case 'education': return `Education [${index}]${value?.degree ? ` (${value.degree})` : ''}`
    default: return section
  }
}

export function ProfileDisplay({ value }) {
  return <p className="text-sm whitespace-pre-wrap text-space-text">{value}</p>
}

export function ExperienceDisplay({ value }) {
  const dates = [value.start, value.end].filter(Boolean).join(' – ')
  return (
    <div>
      <p className="text-sm font-semibold text-space-text">
        {[value.title, value.company].filter(Boolean).join(', ')}
        {dates ? <span className="text-space-dim font-normal"> ({dates})</span> : null}
      </p>
      {value.description ? (
        <p className="text-xs whitespace-pre-wrap text-space-dim mt-1">{value.description}</p>
      ) : null}
    </div>
  )
}

export function EducationDisplay({ value }) {
  const tail = value.graduated ? ` (${value.graduated})` : ''
  const degreeField = [value.degree, value.field].filter(Boolean).join(' in ')
  return (
    <p className="text-sm text-space-text">
      {[degreeField, value.institution].filter(Boolean).join(', ')}{tail}
    </p>
  )
}

export function ProjectDisplay({ value }) {
  return (
    <p className="text-sm text-space-text">
      {value.name ? <span className="font-semibold">{value.name}: </span> : null}
      <span className="text-space-dim">{value.description}</span>
    </p>
  )
}

export function SkillsGroupDisplay({ value }) {
  return (
    <p className="text-sm text-space-text">
      <span className="font-semibold">{value.category}: </span>
      <span className="text-space-dim">{(value.items || []).join(', ')}</span>
    </p>
  )
}
