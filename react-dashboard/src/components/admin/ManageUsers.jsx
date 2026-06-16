import { useState, useEffect, useCallback } from 'react'
import { inviteUser, getInvites, getUsers, getUserPurchases, startImpersonation } from '../../api'

export default function ManageUsers() {
  const [email, setEmail] = useState('')
  const [status, setStatus] = useState(null) // { kind: 'ok'|'err', text }
  const [submitting, setSubmitting] = useState(false)
  const [invites, setInvites] = useState([])
  const [users, setUsers] = useState([])
  const [purchasesFor, setPurchasesFor] = useState(null) // profile_id | null
  const [purchases, setPurchases] = useState(null)        // null=loading

  useEffect(() => { getUsers().then(setUsers).catch(() => {}) }, [])

  const openPurchases = (profileId) => {
    setPurchasesFor(profileId)
    setPurchases(null)
    getUserPurchases(profileId).then(setPurchases).catch(() => setPurchases([]))
  }

  const viewAs = async (profileId) => {
    try {
      await startImpersonation(profileId)
      window.location.href = '/'
    } catch {
      setStatus({ kind: 'err', text: 'Could not start impersonation.' })
    }
  }

  const refreshInvites = useCallback(() => {
    getInvites().then(setInvites).catch(() => {})
  }, [])

  useEffect(() => { refreshInvites() }, [refreshInvites])

  const submit = async (e) => {
    e.preventDefault()
    if (!email.trim()) return
    setSubmitting(true)
    setStatus(null)
    try {
      const r = await inviteUser(email.trim())
      const text = r.already_invited
        ? 'Already invited.'
        : r.emailed
        ? 'Invited — email sent.'
        : 'Added to allowlist (email not configured).'
      setStatus({ kind: 'ok', text })
      setEmail('')
      refreshInvites()
    } catch {
      setStatus({ kind: 'err', text: 'Failed to send invite.' })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <section>
        <h2 className="text-lg font-semibold mb-3">Invite a user</h2>
        <form onSubmit={submit} className="flex gap-2">
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="person@example.com"
            className="flex-1 px-3 py-2 rounded-lg bg-white/5 border border-space-border text-sm focus:outline-none focus:border-purple-500"
          />
          <button
            type="submit"
            disabled={submitting}
            className="px-4 py-2 rounded-lg bg-purple-600 text-white text-sm font-semibold hover:bg-purple-500 disabled:opacity-50"
          >
            {submitting ? 'Sending…' : 'Send Invite'}
          </button>
        </form>
        {status && (
          <p className={`text-sm mt-2 ${status.kind === 'ok' ? 'text-green-400' : 'text-red-400'}`}>
            {status.text}
          </p>
        )}
        {invites.length > 0 && (
          <ul className="flex flex-col gap-1 mt-4">
            <li className="text-xs uppercase tracking-widest text-space-dim mb-1">Invited</li>
            {invites.map((inv) => (
              <li key={inv.email} className="flex justify-between text-sm border-b border-space-border/50 py-1">
                <span>{inv.email}</span>
                <span className="text-space-dim text-xs">{new Date(inv.created_at).toLocaleDateString()}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h2 className="text-lg font-semibold mb-3">Users</h2>
        <div className="border border-space-border rounded-lg overflow-hidden">
          <div className="grid grid-cols-[2fr_1fr_1fr_auto] gap-2 px-3 py-2 text-xs uppercase tracking-widest text-space-dim bg-white/5">
            <span>Email</span><span>Tier</span><span>Credits</span><span>Actions</span>
          </div>
          <div className="max-h-60 overflow-y-auto">
            {users.map((u) => (
              <div key={u.profile_id} className="grid grid-cols-[2fr_1fr_1fr_auto] gap-2 px-3 py-2 text-sm items-center border-t border-space-border/50">
                <span className="truncate" title={u.email}>{u.email}</span>
                <span className="text-space-dim">{u.tier}</span>
                <span className="font-mono text-purple-400">{(u.credits ?? 0).toLocaleString()}</span>
                <span className="flex items-center gap-2">
                  <button
                    type="button"
                    title="View app as this user"
                    onClick={() => viewAs(u.profile_id)}
                    className="text-space-dim hover:text-amber-400 transition-colors"
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" />
                    </svg>
                  </button>
                  <button
                    type="button"
                    title="View purchase history"
                    onClick={() => openPurchases(u.profile_id)}
                    className="text-space-dim hover:text-purple-400 transition-colors text-xs underline"
                  >
                    Purchases
                  </button>
                </span>
              </div>
            ))}
            {users.length === 0 && <p className="px-3 py-3 text-xs text-space-dim">No users.</p>}
          </div>
        </div>
      </section>

      {purchasesFor !== null && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/70" onClick={() => setPurchasesFor(null)}>
          <div className="bg-[#12121f] border border-space-border rounded-xl p-5 w-full max-w-md mx-4" onClick={(e) => e.stopPropagation()}>
            <div className="flex justify-between items-center mb-3">
              <h3 className="text-sm font-semibold">Purchase history</h3>
              <button onClick={() => setPurchasesFor(null)} className="text-space-dim hover:text-space-text" aria-label="Close">×</button>
            </div>
            {purchases === null ? (
              <p className="text-xs text-space-dim">Loading…</p>
            ) : purchases.length === 0 ? (
              <p className="text-xs text-space-dim">No purchases.</p>
            ) : (
              <ul className="flex flex-col gap-1">
                {purchases.map((p) => (
                  <li key={p.stripe_session_id} className="flex justify-between text-xs border-b border-space-border/50 py-1">
                    <span>{new Date(p.created_at).toLocaleDateString()}</span>
                    <span>{p.credits.toLocaleString()} cr</span>
                    <span className="text-space-dim">${p.amount_usd.toFixed(2)} · {p.status}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
