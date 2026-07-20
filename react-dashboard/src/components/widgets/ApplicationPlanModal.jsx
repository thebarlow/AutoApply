import { useEffect, useState } from 'react'
import { getApplicationPlan } from '../../api'

const STATUS_LABEL = {
  filled: 'filled',
  drafted: 'drafted (review)',
  blank: 'blank',
  unknown: 'unknown',
}

// Read-only view of the field-mapping engine's computed application plan for a job.
export default function ApplicationPlanModal({ jobKey, open, onClose }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!open) return
    setLoading(true)
    getApplicationPlan(jobKey)
      .then(setData)
      .finally(() => setLoading(false))
  }, [open, jobKey])

  if (!open) return null
  const plan = data?.plan

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div
        className="bg-space-mid text-space-text rounded-lg p-4 max-w-lg w-full max-h-[80vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-sm font-semibold mb-2">Application plan</h3>
        {loading && <p className="text-xs text-space-dim">Loading…</p>}
        {!loading && !plan && (
          <p className="text-xs text-space-dim">
            No application plan yet. It’s computed when the extension visits this job’s apply page.
          </p>
        )}
        {!loading && plan && (
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-space-dim">
                <th className="pr-2 py-1">Field</th>
                <th className="pr-2 py-1">Value</th>
                <th className="py-1">Status</th>
              </tr>
            </thead>
            <tbody>
              {plan.fields.map((f) => (
                <tr key={f.field_id} className="border-t border-white/5">
                  <td className="pr-2 py-1">{f.label || f.field_id}</td>
                  <td className="pr-2 py-1">{f.value || <em>—</em>}</td>
                  <td className="py-1">{STATUS_LABEL[f.status] || f.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <button
          className="mt-3 text-xs px-2 py-1 rounded bg-space-dark text-space-text"
          onClick={onClose}
        >
          Close
        </button>
      </div>
    </div>
  )
}
