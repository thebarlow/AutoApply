import { useState, useEffect, useCallback } from 'react'
import { getCredits, getSystemBalance } from '../../api'

const CREDITS_PER_DOLLAR = 1000

/**
 * Balance display. Non-admins see personal credits (click → Buy modal, via
 * `onClick`). Admins see the platform system balance instead; clicking toggles
 * between a dollar amount and the equivalent credit amount (no Buy modal).
 * `variant` selects navbar ('nav') vs settings-panel ('panel') vs 'settings'.
 */
export default function CreditBalance({ variant = 'nav', onClick, isAdmin = false }) {
  const [balance, setBalance] = useState(null)
  const [remaining, setRemaining] = useState(null) // admin: system $ remaining
  const [unit, setUnit] = useState('usd')           // admin toggle: 'usd' | 'credits'
  const [error, setError] = useState(false)

  const refresh = useCallback(() => {
    if (isAdmin) {
      getSystemBalance()
        .then((d) => { setRemaining(d.remaining); setError(false) })
        .catch(() => setError(true))
      return
    }
    getCredits()
      .then((d) => {
        setBalance(d.balance); setError(false)
        window.__creditRate = d.rate ?? 0
      })
      .catch(() => setError(true))
  }, [isAdmin])

  useEffect(() => {
    refresh()
    window.addEventListener('auto-apply:credits-stale', refresh)
    return () => window.removeEventListener('auto-apply:credits-stale', refresh)
  }, [refresh])

  let text
  if (error) {
    text = isAdmin ? '— balance' : '— credits'
  } else if (isAdmin) {
    if (remaining == null) text = '…'
    else if (unit === 'usd') {
      text = `$${Number(remaining).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    } else {
      text = `${Math.round(remaining * CREDITS_PER_DOLLAR).toLocaleString()} credits`
    }
  } else {
    text = balance == null ? '…' : `${balance.toLocaleString()} credits`
  }

  // Admin: click toggles units. Non-admin: delegate to `onClick` (Buy modal).
  const handleClick = isAdmin
    ? () => setUnit((u) => (u === 'usd' ? 'credits' : 'usd'))
    : onClick
  const title = isAdmin ? 'System balance — click to toggle $/credits' : undefined

  if (variant === 'panel') {
    return (
      <div className="flex items-center justify-between px-3 py-2 rounded-lg border border-space-border bg-white/5">
        <span className="text-xs uppercase tracking-widest text-space-dim">
          {isAdmin ? 'System' : 'Credits'}
        </span>
        <span className="text-sm font-mono text-purple-400">{text}</span>
      </div>
    )
  }

  if (variant === 'settings') {
    return (
      <button
        type="button"
        onClick={handleClick}
        title={title ?? 'Buy credits'}
        className="self-center inline-flex items-center gap-1 text-sm font-mono text-purple-400 hover:text-purple-300 transition-colors"
      >
        {text}
        {!isAdmin && (
          <span
            aria-hidden="true"
            className="inline-flex items-center justify-center w-4 h-4 rounded-full border border-purple-400/60 text-xs leading-none"
          >
            +
          </span>
        )}
      </button>
    )
  }

  return (
    <span
      className="text-sm font-medium text-purple-400 cursor-pointer hover:text-purple-300"
      title={title ?? 'Session usage'}
      onClick={handleClick}
    >
      {text}
    </span>
  )
}
