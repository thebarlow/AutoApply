import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { resumeCompare } from '../../api'

function Column({ title, data }) {
  if (!data) return null
  return (
    <div className="flex-1 min-w-0 border border-space-border rounded-lg p-4">
      <div className="flex items-center justify-between mb-2">
        <h3 className="font-semibold">{title}</h3>
        {data.error == null && (
          <span className="text-xs text-space-dim">score {Number(data.score).toFixed(2)}</span>
        )}
      </div>
      {data.error != null ? (
        <p className="text-red-400 text-sm">Error: {data.error}</p>
      ) : (
        <div className="prose prose-invert prose-sm max-w-none">
          <ReactMarkdown>{data.markdown}</ReactMarkdown>
        </div>
      )}
    </div>
  )
}

export default function ResumeCompare() {
  const [jobKey, setJobKey] = useState('')
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const run = async () => {
    setBusy(true); setErr(''); setResult(null)
    try {
      setResult(await resumeCompare(jobKey.trim()))
    } catch (e) {
      setErr(String(e.message || e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-end gap-2">
        <label className="flex flex-col text-sm gap-1">
          <span className="text-space-dim">Job key</span>
          <input
            aria-label="Job key" value={jobKey}
            className="bg-white/5 border border-space-border rounded px-2 py-1 text-sm"
            onChange={(e) => setJobKey(e.target.value)}
          />
        </label>
        <button
          type="button" disabled={busy || !jobKey.trim()}
          className="px-3 py-1.5 rounded-lg border border-space-border bg-[#1a1a2e] hover:bg-[#23233a] disabled:opacity-50"
          onClick={run}
        >{busy ? 'Comparing…' : 'Compare'}</button>
      </div>
      {err && <p className="text-red-400 text-sm">{err}</p>}
      {result && (
        <div className="flex gap-4 items-start">
          <Column title="Model 1 (single-call)" data={result.model1} />
          <Column title="Model 2 (per-section)" data={result.model2} />
        </div>
      )}
    </div>
  )
}
