import { useState } from 'react'

// A résumé section: a hover-tinted container with a title and item rows.
// The title is clickable (`onTitleClick`) to open `titlePopover` (rendered to its
// right) for section-level feedback; `feedbackBox` renders below the title.
export default function ResumeSection({ title, onTitleClick, titlePopover, feedbackBox, children }) {
  const [hover, setHover] = useState(false)
  return (
    <section
      className={`doc-section${hover ? ' hl' : ''}`}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <div className="flex items-center gap-2 mb-2">
        <div
          className={`doc-section-title text-xs uppercase tracking-widest text-space-dim inline-block${onTitleClick ? ' cursor-pointer' : ''}`}
          onClick={onTitleClick}
          title={onTitleClick ? 'Section feedback' : undefined}
        >
          {title}
        </div>
        {titlePopover}
      </div>
      {feedbackBox}
      <div className="flex flex-col gap-2">{children}</div>
    </section>
  )
}

// One interactive item row inside a section.
export function ItemRow({ onClick, children }) {
  const [hover, setHover] = useState(false)
  return (
    <div
      className={`doc-item${hover ? ' hl' : ''}`}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      onClick={onClick}
    >
      {children}
    </div>
  )
}
