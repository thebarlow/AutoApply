import Widget from '../shared/Widget'
import JobCard from '../shared/JobCard'
import { inboxJobs } from '../../mockData'

export default function Inbox() {
  return (
    <Widget title="Inbox" className="flex-[2]">
      <div className="flex flex-col gap-2">
        {inboxJobs.map((job) => (
          <JobCard
            key={job.id}
            title={job.title}
            company={job.company}
            meta={job.dateAdded}
            metaColor="text-space-dim"
          />
        ))}
      </div>
    </Widget>
  )
}
