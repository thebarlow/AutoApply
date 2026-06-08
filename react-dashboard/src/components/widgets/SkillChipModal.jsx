import { useEffect, useState } from 'react'
import {
  getSkillAliases, searchSkillAliases, assignSkillAlias,
  removeSkillAliasMember, addProfileSkill, removeProfileSkill,
} from '../../api'

// `skill` is the canonical display string of the clicked chip.
// `isOwned` reflects whether it is currently in the active profile's skills.
// `onChanged` is called after any mutation so the parent can refetch.
export default function SkillChipModal({ skill, isOwned = false, onClose, onChanged }) {
  const [group, setGroup] = useState({ canonical: skill, members: [] })
  const [query, setQuery] = useState('')
  const [matches, setMatches] = useState([])
  const [owned, setOwned] = useState(isOwned)
  const [busy, setBusy] = useState(false)

  const loadGroup = () => {
    getSkillAliases().then(({ groups }) => {
      const found = groups.find(
        (g) => g.canonical === skill || g.members.includes(skill.toLowerCase())
      )
      setGroup(found || { canonical: skill, members: [] })
    })
  }

  useEffect(loadGroup, [skill])

  useEffect(() => {
    const q = query.trim()
    if (!q) { setMatches([]); return }
    let active = true
    searchSkillAliases(q).then(({ canonicals }) => { if (active) setMatches(canonicals) })
    return () => { active = false }
  }, [query])

  const mutate = async (fn) => {
    setBusy(true)
    try { await fn(); loadGroup(); onChanged?.() } finally { setBusy(false) }
  }

  const assignTo = (canonical) => mutate(() => assignSkillAlias(skill, canonical))
  const removeMember = (member) => mutate(() => removeSkillAliasMember(member))
  const toggleOwned = () => mutate(async () => {
    if (owned) { await removeProfileSkill(skill); setOwned(false) }
    else { await addProfileSkill(skill); setOwned(true) }
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div
        className="w-80 max-w-[90vw] rounded-lg border border-space-border bg-[#0f0f1a] p-4 text-space-text shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold">{skill}</h3>
          <button onClick={onClose} className="text-space-dim hover:text-space-text">✕</button>
        </div>

        <label className="flex items-center gap-2 text-xs mb-3 cursor-pointer">
          <input type="checkbox" checked={owned} onChange={toggleOwned} disabled={busy} />
          A skill I have
        </label>

        <p className="text-xs font-semibold text-space-dim mb-1">Alias group</p>
        <div className="flex flex-wrap gap-1 mb-2">
          {group.members.map((m) => (
            <span key={m} className="inline-flex items-center gap-1 rounded bg-white/10 px-1.5 py-0.5 text-xs">
              {m}
              {m !== group.canonical.toLowerCase() && (
                <button onClick={() => removeMember(m)} disabled={busy} className="text-space-dim hover:text-red-400">✕</button>
              )}
            </span>
          ))}
          {group.members.length === 0 && <span className="text-xs text-space-dim">Not grouped yet.</span>}
        </div>

        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search or create a group…"
          className="w-full rounded border border-space-border bg-transparent px-2 py-1 text-xs mb-1"
        />
        <div className="flex flex-col gap-0.5 max-h-40 overflow-auto">
          {matches.map((c) => (
            <button key={c} onClick={() => assignTo(c)} disabled={busy}
              className="text-left text-xs px-2 py-1 rounded hover:bg-white/10">
              {c}
            </button>
          ))}
          {query.trim() && !matches.some((c) => c.toLowerCase() === query.trim().toLowerCase()) && (
            <button onClick={() => assignTo(query.trim())} disabled={busy}
              className="text-left text-xs px-2 py-1 rounded hover:bg-white/10 text-purple-400">
              + Create group "{query.trim()}"
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
