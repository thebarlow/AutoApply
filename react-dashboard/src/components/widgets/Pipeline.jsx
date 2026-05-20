import { motion } from 'framer-motion'
import JobCard, { NewIcon, ProcessingIcon } from '../shared/JobCard'
import { inboxJobs, processingJobs, outboxJobs } from '../../mockData'

const outcomeColor = (outcome) =>
  outcome === 'Applied' ? 'text-green-400' : 'text-space-muted'

function Section({ title, children }) {
  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-xs font-semibold uppercase tracking-widest text-space-dim border-b border-space-border pb-1">
        {title}
      </h3>
      <div className="flex flex-col gap-2">{children}</div>
    </div>
  )
}

export default function Pipeline() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: 'easeOut' }}
      whileHover={{ boxShadow: '0 0 24px 2px rgba(109,40,217,0.15)' }}
      className="bg-white/5 border border-space-border rounded-xl p-4 flex flex-col gap-4 overflow-hidden h-full"
    >
      <Section title="Inbox">
        {inboxJobs.map((job) => (
          <JobCard
            key={job.id}
            title={job.title}
            company={job.company}
            docs={job.docs}
            statusIcon={!job.viewed ? <NewIcon /> : null}
          />
        ))}
      </Section>

      <Section title="Processing">
        {processingJobs.map((job) => (
          <JobCard
            key={job.id}
            title={job.title}
            company={job.company}
            docs={job.docs}
            statusIcon={<ProcessingIcon />}
          />
        ))}
      </Section>

      <Section title="Outbound">
        {outboxJobs.map((job) => (
          <JobCard
            key={job.id}
            title={job.title}
            company={job.company}
            docs={job.docs}
            statusIcon={
              <span className={`text-xs font-medium shrink-0 ${outcomeColor(job.outcome)}`}>
                {job.outcome}
              </span>
            }
          />
        ))}
      </Section>
    </motion.div>
  )
}
