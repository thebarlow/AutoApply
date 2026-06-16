import { useState, useEffect, useCallback } from 'react'
import {
  inviteUser, getInvites, getUsers, getUserPurchases, startImpersonation,
  setUserAccess, getGrantBudget, grantCredits,
} from '../../api'

const SORTS = [
  { key: 'email', label: 'Email' },
  { key: 'tier', label: 'Tier' },
  { key: 'credits', label: 'Credits' },
]

// Admins display '—' for credits; sort them to the bottom of a credits sort.
const creditSortVal = (u) => (u.is_admin ? -1 : (u.credits ?? 0))

export default function ManageUsers() {
  const [email, setEmail] = useState('')
  const [status, setStatus] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [invites, setInvites] = useState([])

  const [users, setUsers] = useState([])
  const [search, setSearch] = useState('')
  const [sortKey, setSortKey] = useState('email')
  const [sortDir, setSortDir] = useState('asc')

  const [purchasesFor, setPurchasesFor] = useState(null)
  const [purchases, setPurchases] = useState(null)

  const [budget, setBudget] = useState(null)
  const [grantFor, setGrantFor] = useState(null)   // user | null
  const [grantAmount, setGrantAmount] = useState(100)
  const [grantError, setGrantError] = useState(null)
  const [granting, setGranting] = useState(false)

  const [revokeFor, setRevokeFor] = useState(null) // user | null

  const refreshUsers = useCallback(() => { getUsers().then(setUsers).catch(() => {}) }, [])
  const refreshBudget = useCallback(() => { getGrantBudget().then(setBudget).catch(() => setBudget(null)) }, [])
  const refreshInvites = useCallback(() => { getInvites().then(setInvites).catch(() => {}) }, [])

  useEffect(() => { refreshUsers() }, [refreshUsers])
  useEffect(() => { refreshBudget() }, [refreshBudget])
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

  const toggleSort = (key) => {
    if (key === sortKey) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else { setSortKey(key); setSortDir('asc') }
  }

  const openGrant = (u) => {
    setGrantFor(u)
    setGrantError(null)
    const avail = budget?.available
    setGrantAmount(avail != null ? Math.min(100, avail) : 100)
  }

  const submitGrant = async () => {
    if (!grantFor) return
    setGranting(true)
    setGrantError(null)
    try {
      await grantCredits(grantFor.profile_id, Math.floor(Number(grantAmount)))
      setGrantFor(null)
      refreshUsers()
      refreshBudget()
    } catch {
      setGrantError('Grant failed (over budget or balance unavailable).')
    } finally {
      setGranting(false)
    }
  }

  const confirmRevoke = async () => {
    if (!revokeFor) return
    try {
      await setUserAccess(revokeFor.profile_id, true)
      setRevokeFor(null)
      refreshUsers()
    } catch {
      setStatus({ kind: 'err', text: 'Could not revoke access.' })
    }
  }

  const restore = async (u) => {
    try { await setUserAccess(u.profile_id, false); refreshUsers() }
    catch { setStatus({ kind: 'err', text: 'Could not restore access.' }) }
  }

  const shown = users
    .filter((u) => u.email.toLowerCase().includes(search.trim().toLowerCase()))
    .sort((a, b) => {
      let av, bv
      if (sortKey === 'credits') { av = creditSortVal(a); bv = creditSortVal(b) }
      else { av = (a[sortKey] ?? '').toString().toLowerCase(); bv = (b[sortKey] ?? '').toString().toLowerCase() }
      if (av < bv) return sortDir === 'asc' ? -1 : 1
      if (av > bv) return sortDir === 'asc' ? 1 : -1
      return 0
    })

  const arrow = (key) => (key === sortKey ? (sortDir === 'asc' ? ' ▲' : ' ▼') : '')

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
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by email…"
          className="w-full mb-3 px-3 py-2 rounded-lg bg-white/5 border border-space-border text-sm focus:outline-none focus:border-purple-500"
        />
        <div className="border border-space-border rounded-lg overflow-hidden">
          <div className="grid grid-cols-[2fr_1fr_1fr_auto] gap-2 px-3 py-2 text-xs uppercase tracking-widest text-space-dim bg-white/5">
            {SORTS.map((s) => (
              <button
                key={s.key}
                onClick={() => toggleSort(s.key)}
                className="text-left hover:text-space-text transition-colors"
              >
                {s.label}{arrow(s.key)}
              </button>
            ))}
            <span className="text-left">Actions</span>
          </div>
          <div className="max-h-60 overflow-y-auto">
            {shown.map((u) => (
              <div
                key={u.profile_id}
                className={`grid grid-cols-[2fr_1fr_1fr_auto] gap-2 px-3 py-2 text-sm items-center border-t border-space-border/50 ${u.banned ? 'opacity-60' : ''}`}
              >
                <span className="truncate flex items-center gap-2" title={u.email}>
                  {u.email}
                  {u.is_admin && (
                    <span className="text-[10px] font-bold text-black bg-amber-400 rounded px-1 py-0.5">ADMIN</span>
                  )}
                  {u.banned && (
                    <span className="text-[10px] font-bold text-white bg-red-600 rounded px-1 py-0.5">BANNED</span>
                  )}
                </span>
                <span className="text-space-dim text-left">{u.tier}</span>
                {u.is_admin ? (
                  <span className="font-mono text-space-dim text-left">—</span>
                ) : (
                  <button
                    type="button"
                    title="Grant credits"
                    onClick={() => openGrant(u)}
                    className="font-mono text-purple-400 hover:text-purple-300 text-left"
                  >
                    {(u.credits ?? 0).toLocaleString()}
                  </button>
                )}
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
                  {!u.is_admin && (u.banned ? (
                    <button
                      type="button"
                      title="Restore access"
                      onClick={() => restore(u)}
                      className="text-space-dim hover:text-green-400 transition-colors"
                    >↺</button>
                  ) : (
                    <button
                      type="button"
                      title="Revoke access"
                      onClick={() => setRevokeFor(u)}
                      className="text-red-500 hover:text-red-400 transition-colors font-bold"
                    >✕</button>
                  ))}
                </span>
              </div>
            ))}
            {shown.length === 0 && <p className="px-3 py-3 text-xs text-space-dim">No users.</p>}
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

      {grantFor && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/70" onClick={() => setGrantFor(null)}>
          <div className="bg-[#12121f] border border-space-border rounded-xl p-5 w-full max-w-sm mx-4" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-sm font-semibold mb-1">Grant credits</h3>
            <p className="text-xs text-space-dim mb-3">{grantFor.email}</p>
            {budget?.available == null ? (
              <p className="text-xs text-red-400 mb-3">System balance unavailable — grants are disabled.</p>
            ) : (
              <p className="text-xs text-space-dim mb-3">Up to {budget.available.toLocaleString()} credits available (free to the user, funded from the system balance).</p>
            )}
            <input
              type="number"
              min="1"
              step="1"
              max={budget?.available ?? undefined}
              value={grantAmount}
              onChange={(e) => setGrantAmount(e.target.value)}
              disabled={budget?.available == null}
              className="w-full mb-3 px-3 py-2 rounded-lg bg-white/5 border border-space-border text-sm focus:outline-none focus:border-purple-500 disabled:opacity-50"
            />
            {grantError && <p className="text-xs text-red-400 mb-2">{grantError}</p>}
            <div className="flex justify-end gap-2">
              <button onClick={() => setGrantFor(null)} className="px-3 py-1.5 text-sm text-space-dim hover:text-space-text">Cancel</button>
              <button
                onClick={submitGrant}
                disabled={granting || budget?.available == null || Number(grantAmount) <= 0}
                className="px-3 py-1.5 rounded-lg bg-purple-600 text-white text-sm font-semibold hover:bg-purple-500 disabled:opacity-50"
              >
                {granting ? 'Granting…' : 'Grant'}
              </button>
            </div>
          </div>
        </div>
      )}

      {revokeFor && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/70" onClick={() => setRevokeFor(null)}>
          <div className="bg-[#12121f] border border-space-border rounded-xl p-5 w-full max-w-sm mx-4" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-sm font-semibold mb-1">Revoke access</h3>
            <p className="text-xs text-space-dim mb-4">
              Ban <span className="text-space-text">{revokeFor.email}</span> and remove them from the allowlist? They'll be signed out and need a fresh invite to return.
            </p>
            <div className="flex justify-end gap-2">
              <button onClick={() => setRevokeFor(null)} className="px-3 py-1.5 text-sm text-space-dim hover:text-space-text">Cancel</button>
              <button onClick={confirmRevoke} className="px-3 py-1.5 rounded-lg bg-red-600 text-white text-sm font-semibold hover:bg-red-500">Revoke</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
