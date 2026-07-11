import { motion } from 'framer-motion'
import { BORDER_CLASS } from '../findjobs/borderStatus'

function ProcessingIcon() {
  const dots = Array.from({ length: 8 }, (_, i) => {
    const angle = (i / 8) * 2 * Math.PI
    const cx = 9 + 6 * Math.cos(angle)
    const cy = 9 + 6 * Math.sin(angle)
    return <circle key={i} cx={cx} cy={cy} r="1.4" fill="#a78bfa" />
  })
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 18 18"
      className="shrink-0 animate-spin"
      style={{ animationDuration: '1.4s' }}
    >
      {dots}
    </svg>
  )
}

function TrashIcon() {
  return (
    <svg className="w-4 h-4 text-space-dim shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2m3 0v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6h14z" />
      <path d="M10 11v6M14 11v6" />
    </svg>
  )
}

export default function JobCard({ title, company, statusIcon, docs = {}, selected = false, state, score, appliedAt, scrapedAt, salaryMin, salaryMax, salaryRaw, flagged = false, borderStatus = null, leading = null }) {
  const hasResume = docs.resume
  const hasCoverLetter = docs.coverLetter

  function ScorePill() {
    if (score == null) return null
    const pct = Math.round(score * 100)
    const color = pct >= 70 ? 'text-green-400' : pct >= 40 ? 'text-yellow-400' : 'text-red-400'
    return <span className={`text-xs font-semibold shrink-0 ${color}`}>{pct}%</span>
  }

  function formatSalary() {
    if (salaryMin != null) {
      const fmt = (n) => n >= 1000 ? `$${Math.round(n / 1000)}K` : `$${n}`
      if (salaryMax != null && salaryMax !== salaryMin) return `${fmt(salaryMin)}–${fmt(salaryMax)}`
      return fmt(salaryMin)
    }
    if (salaryRaw) {
      const nums = salaryRaw.replace(/,/g, '').match(/\d+(?:\.\d+)?[kK]?/g)
      if (nums && nums.length > 0) {
        const toNum = (s) => parseFloat(s) * (/[kK]$/.test(s) ? 1000 : 1)
        const values = nums.map(toNum).filter(n => n > 0)
        if (values.length === 0) return salaryRaw
        const min = Math.min(...values)
        const max = Math.max(...values)
        const fmt = (n) => n >= 1000 ? `$${Math.round(n / 1000)}K` : `$${n}`
        return min === max ? fmt(min) : `${fmt(min)}–${fmt(max)}`
      }
      if (salaryRaw.length <= 20) return salaryRaw
    }
    return null
  }

  function formatDate() {
    const iso = appliedAt || scrapedAt
    if (!iso) return null
    const label = appliedAt ? 'Applied' : 'Added'
    const d = new Date(iso)
    const formatted = d.toLocaleDateString('en-US', { month: 'numeric', day: 'numeric', year: '2-digit' })
    return `${label} ${formatted}`
  }

  const salaryText = formatSalary()
  const dateText = formatDate()
  const hasMetadata = salaryText || dateText

  return (
    <motion.div
      whileHover={{ scale: 1.01, backgroundColor: 'rgba(255,255,255,0.06)' }}
      transition={{ duration: 0.15 }}
      className={`flex items-stretch justify-between rounded-lg px-3 py-2 border gap-3 transition-colors
        ${selected ? 'bg-purple-900/30' : 'bg-white/[0.03]'}
        ${borderStatus ? BORDER_CLASS[borderStatus]
          : selected ? 'border-purple-500/50' : 'border-white/5'}`}
    >
      {leading}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          {flagged && <FlagIconFilled />}
          <p className="text-sm font-medium text-space-text truncate">{title}</p>
        </div>
        <p className="text-xs text-space-dim">{company}</p>
        {hasMetadata && (
          <div className="flex justify-between mt-0.5">
            <span className="text-xs text-space-dim">{salaryText ?? ''}</span>
            <span className="text-xs text-space-dim">{dateText ?? ''}</span>
          </div>
        )}
      </div>

      {(hasResume || hasCoverLetter) && (
        <div className="flex items-center gap-1.5">
          {hasResume && (
            <img src="/assets/resume_icon_64.png" alt="Resume" className="h-7 w-auto object-contain opacity-80" />
          )}
          {hasCoverLetter && (
            <img src="/assets/coverletter_icon_64.png" alt="Cover Letter" className="h-7 w-auto object-contain opacity-80" />
          )}
        </div>
      )}

      <div className="flex items-center self-stretch gap-1.5">
        <ScorePill />
        {state === 'deleted' && <TrashIcon />}
        {statusIcon}
      </div>
    </motion.div>
  )
}

function EyeIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" className="shrink-0">
      <path d="M1.5 9 C 3.5 5, 6 4, 9 4 C 12 4, 14.5 5, 16.5 9 C 14.5 13, 12 14, 9 14 C 6 14, 3.5 13, 1.5 9 Z" stroke="#60A5FA" strokeWidth="1.2" fill="none"/>
      <circle cx="9" cy="9" r="2.2" stroke="#60A5FA" strokeWidth="1.2" fill="none"/>
      <circle cx="9" cy="9" r="0.9" fill="#60A5FA"/>
    </svg>
  )
}

function WarningIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" className="shrink-0">
      <path d="M9 1.5 L17 16 L1 16 Z" stroke="#EF4444" strokeWidth="1.2" strokeLinejoin="round" fill="none"/>
      <text x="9" y="13.5" textAnchor="middle" fontSize="9" fontWeight="700" fill="#EF4444">!</text>
    </svg>
  )
}

function FlagIconFilled() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="#ef4444" stroke="#ef4444" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="shrink-0">
      <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/>
      <line x1="4" y1="22" x2="4" y2="15"/>
    </svg>
  )
}

export { ProcessingIcon, EyeIcon, WarningIcon }
