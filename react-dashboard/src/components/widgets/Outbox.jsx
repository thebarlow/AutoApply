import Widget from '../shared/Widget'
import JobCard from '../shared/JobCard'
import { outboxJobs } from '../../mockData'

const outcomeColor = (outcome) =>
  outcome === 'Applied' ? 'text-green-400' : 'text-space-muted'

export default function Outbox() {
  return (
    <Widget title="Outbox" className="flex-[1.5]">
      <div className="flex flex-col gap-2">
        {outboxJobs.map((job) => (
          <JobCard
            key={job.id}
            title={job.title}
            company={job.company}
            meta={job.outcome}
            metaColor={outcomeColor(job.outcome)}
          />
        ))}
      </div>
    </Widget>
  )
}
