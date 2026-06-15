import { useState, useEffect } from 'react'
import { getCredits } from '../../api'

/**
 * Credit-balance overlay opened from the navbar "+" button. Shows the current
 * balance and a "Buy more credits" button that opens the pack-selection modal
 * (via `onBuy`). Closes on backdrop click or Escape (`onClose`).
 */
export default function CreditsOverlay({ onClose, onBuy }) {
  const [balance, setBalance] = useState(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    getCredits()
      .then((d) => { setBalance(d.balance); setError(false) })
      .catch(() => setError(true))
  }, [])

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const balanceText = error
    ? '—'
    : balance == null
    ? '…'
    : balance.toLocaleString()

  return (
    <div className="fixed inset-0 z-[150] flex items-center justify-center bg-black/70"
         onClick={onClose}>
      <div className="bg-[#0f0f1a] border border-space-border rounded-2xl p-6 w-[22rem] max-w-[90vw]"
           onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-space-text">Credits</h2>
          <button onClick={onClose}
                  className="text-space-dim hover:text-space-text text-xl leading-none">×</button>
        </div>
        <p className="text-sm text-space-dim mb-1">Credit Balance</p>
        <p className="text-3xl font-mono text-purple-400 mb-5">{balanceText}</p>
        <button onClick={onBuy}
                className="w-full py-2.5 rounded-xl border border-purple-400 text-purple-400 hover:bg-purple-400/10 text-sm font-medium transition-colors">
          Buy more credits
        </button>
      </div>
    </div>
  )
}
