import { useState, useEffect } from 'react'
import { getPacks, startCheckout } from '../../api'

/** Modal listing credit packs; clicking one redirects to Stripe Checkout. */
export default function BuyCreditsModal({ onClose }) {
  const [packs, setPacks] = useState(null)
  const [error, setError] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    getPacks().then(setPacks).catch(() => setError(true))
  }, [])

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const buy = async (priceId) => {
    setBusy(true)
    try {
      const { url } = await startCheckout(priceId)
      window.location = url
    } catch {
      setError(true)
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[150] flex items-center justify-center bg-black/70"
         onClick={onClose}>
      <div className="bg-[#0f0f1a] border border-space-border rounded-2xl p-6 w-[26rem] max-w-[90vw]"
           onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-space-text">Buy credits</h2>
          <button onClick={onClose}
                  className="text-space-dim hover:text-space-text text-xl leading-none">×</button>
        </div>
        {error && <p className="text-sm text-red-400 mb-3">Something went wrong. Try again.</p>}
        {packs == null && !error && <p className="text-sm text-space-dim">Loading…</p>}
        <div className="flex flex-col gap-2">
          {(packs || []).map((p) => (
            <button key={p.price_id} disabled={busy} onClick={() => buy(p.price_id)}
                    className="flex items-center justify-between px-4 py-3 rounded-xl border border-space-border bg-white/5 hover:border-purple-400 disabled:opacity-50 transition-colors">
              <span className="text-sm font-medium text-space-text">
                {p.credits.toLocaleString()} credits
                {p.discount > 0 && (
                  <span className="ml-2 text-[11px] text-emerald-400">
                    +{Math.round(p.discount * 100)}% bonus
                  </span>
                )}
              </span>
              <span className="text-sm font-mono text-purple-400">
                ${p.amount_usd.toFixed(2)}
              </span>
            </button>
          ))}
        </div>
        <p className="text-[11px] text-space-dim mt-4">
          Secured by Stripe. You'll be redirected to complete payment.
        </p>
      </div>
    </div>
  )
}
