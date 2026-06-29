import { useState, useRef, useCallback } from 'react'
import { resumeCompare } from '../../api'

function buildRows(m1, m2) {
  const s1 = m1?.sections || []
  const s2 = m2?.sections || []
  const key = (h) => h.trim().toLowerCase()
  const map2 = new Map(s2.map((s) => [key(s.heading), s]))
  const rows = []
  const seen = new Set()
  for (const s of s1) {
    const k = key(s.heading)
    seen.add(k)
    rows.push({ heading: s.heading, m1: s, m2: map2.get(k) || null })
  }
  for (const s of s2) {
    const k = key(s.heading)
    if (seen.has(k)) continue
    rows.push({ heading: s.heading, m1: null, m2: s })
  }
  return rows
}

function srcDoc(css, html) {
  return `<style>${css}</style><div class="resume">${html}</div>`
}

function Cell({ css, section, errored, registerFrame }) {
  if (errored) return <div className="text-red-400/70 text-xs italic p-2">— error —</div>
  if (!section) return <div className="text-space-dim text-xs italic p-2">— not present —</div>
  return (
    <iframe
      title="section"
      srcDoc={srcDoc(css, section.html)}
      ref={registerFrame}
      className="w-full bg-white rounded border border-space-border"
      style={{ height: 80, border: 'none' }}
    />
  )
}

function HeaderCell({ title, model }) {
  return (
    <div className="flex items-center justify-between px-1 pb-2 border-b border-space-border">
      <h3 className="font-semibold text-sm">{title}</h3>
      {model?.error == null && model?.score != null && (
        <span className="text-xs text-space-dim">score {Number(model.score).toFixed(2)}</span>
      )}
      {model?.error != null && <span className="text-red-400 text-xs">Error: {model.error}</span>}
    </div>
  )
}

export default function ResumeCompare() {
  const [jobKey, setJobKey] = useState('')
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  // rowKey -> { left, right } iframe element refs, for height equalization.
  const frames = useRef({})

  const run = async () => {
    setBusy(true); setErr(''); setResult(null); frames.current = {}
    try {
      setResult(await resumeCompare(jobKey.trim()))
    } catch (e) {
      setErr(String(e.message || e))
    } finally {
      setBusy(false)
    }
  }

  // Equalize the two iframes in a row to the taller content height once both loaded.
  const equalize = useCallback((rowKey) => {
    const pair = frames.current[rowKey]
    if (!pair) return
    const heights = []
    for (const f of [pair.left, pair.right]) {
      if (!f) continue
      try {
        heights.push(f.contentDocument.documentElement.scrollHeight)
      } catch { /* not ready */ }
    }
    if (!heights.length) return
    const h = Math.max(...heights)
    for (const f of [pair.left, pair.right]) if (f) f.style.height = `${h}px`
  }, [])

  const register = (rowKey, side) => (el) => {
    if (!el) return
    frames.current[rowKey] = frames.current[rowKey] || {}
    frames.current[rowKey][side] = el
    el.addEventListener('load', () => equalize(rowKey), { once: true })
  }

  const m1 = result?.model1
  const m2 = result?.model2
  const bothErrored = m1?.error != null && m2?.error != null
  const rows = result && !bothErrored ? buildRows(m1, m2) : []

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
        <div className="flex flex-col gap-3">
          {/* Sticky header row */}
          <div className="grid grid-cols-[7rem_1fr_1fr] gap-3 sticky top-0 bg-space-bg z-10 pt-1">
            <div />
            <HeaderCell title="Model 1 (single-call)" model={m1} />
            <HeaderCell title="Model 2 (per-section)" model={m2} />
          </div>

          {bothErrored && (
            <p className="text-red-400 text-sm">Both models failed; nothing to compare.</p>
          )}

          {rows.map((row, i) => {
            const rowKey = `${i}:${row.heading}`
            return (
              <div key={rowKey} className="grid grid-cols-[7rem_1fr_1fr] gap-3 items-start">
                <div className="text-xs font-semibold text-space-dim uppercase tracking-wide pt-2">
                  {row.heading}
                </div>
                <Cell css={result.css} section={row.m1} errored={m1?.error != null}
                  registerFrame={register(rowKey, 'left')} />
                <Cell css={result.css} section={row.m2} errored={m2?.error != null}
                  registerFrame={register(rowKey, 'right')} />
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
