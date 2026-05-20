import Widget from '../shared/Widget'
import { settings } from '../../mockData'

const fields = [
  { label: 'Resume Path', value: settings.resumePath },
  { label: 'Target Roles', value: settings.targetRoles },
  { label: 'Location', value: settings.locationPreference },
  { label: 'Model', value: settings.modelInUse },
]

export default function Settings() {
  return (
    <Widget title="Settings / Details">
      <div className="flex flex-col gap-3">
        {fields.map(({ label, value }) => (
          <div key={label} className="flex flex-col gap-0.5">
            <span className="text-xs text-space-dim">{label}</span>
            <span className="text-sm text-space-text truncate">{value}</span>
          </div>
        ))}
      </div>
    </Widget>
  )
}
