import { useState, useEffect, useCallback } from 'react'
import { inviteUser, getInvites } from '../../api'

export default function ManageUsers() {
  const [email, setEmail] = useState('')
  const [status, setStatus] = useState(null) // { kind: 'ok'|'err', text }
  const [submitting, setSubmitting] = useState(false)
  const [invites, setInvites] = useState([])

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
    </div>
  )
}
