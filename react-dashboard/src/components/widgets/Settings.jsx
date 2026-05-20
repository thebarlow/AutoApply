import { useState, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { users as mockUsers, activeUserId as defaultActiveId, settings as mockSettings } from '../../mockData'

// ─── icons ────────────────────────────────────────────────────────────────────

function BackArrow() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10 12L6 8l4-4" />
    </svg>
  )
}

const inputClass =
  'w-full bg-white/5 border border-space-border rounded-lg px-3 py-2 text-sm text-space-text placeholder-space-dim focus:outline-none focus:border-purple-500 transition-colors'

// ─── Advanced tab ─────────────────────────────────────────────────────────────

function AdvancedTab() {
  const [provider, setProvider] = useState(mockSettings.provider)
  const [model, setModel] = useState(mockSettings.model)
  const [apiKey, setApiKey] = useState(mockSettings.apiKey)

  return (
    <div className="flex flex-col gap-4">
      <p className="text-xs font-semibold uppercase tracking-widest text-space-dim">Provider</p>
      <div className="flex flex-col gap-3">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-space-dim">LLM Provider</label>
          <input
            className={inputClass}
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            placeholder="e.g. anthropic, openai"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-space-dim">Model (comma-separated)</label>
          <input
            className={inputClass}
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder="e.g. claude-sonnet-4-6, gpt-4o"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-space-dim">API Key</label>
          <input
            type="password"
            className={inputClass}
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="sk-..."
          />
        </div>
      </div>
    </div>
  )
}

// ─── Create Profile ───────────────────────────────────────────────────────────

function CreateProfile() {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [droppedFile, setDroppedFile] = useState(null)
  const [dragging, setDragging] = useState(false)
  const fileInputRef = useRef()

  const handleDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) setDroppedFile(file)
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <label className="text-xs text-space-dim">Full Name</label>
        <input className={inputClass} value={name} onChange={(e) => setName(e.target.value)} placeholder="Jane Doe" />
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-xs text-space-dim">Email</label>
        <input className={inputClass} value={email} onChange={(e) => setEmail(e.target.value)} placeholder="jane@example.com" />
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-xs text-space-dim">Resume</label>
        <div
          onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          className={`flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-4 py-6 cursor-pointer transition-colors
            ${dragging ? 'border-purple-400 bg-purple-400/10' : 'border-space-border hover:border-purple-500/50'}`}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.doc,.docx"
            className="hidden"
            onChange={(e) => setDroppedFile(e.target.files[0])}
          />
          {droppedFile ? (
            <p className="text-sm text-purple-400 text-center">{droppedFile.name}</p>
          ) : (
            <>
              <p className="text-sm text-space-dim text-center">Drop resume here or click to browse</p>
              <p className="text-xs text-space-dim/60">.pdf, .doc, .docx</p>
            </>
          )}
        </div>
      </div>
      <button className="mt-2 w-full py-2 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-sm font-semibold transition-colors">
        Save Profile
      </button>
    </div>
  )
}

// ─── Profile List ─────────────────────────────────────────────────────────────

function ProfileList({ onCreateProfile }) {
  const [activeId, setActiveId] = useState(
    mockUsers.length === 1 ? mockUsers[0].id : defaultActiveId
  )

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        {mockUsers.map((user) => (
          <label
            key={user.id}
            className="flex items-center gap-3 rounded-lg px-3 py-2.5 bg-white/[0.03] border border-white/5 cursor-pointer hover:bg-white/[0.06] transition-colors"
          >
            <input
              type="radio"
              name="activeUser"
              value={user.id}
              checked={activeId === user.id}
              onChange={() => setActiveId(user.id)}
              className="accent-purple-500"
            />
            <div>
              <p className="text-sm font-medium text-space-text">{user.fullName}</p>
              <p className="text-xs text-space-dim">{user.email}</p>
            </div>
          </label>
        ))}
      </div>
      <button
        onClick={onCreateProfile}
        className="w-full py-2 rounded-lg border border-space-border hover:border-purple-500/50 text-sm text-space-dim hover:text-space-text transition-colors"
      >
        Create Profile
      </button>
    </div>
  )
}

// ─── User tab ─────────────────────────────────────────────────────────────────

function UserTab({ onProfileSettings }) {
  const activeUser = mockUsers.find((u) => u.id === defaultActiveId) ?? null

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-space-text">
        {activeUser ? `Welcome back, ${activeUser.fullName}.` : 'Please select an active user!'}
      </p>
      <button
        onClick={onProfileSettings}
        className="w-full py-2 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-sm font-semibold transition-colors"
      >
        Profile Settings
      </button>
    </div>
  )
}

// ─── Tasks tab ────────────────────────────────────────────────────────────────

function TasksTab() {
  return <div className="text-sm text-space-dim">No active tasks.</div>
}

// ─── Root ─────────────────────────────────────────────────────────────────────

const TABS = ['User', 'Tasks', 'Advanced']

const slideVariants = {
  enter: { x: 40, opacity: 0 },
  center: { x: 0, opacity: 1 },
  exit: { x: -40, opacity: 0 },
}

export default function Settings() {
  const [activeTab, setActiveTab] = useState('User')
  // view stack: 'main' | 'profiles' | 'createProfile'
  const [view, setView] = useState('main')

  const viewTitle = view === 'profiles' ? 'Profile Settings' : 'Create Profile'

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: 'easeOut' }}
      whileHover={{ boxShadow: '0 0 24px 2px rgba(109,40,217,0.15)' }}
      className="bg-white/5 border border-space-border rounded-xl flex flex-col overflow-hidden h-full"
    >
      {/* Header: tab bar or sub-view title */}
      {view === 'main' ? (
        <div className="flex border-b border-space-border shrink-0">
          {TABS.map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`flex-1 py-2.5 text-xs font-semibold uppercase tracking-widest transition-colors
                ${activeTab === tab
                  ? 'text-purple-400 border-b-2 border-purple-400 bg-white/5'
                  : 'text-space-dim hover:text-space-text'
                }`}
            >
              {tab}
            </button>
          ))}
        </div>
      ) : (
        <div className="flex items-center gap-2 px-4 py-3 border-b border-space-border shrink-0">
          <button
            onClick={() => setView(view === 'createProfile' ? 'profiles' : 'main')}
            className="text-space-dim hover:text-purple-400 transition-colors"
          >
            <BackArrow />
          </button>
          <span className="text-xs font-semibold uppercase tracking-widest text-space-dim">
            {viewTitle}
          </span>
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 relative">
        <AnimatePresence mode="wait">
          <motion.div
            key={view === 'main' ? activeTab : view}
            variants={slideVariants}
            initial="enter"
            animate="center"
            exit="exit"
            transition={{ duration: 0.2 }}
          >
            {view === 'main' && activeTab === 'User' && (
              <UserTab onProfileSettings={() => setView('profiles')} />
            )}
            {view === 'main' && activeTab === 'Tasks' && <TasksTab />}
            {view === 'main' && activeTab === 'Advanced' && <AdvancedTab />}
            {view === 'profiles' && (
              <ProfileList onCreateProfile={() => setView('createProfile')} />
            )}
            {view === 'createProfile' && (
              <CreateProfile onBack={() => setView('profiles')} />
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </motion.div>
  )
}
