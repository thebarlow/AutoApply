import { useState } from 'react'

// Render the backend's preview object as a short human summary.
function formatPreview(preview) {
  if (!preview || typeof preview !== 'object') return ''
  if (typeof preview.count === 'number') return `${preview.count} entries`
  if (Array.isArray(preview.items)) return preview.items.join(', ')
  if (Array.isArray(preview.fields)) return preview.fields.join(', ')
  if (typeof preview.chars === 'number') return `${preview.chars} characters`
  return ''
}

export default function ParsePreview({ proposal, onApply, onCancel, applying }) {
  const sections = proposal.sections

  const [actions, setActions] = useState(() => sections.map((s) => s.default_action))
  const [names, setNames] = useState(() => sections.map((s) => s.name))

  // Keep the original index alongside each row so filtered subsets map back to
  // the flat actions/names state without an O(n²) indexOf or name-based key.
  const builtins = sections
    .map((s, i) => ({ s, i }))
    .filter(({ s }) => s.origin === 'builtin')
  const novels = sections
    .map((s, i) => ({ s, i }))
    .filter(({ s }) => s.origin === 'novel')

  const setAction = (i, val) =>
    setActions((prev) => prev.map((a, idx) => (idx === i ? val : a)))

  const setName = (i, val) =>
    setNames((prev) => prev.map((n, idx) => (idx === i ? val : n)))

  const handleApply = () => {
    onApply({
      ...proposal,
      sections: sections.map((s, i) => ({ ...s, action: actions[i], name: names[i] })),
    })
  }

  const selectClass = 'bg-white text-black border border-gray-300 rounded px-2 py-1 text-sm'
  const inputClass =
    'bg-white text-black border border-gray-300 rounded px-2 py-1 text-sm w-full'

  return (
    <div className="flex flex-col gap-4">
      {/* Builtin sections */}
      <div>
        <h3 className="text-sm font-semibold mb-2">Standard sections</h3>
        <div className="flex flex-col gap-2">
          {builtins.map(({ s, i }) => {
            return (
              <div key={i} className="flex items-center gap-3">
                <span className="text-sm flex-1">{s.name}</span>
                <select
                  className={selectClass}
                  value={actions[i]}
                  onChange={(e) => setAction(i, e.target.value)}
                >
                  {s.allowed_actions.map((a) => (
                    <option key={a} value={a}>{a}</option>
                  ))}
                </select>
              </div>
            )
          })}
        </div>
      </div>

      {/* Novel sections */}
      {novels.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold mb-2">Additional sections found</h3>
          <div className="flex flex-col gap-2">
            {novels.map(({ s, i }) => {
              const previewText = formatPreview(s.preview)
              return (
                <div key={i} className="flex flex-col gap-1">
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-gray-400">{s.kind}</span>
                    <input
                      className={inputClass}
                      value={names[i]}
                      onChange={(e) => setName(i, e.target.value)}
                    />
                    <select
                      className={selectClass}
                      value={actions[i]}
                      onChange={(e) => setAction(i, e.target.value)}
                    >
                      {s.allowed_actions.map((a) => (
                        <option key={a} value={a}>{a}</option>
                      ))}
                    </select>
                  </div>
                  {previewText && (
                    <p className="text-xs text-gray-400 pl-1">{previewText}</p>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-2 justify-end">
        <button
          className="px-3 py-1.5 text-sm rounded border border-gray-500 text-gray-300 hover:bg-white/10"
          onClick={onCancel}
        >
          Cancel
        </button>
        <button
          className="px-3 py-1.5 text-sm rounded bg-purple-600 hover:bg-purple-500 text-white disabled:opacity-50"
          onClick={handleApply}
          disabled={!!applying}
        >
          Apply
        </button>
      </div>
    </div>
  )
}
