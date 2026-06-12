import { useState, useEffect, useCallback } from 'react'
import { getCredits } from '../../api'

/**
 * Credit balance display. Fetches /api/credits on mount and refetches when an
 * `auto-apply:credits-stale` event fires (dispatched from api.js after a metered
 * action or a 402). `variant` selects navbar ('nav') vs settings-panel ('panel')
 * styling.
 */
export default function CreditBalance({ variant = 'nav' }) {
  const [balance, setBalance] = useState(null)
  const [error, setError] = useState(false)

  const refresh = useCallback(() => {
    getCredits()
      .then((d) => { setBalance(d.balance); setError(false) })
      .catch(() => setError(true))
  }, [])

  useEffect(() => {
    refresh()
    window.addEventListener('auto-apply:credits-stale', refresh)
    return () => window.removeEventListener('auto-apply:credits-stale', refresh)
  }, [refresh])

  const text = error
    ? '— credits'
    : balance == null
    ? '…'
    : `${balance.toLocaleString()} credits`

  if (variant === 'panel') {
    return (
      <div className="flex items-center justify-between px-3 py-2 rounded-lg border border-space-border bg-white/5">
        <span className="text-xs uppercase tracking-widest text-space-dim">Credits</span>
        <span className="text-sm font-mono text-purple-400">{text}</span>
      </div>
    )
  }

  return (
    <span
      className="text-sm font-medium text-purple-400"
      title="Your remaining credits"
    >
      {text}
    </span>
  )
}
