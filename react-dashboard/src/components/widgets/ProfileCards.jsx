import { useState, useEffect } from 'react'
import { getProfiles, setActiveProfile } from '../../api'

export default function ProfileCards({ onSelect, onCreateProfile }) {
  const [profiles, setProfiles] = useState([])
  const [activeId, setActiveId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [settingActive, setSettingActive] = useState(null)

  useEffect(() => {
    getProfiles()
      .then((data) => {
        setProfiles(data.profiles ?? [])
        setActiveId(data.active_id ?? null)
      })
      .catch(() => setError('Failed to load profiles'))
      .finally(() => setLoading(false))
  }, [])

  const handleSetActive = async (id) => {
    setSettingActive(id)
    try {
      await setActiveProfile(id)
      setActiveId(id)
      window.dispatchEvent(new CustomEvent('auto-apply:prompt-status-stale'))
    } finally {
      setSettingActive(null)
    }
  }

  if (loading) return <p className="text-xs text-space-dim">Loading…</p>
  if (error) return <p className="text-xs text-red-400">{error}</p>

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        {profiles.length === 0 && (
          <p className="text-sm text-space-dim text-center py-2">
            A user profile is required to use the app — create one below!
          </p>
        )}
        {profiles.map((profile) => (
          <div
            key={profile.id}
            className={`flex items-center gap-2 rounded-lg border border-white/5 border-l-4 bg-white/[0.03]
              ${activeId === profile.id ? 'border-l-purple-500' : 'border-l-transparent'}`}
          >
            <button
              onClick={() => onSelect(profile.id)}
              className="flex-1 flex flex-col gap-0.5 px-3 py-2.5 text-left hover:bg-white/[0.03] transition-colors rounded-lg min-w-0"
            >
              <p className="text-sm font-medium text-space-text">{profile.name || 'Unnamed'}</p>
              {(profile.first_name || profile.last_name) && (
                <p className="text-xs text-space-dim">
                  {[profile.first_name, profile.last_name].filter(Boolean).join(' ')}
                </p>
              )}
            </button>
            <div className="pr-2 shrink-0">
              {activeId === profile.id
                ? <span className="text-xs font-medium text-purple-400">Active</span>
                : (
                  <button
                    onClick={() => handleSetActive(profile.id)}
                    disabled={settingActive === profile.id}
                    className="text-xs text-space-dim hover:text-space-text border border-space-border hover:border-purple-500/50 rounded px-2 py-0.5 transition-colors disabled:opacity-50"
                  >
                    {settingActive === profile.id ? '…' : 'Set Active'}
                  </button>
                )
              }
            </div>
          </div>
        ))}
      </div>
      <button
        onClick={onCreateProfile}
        className={`w-full py-2 rounded-lg border text-sm transition-colors
          ${profiles.length === 0
            ? 'shiny-border border-transparent bg-[#0a0a14] text-purple-300 hover:text-white'
            : 'border-space-border hover:border-purple-500/50 text-space-dim hover:text-space-text'
          }`}
      >
        + Create Profile
      </button>
    </div>
  )
}
