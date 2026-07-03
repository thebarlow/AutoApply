import { motion } from 'framer-motion'

export default function Hero({ isAuthed, onCtaClick }) {
  return (
    <section className="relative overflow-hidden px-6 pt-28 pb-24 text-center">
      <div className="absolute inset-0 -z-10 bg-[radial-gradient(ellipse_at_top,rgba(109,40,217,0.35),transparent_60%)]" />
      <motion.h1
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: 'easeOut' }}
        className="mx-auto max-w-3xl text-4xl sm:text-5xl font-bold tracking-tight text-white"
      >
        Land more interviews. Apply in a fraction of the time.
      </motion.h1>
      <motion.p
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.1, ease: 'easeOut' }}
        className="mx-auto mt-6 max-w-xl text-lg text-space-dim"
      >
        AutoApply scrapes jobs, tailors your résumé and cover letter to each one, and
        gets you ready to apply — all from one dashboard.
      </motion.p>
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.2, ease: 'easeOut' }}
        className="mt-10"
      >
        <button
          onClick={onCtaClick}
          className="px-8 py-3 rounded-lg bg-space-accent hover:bg-purple-500 text-white text-base font-semibold transition-colors shadow-lg shadow-purple-900/40"
        >
          {isAuthed ? 'Go to dashboard' : 'Get started'}
        </button>
      </motion.div>
    </section>
  )
}
