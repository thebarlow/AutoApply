import Widget from '../shared/Widget'
import JobCard from '../shared/JobCard'
import { processingJobs } from '../../mockData'

const stageColor = (stage) =>
  stage === 'Scoring' ? 'text-yellow-400' : 'text-blue-400'

export default function Processing() {
  return (
    <Widget title="Processing" className="flex-[1.5]">
      <div className="flex flex-col gap-2">
        {processingJobs.map((job) => (
          <JobCard
            key={job.id}
            title={job.title}
            company={job.company}
            meta={job.stage}
            metaColor={stageColor(job.stage)}
          />
        ))}
      </div>
    </Widget>
  )
}
