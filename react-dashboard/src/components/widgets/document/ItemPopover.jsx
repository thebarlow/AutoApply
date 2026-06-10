// A tiny two-action popover (Edit | Feedback) rendered inline above an item.
export default function ItemPopover({ onEdit, onFeedback, onClose }) {
  return (
    <div className="inline-flex items-center gap-1 rounded-md border border-space-border bg-[#161627] px-1 py-0.5 shadow-lg"
         onClick={(e) => e.stopPropagation()}>
      <button onClick={onEdit}
        className="px-2 py-0.5 text-xs text-space-dim hover:text-space-text rounded">Edit</button>
      <span className="text-space-border">|</span>
      <button onClick={onFeedback}
        className="px-2 py-0.5 text-xs text-space-dim hover:text-space-text rounded">Feedback</button>
      <button onClick={onClose}
        className="px-1 text-xs text-space-dim hover:text-space-text rounded" title="Close">✕</button>
    </div>
  )
}
