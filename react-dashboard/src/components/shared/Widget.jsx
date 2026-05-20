import { motion } from 'framer-motion'

export default function Widget({ title, children, className = '' }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: 'easeOut' }}
      whileHover={{ boxShadow: '0 0 24px 2px rgba(109,40,217,0.15)' }}
      className={`
        bg-white/5 border border-space-border rounded-xl p-4 flex flex-col gap-3
        ${className}
      `}
    >
      <h2 className="text-xs font-semibold uppercase tracking-widest text-space-dim">
        {title}
      </h2>
      <div className="flex-1">{children}</div>
    </motion.div>
  )
}
