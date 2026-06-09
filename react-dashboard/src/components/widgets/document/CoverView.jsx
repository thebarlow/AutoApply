// Cover-letter view. Phase 1: read-only body. Edit + feedback added in later phases
// via the `onEdit`/`feedback` props (unused here).
export default function CoverView({ doc }) {
  if (!doc) return null
  return (
    <div className="prose prose-invert max-w-none text-sm whitespace-pre-wrap text-space-text px-2">
      {doc.body}
    </div>
  )
}
