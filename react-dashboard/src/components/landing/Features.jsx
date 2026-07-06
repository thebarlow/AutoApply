import { motion } from 'framer-motion'

const FEATURES = [
  { title: 'AI-tailored documents', body: 'Every résumé and cover letter is rewritten to match the specific role.' },
  { title: 'ATS-safe formatting', body: 'Clean, parseable output that applicant-tracking systems can read.' },
  { title: 'Job scoring & skill matching', body: 'See how well each posting fits before you spend time on it.' },
  { title: 'Live PDF preview', body: 'Edit and watch the real PDF update side-by-side, instantly.' },
]

export default function Features() {
  return (
    <section className="px-6 py-20 max-w-5xl mx-auto">
      <div className="grid gap-6 sm:grid-cols-2">
        {FEATURES.map((f, i) => (
          <motion.div
            key={f.title}
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.3 }}
            transition={{ duration: 0.5, delay: i * 0.08, ease: 'easeOut' }}
            className="rounded-xl border border-space-border bg-space-card/60 p-6"
          >
            <h3 className="text-lg font-semibold text-white mb-2">{f.title}</h3>
            <p className="text-sm text-space-dim">{f.body}</p>
          </motion.div>
        ))}
      </div>
    </section>
  )
}
