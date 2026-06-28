import { useState } from 'react'
import { draftSectionPrompt } from '../../../api'

const inputClass = 'bg-white text-black border border-gray-300 rounded px-2 py-1 text-sm w-full'
const textareaClass = 'bg-white text-black border border-gray-300 rounded px-2 py-1 text-sm w-full resize-y'
const labelClass = 'text-xs text-gray-400 mb-0.5'

function SectionRow({ row, index, onChange, profileId }) {
  const [purpose, setPurpose] = useState('')
  const [tailoring, setTailoring] = useState('')
  const [drafting, setDrafting] = useState(false)

  const toggleCustomize = () => onChange(index, { ...row, customize: !row.customize })
  const setPrompt = (val) => onChange(index, { ...row, prompt: val })
  const setName = (val) => onChange(index, { ...row, name: val })

  const handleDraft = async () => {
    setDrafting(true)
    try {
      const res = await draftSectionPrompt(profileId, {
        section_name: row.name,
        purpose,
        tailoring,
      })
      if (res?.prompt) setPrompt(res.prompt)
    } finally {
      setDrafting(false)
    }
  }

  // Single flat div so that getByText(name).closest('div') finds this element,
  // which contains both the checkbox and the conditionally rendered textarea.
  return (
    <div className="flex flex-col gap-2 py-2 border-b border-gray-700 last:border-0">
      {/* Use <label> (not div) so that getByText(name).closest('div') climbs to
          the SectionRow outer div, where the textarea is also rendered. */}
      <label className="flex items-center gap-3 cursor-pointer">
        <input
          type="checkbox"
          checked={row.customize}
          onChange={toggleCustomize}
          className="accent-purple-500 w-4 h-4 shrink-0"
        />
        <span className="text-sm flex-1">{row.name}</span>
      </label>

      {/* Editable name input for novel sections, shown below the label row. */}
      {row.origin === 'novel' && (
        <div className="ml-7">
          <p className={labelClass}>Section name</p>
          <input
            className={inputClass}
            value={row.name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
      )}

      {row.customize && (
        <div className="ml-7 flex flex-col gap-2">
          <div>
            <p className={labelClass}>Tailoring prompt</p>
            <textarea
              className={textareaClass}
              rows={3}
              value={row.prompt}
              onChange={(e) => setPrompt(e.target.value)}
            />
          </div>

          {/* Draft affordance */}
          <details className="text-xs">
            <summary className="cursor-pointer text-gray-400 hover:text-gray-200 select-none">
              Draft from questions
            </summary>
            <div className="flex flex-col gap-2 mt-2">
              <div>
                <p className={labelClass}>What is the purpose of this section?</p>
                <input
                  className={inputClass}
                  value={purpose}
                  onChange={(e) => setPurpose(e.target.value)}
                  placeholder="e.g. Highlight relevant certifications"
                />
              </div>
              <div>
                <p className={labelClass}>How should it be tailored per job?</p>
                <input
                  className={inputClass}
                  value={tailoring}
                  onChange={(e) => setTailoring(e.target.value)}
                  placeholder="e.g. Emphasise certs matching required skills"
                />
              </div>
              <button
                className="self-start px-3 py-1 text-xs rounded bg-gray-600 hover:bg-gray-500 text-white disabled:opacity-50"
                onClick={handleDraft}
                disabled={drafting}
              >
                {drafting ? 'Drafting…' : 'Draft'}
              </button>
            </div>
          </details>
        </div>
      )}
    </div>
  )
}

export default function ParsePreview({ proposal, profileId, onApply, onCancel, applying }) {
  const [rows, setRows] = useState(() => proposal.sections.map((s) => ({ ...s })))

  const handleChange = (index, updated) =>
    setRows((prev) => prev.map((r, i) => (i === index ? updated : r)))

  const handleFinish = () => onApply({ ...proposal, sections: rows })

  return (
    <div className="flex flex-col gap-4">
      <h3 className="text-sm font-semibold">Which sections should we tailor to each job?</h3>

      <div className="flex flex-col">
        {rows.map((row, i) => (
          <SectionRow
            key={i}
            row={row}
            index={i}
            onChange={handleChange}
            profileId={profileId}
          />
        ))}
      </div>

      <div className="flex gap-2 justify-end">
        <button
          className="px-3 py-1.5 text-sm rounded border border-gray-500 text-gray-300 hover:bg-white/10"
          onClick={onCancel}
        >
          Cancel
        </button>
        <button
          className="px-3 py-1.5 text-sm rounded bg-purple-600 hover:bg-purple-500 text-white disabled:opacity-50"
          onClick={handleFinish}
          disabled={!!applying}
        >
          Finish
        </button>
      </div>
    </div>
  )
}
