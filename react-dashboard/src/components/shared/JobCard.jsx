import { motion } from 'framer-motion'

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

export default function JobCard({ title, company, statusIcon, docs = {}, selected = false }) {
  const hasResume = docs.resume
  const hasCoverLetter = docs.coverLetter

  return (
    <motion.div
      whileHover={{ scale: 1.01, backgroundColor: 'rgba(255,255,255,0.06)' }}
      transition={{ duration: 0.15 }}
      className={`flex items-stretch justify-between rounded-lg px-3 py-2 border gap-3 transition-colors
        ${selected
          ? 'bg-purple-900/30 border-purple-500/50'
          : 'bg-white/[0.03] border-white/5'
        }`}
    >
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-space-text truncate">{title}</p>
        <p className="text-xs text-space-dim">{company}</p>
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

      <div className="flex items-center self-stretch">
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

export { ProcessingIcon, EyeIcon, WarningIcon }
