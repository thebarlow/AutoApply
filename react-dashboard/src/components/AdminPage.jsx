import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import Navbar from './Navbar'
import { getMe } from '../api'
import ManageUsers from './admin/ManageUsers'
import ResumeCompare from './admin/ResumeCompare'

const FUNCTIONS = [
  { key: 'users', label: 'Manage Users' },
  { key: 'resume-compare', label: 'Résumé Compare' },
]

export default function AdminPage() {
  const [me, setMe] = useState(undefined) // undefined=loading
  const [active, setActive] = useState('users')

  useEffect(() => {
    getMe().then(setMe).catch(() => setMe(null))
  }, [])

  if (me === undefined) return null
  if (!me?.is_admin) {
    return (
      <div className="min-h-screen flex items-center justify-center text-space-dim">
        <p>Not authorized. <Link to="/" className="text-purple-400 hover:underline">Go home</Link></p>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[#0f0f1a] text-space-text">
      <Navbar me={me} />
      <div className="max-w-5xl mx-auto p-6">
        <div className="flex gap-8 h-[calc(100vh-4rem)]">
          <nav className="w-56 shrink-0 sticky top-6 self-start">
            <p className="text-xs uppercase tracking-widest text-space-dim mb-3">Admin</p>
            <ul className="space-y-2">
              {FUNCTIONS.map((f) => (
                <li key={f.key}>
                  <button
                    onClick={() => setActive(f.key)}
                    className={`w-full text-left text-base font-semibold transition-colors ${
                      active === f.key ? 'text-space-text' : 'text-space-dim hover:text-space-text'
                    }`}
                  >
                    {f.label}
                  </button>
                </li>
              ))}
            </ul>
          </nav>

          <section className="flex-1 min-w-0 overflow-y-auto">
            {active === 'users' && <ManageUsers />}
            {active === 'resume-compare' && <ResumeCompare />}
          </section>
        </div>
      </div>
    </div>
  )
}
