import { motion } from 'framer-motion'

const STEPS = [
  { n: '1', title: 'Scrape', body: 'Pull job postings from the boards you care about into one inbox.' },
  { n: '2', title: 'Tailor', body: 'Generate a résumé and cover letter tuned to each posting.' },
  { n: '3', title: 'Apply', body: 'Review, refine, and submit — ATS-safe and ready to send.' },
]

export default function HowItWorks() {
  return (
    <section className="px-6 py-20 max-w-5xl mx-auto">
      <h2 className="text-center text-3xl font-bold text-white mb-14">How it works</h2>
      <div className="grid gap-8 sm:grid-cols-3">
        {STEPS.map((s, i) => (
          <motion.div
            key={s.n}
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.4 }}
            transition={{ duration: 0.5, delay: i * 0.1, ease: 'easeOut' }}
            className="text-center"
          >
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-space-accent/20 text-space-accent text-xl font-bold">
              {s.n}
            </div>
            <h3 className="text-lg font-semibold text-white mb-2">{s.title}</h3>
            <p className="text-sm text-space-dim">{s.body}</p>
          </motion.div>
        ))}
      </div>
    </section>
  )
}
