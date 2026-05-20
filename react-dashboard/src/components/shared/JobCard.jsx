import { motion } from 'framer-motion'

export default function JobCard({ title, company, meta, metaColor = 'text-space-dim' }) {
  return (
    <motion.div
      whileHover={{ scale: 1.01, backgroundColor: 'rgba(255,255,255,0.06)' }}
      transition={{ duration: 0.15 }}
      className="flex items-center justify-between rounded-lg px-3 py-2 bg-white/[0.03] border border-white/5"
    >
      <div>
        <p className="text-sm font-medium text-space-text">{title}</p>
        <p className="text-xs text-space-dim">{company}</p>
      </div>
      <span className={`text-xs font-medium ${metaColor}`}>{meta}</span>
    </motion.div>
  )
}
