import { useState } from 'react'

// A résumé section: a hover-tinted container with a title and item rows.
// `items` is [{ key, node }]; each item row manages its own focused-hover state.
export default function ResumeSection({ title, children }) {
  const [hover, setHover] = useState(false)
  return (
    <section
      className={`doc-section${hover ? ' hl' : ''}`}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <div className="doc-section-title text-xs uppercase tracking-widest text-space-dim mb-2 inline-block">
        {title}
      </div>
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
