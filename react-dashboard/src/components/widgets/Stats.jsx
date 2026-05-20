import Widget from '../shared/Widget'
import { stats } from '../../mockData'

const tiles = [
  { label: 'Total Jobs', value: stats.totalJobs },
  { label: 'Applied', value: stats.applied },
  { label: 'Success Rate', value: stats.successRate },
  { label: 'Credits Used', value: stats.creditsUsed },
]

export default function Stats() {
  return (
    <Widget title="Stats">
      <div className="grid grid-cols-2 gap-3">
        {tiles.map(({ label, value }) => (
          <div
            key={label}
            className="bg-white/5 rounded-lg p-3 flex flex-col gap-1 border border-white/5"
          >
            <span className="text-2xl font-bold text-white">{value}</span>
            <span className="text-xs text-space-dim">{label}</span>
          </div>
        ))}
      </div>
    </Widget>
  )
}
