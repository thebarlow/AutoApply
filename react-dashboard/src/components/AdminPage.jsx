import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { getMe, inviteUser, getInvites } from '../api'

export default function AdminPage() {
  const [allowed, setAllowed] = useState(undefined) // undefined=loading
  const [email, setEmail] = useState('')
  const [status, setStatus] = useState(null) // { kind: 'ok'|'err', text }
  const [submitting, setSubmitting] = useState(false)
  const [invites, setInvites] = useState([])

  useEffect(() => {
    getMe().then((me) => setAllowed(!!me?.is_admin)).catch(() => setAllowed(false))
  }, [])

  const refreshInvites = useCallback(() => {
    getInvites().then(setInvites).catch(() => {})
  }, [])

  useEffect(() => { if (allowed) refreshInvites() }, [allowed, refreshInvites])

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

  if (allowed === undefined) return null
  if (!allowed) {
    return (
      <div className="min-h-screen flex items-center justify-center text-space-dim">
        <p>Not authorized. <Link to="/" className="text-purple-400 hover:underline">Go home</Link></p>
      </div>
    )
  }

  return (
    <div className="min-h-screen text-space-text p-8 max-w-xl mx-auto">
      <Link to="/" className="text-sm text-space-dim hover:text-purple-400">← Back</Link>
      <h1 className="text-2xl font-bold mt-4 mb-6">Admin — Invite Users</h1>

      <form onSubmit={submit} className="flex gap-2 mb-3">
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
        <p className={`text-sm mb-6 ${status.kind === 'ok' ? 'text-green-400' : 'text-red-400'}`}>
          {status.text}
        </p>
      )}

      <h2 className="text-xs uppercase tracking-widest text-space-dim mb-2">Invited</h2>
      <ul className="flex flex-col gap-1">
        {invites.map((inv) => (
          <li key={inv.email} className="flex justify-between text-sm border-b border-space-border/50 py-1">
            <span>{inv.email}</span>
            <span className="text-space-dim text-xs">{new Date(inv.created_at).toLocaleDateString()}</span>
          </li>
        ))}
        {invites.length === 0 && <li className="text-xs text-space-dim">No invites yet.</li>}
      </ul>
    </div>
  )
}
