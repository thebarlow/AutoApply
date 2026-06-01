import { useState, useEffect } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer,
  PieChart, Pie, Cell, Sector,
} from 'recharts'
import { getProfiles, getStats, getSkillFrequency, getJobsForSkill } from '../../api'
import ProfileCards from './ProfileCards'

const WINDOWS = [
  { key: 'session', label: 'Session' },
  { key: 'today', label: 'Today' },
  { key: 'week', label: 'Week' },
  { key: 'all_time', label: 'All Time' },
]

const STATE_LABELS = {
  new: 'New',
  pending_review: 'Pending Review',
  ready: 'Ready',
  applied: 'Applied',
  contact: 'In Contact',
  rejected: 'Rejected',
}

const STATE_COLORS = {
  new: '#7c3aed',
  pending_review: '#f59e0b',
  ready: '#3b82f6',
  applied: '#10b981',
  contact: '#06b6d4',
  rejected: '#ef4444',
}

const SKILL_FIELDS = [
  { key: 'skills', label: 'Required / Preferred' },
  { key: 'tech_stack', label: 'Tech Stack' },
]

const REQUIRED_COLOR = '#7c3aed'
const PREFERRED_COLOR = '#3b82f6'
const TECH_COLORS = ['#7c3aed', '#3b82f6', '#06b6d4', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899']
const OTHER_COLOR = '#555'
const ACTIVE_OUTLINE = '#e9d5ff'

// Renders the selected pie slice enlarged + outlined (the "raised / pulled-out" effect).
function renderRaisedSlice(props) {
  const { cx, cy, innerRadius, outerRadius, startAngle, endAngle, fill } = props
  return (
    <Sector
      cx={cx}
      cy={cy}
      innerRadius={innerRadius}
      outerRadius={outerRadius + 6}
      startAngle={startAngle}
      endAngle={endAngle}
      fill={fill}
      stroke={ACTIVE_OUTLINE}
      strokeWidth={2}
    />
  )
}

export default function UserHome({ onSelect, onCreateProfile, onSkillFilter, activeSkill }) {
  const [activeProfile, setActiveProfile] = useState(null)
  const [profilesLoaded, setProfilesLoaded] = useState(false)
  const [showSwitchUser, setShowSwitchUser] = useState(false)
  const [win, setWin] = useState('session')
  const [stats, setStats] = useState(null)
  const [statsLoading, setStatsLoading] = useState(false)
  const [statsError, setStatsError] = useState(null)
  const [skillFreq, setSkillFreq] = useState(null)
  const [skillField, setSkillField] = useState('skills')
  const [skillError, setSkillError] = useState(null)

  const fetchProfiles = () => {
    getProfiles()
      .then(({ profiles, active_id }) => {
        const active = profiles.find((p) => p.id === active_id) ?? null
        setActiveProfile(active)
      })
      .catch(() => setActiveProfile(null))
      .finally(() => setProfilesLoaded(true))
  }

  useEffect(() => {
    fetchProfiles()
  }, [])

  useEffect(() => {
    if (!activeProfile) return
    setStatsLoading(true)
    setStatsError(null)
    getStats(win)
      .then(setStats)
      .catch(() => setStatsError('Could not load stats'))
      .finally(() => setStatsLoading(false))
  }, [win, activeProfile])

  useEffect(() => {
    if (!activeProfile) return
    setSkillError(null)
    setSkillFreq(null)
    getSkillFrequency()
      .then(setSkillFreq)
      .catch(() => setSkillError('Could not load skill data'))
  }, [activeProfile])

  if (!profilesLoaded) {
    return <p className="text-xs text-space-dim">Loading…</p>
  }

  if (!activeProfile) {
    return <ProfileCards onSelect={onSelect} onCreateProfile={onCreateProfile} onActiveChanged={fetchProfiles} />
  }

  if (showSwitchUser) {
    return (
      <div className="flex flex-col gap-3">
        <button
          onClick={() => setShowSwitchUser(false)}
          className="flex items-center gap-1.5 text-xs text-space-dim hover:text-purple-400 transition-colors self-start"
        >
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M10 12L6 8l4-4" />
          </svg>
          Back
        </button>
        <ProfileCards onSelect={onSelect} onCreateProfile={onCreateProfile} onActiveChanged={fetchProfiles} />
      </div>
    )
  }

  const fullName = [activeProfile.first_name, activeProfile.last_name].filter(Boolean).join(' ')
  const displayName = fullName || activeProfile.name || 'there'

  const pieData = stats
    ? Object.entries(STATE_LABELS)
        .map(([key, label]) => ({ key, name: label, value: stats.by_state[key] ?? 0 }))
        .filter((d) => d.value > 0)
    : []

  const totalJobs = skillFreq?.total_jobs ?? 0
  const isTechStack = skillField === 'tech_stack'
  const rawRows = skillFreq ? (isTechStack ? skillFreq.tech_stack : skillFreq.skills) : []
  // API returns skills/tech_stack pre-sorted by frequency desc, so slicing the
  // first 12 yields the top skills without a client-side sort.
  const skillBars = rawRows.slice(0, 12).map((row) => {
    const total = isTechStack ? row.count : row.required + row.preferred
    return {
      skill: row.skill,
      required: isTechStack ? 0 : row.required,
      preferred: isTechStack ? 0 : row.preferred,
      count: isTechStack ? row.count : 0,
      total,
      pct: totalJobs ? Math.round((total / totalJobs) * 100) : 0,
    }
  })

  const handleSkillBarClick = (data) => {
    // Recharts Bar onClick passes the datum; row fields may be top-level or under .payload.
    const skill = data?.skill ?? data?.payload?.skill
    if (!skill || !onSkillFilter) return
    getJobsForSkill(skill)
      .then(({ job_keys }) => onSkillFilter({ skill, jobKeys: job_keys }))
      .catch(() => setSkillError('Could not load jobs for skill'))
  }

  // Tech Stack pie: top 8 skills + an aggregated, non-clickable "Other" slice.
  const techList = skillFreq?.tech_stack ?? []
  const otherCount = techList.slice(8).reduce((sum, r) => sum + r.count, 0)
  const pieSlices = [
    ...techList.slice(0, 8).map((r, i) => ({
      skill: r.skill, value: r.count, color: TECH_COLORS[i % TECH_COLORS.length], isOther: false,
    })),
    ...(otherCount > 0 ? [{ skill: 'Other', value: otherCount, color: OTHER_COLOR, isOther: true }] : []),
  ]
  const activeSliceIndex = pieSlices.findIndex((s) => !s.isOther && s.skill === activeSkill)
  const hasSkillData = isTechStack ? pieSlices.length > 0 : skillBars.length > 0

  const handleSliceClick = (slice) => {
    if (!slice || slice.isOther) return
    handleSkillBarClick({ skill: slice.skill })
  }

  return (
    <div className="flex flex-col gap-5">
      <div>
        <p className="text-xs text-space-dim uppercase tracking-widest mb-0.5">Welcome back</p>
        <h2 className="text-lg font-semibold text-space-text">{displayName}</h2>
      </div>

      <div className="flex gap-1.5">
        {WINDOWS.map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setWin(key)}
            className={`px-3 py-1 rounded text-xs font-semibold transition-colors
              ${win === key ? 'bg-purple-600 text-white' : 'text-space-dim hover:text-space-text border border-space-border'}`}
          >
            {label}
          </button>
        ))}
      </div>

      {statsError && (
        <p className="text-xs text-space-dim/60">{statsError}</p>
      )}

      {!statsError && (
        <>
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-space-dim mb-2">Activity</p>
            {statsLoading && !stats && <p className="text-xs text-space-dim">Loading…</p>}
            {!statsLoading && stats && stats.bars.length === 0 && (
              <p className="text-xs text-space-dim">No activity yet.</p>
            )}
            {!statsLoading && stats && stats.bars.length > 0 && (
              <ResponsiveContainer width="100%" height={160}>
                <BarChart data={stats.bars} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
                  <XAxis dataKey="label" tick={{ fontSize: 10, fill: '#8888aa' }} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 10, fill: '#8888aa' }} />
                  <Tooltip
                    contentStyle={{ background: '#0f0f1a', border: '1px solid #2a2a4a', borderRadius: 8, fontSize: 11 }}
                    labelStyle={{ color: '#c8c8e8' }}
                  />
                  <Legend wrapperStyle={{ fontSize: 11, color: '#8888aa' }} />
                  <Bar dataKey="scraped" name="Scraped" fill="#7c3aed" radius={[3, 3, 0, 0]} />
                  <Bar dataKey="resumes" name="Resumes" fill="#3b82f6" radius={[3, 3, 0, 0]} />
                  <Bar dataKey="covers" name="Covers" fill="#0d9488" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>

          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-space-dim mb-2">Pipeline</p>
            {statsLoading && !stats && <p className="text-xs text-space-dim">Loading…</p>}
            {!statsLoading && stats && pieData.length === 0 && (
              <p className="text-xs text-space-dim">No jobs yet.</p>
            )}
            {!statsLoading && stats && pieData.length > 0 && (
              <div className="flex items-center gap-3">
                <ResponsiveContainer width={120} height={120}>
                  <PieChart>
                    <Pie
                      data={pieData}
                      cx="50%"
                      cy="50%"
                      innerRadius={30}
                      outerRadius={55}
                      dataKey="value"
                      strokeWidth={0}
                    >
                      {pieData.map((entry) => (
                        <Cell key={entry.name} fill={STATE_COLORS[entry.key] ?? '#555'} />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={{ background: '#0f0f1a', border: '1px solid #2a2a4a', borderRadius: 8, fontSize: 11 }}
                    />
                  </PieChart>
                </ResponsiveContainer>
                <div className="flex flex-col gap-1">
                  {pieData.map((entry) => (
                    <div key={entry.name} className="flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full shrink-0" style={{ background: STATE_COLORS[entry.key] ?? '#555' }} />
                      <span className="text-xs text-space-dim">{entry.name}</span>
                      <span className="text-xs font-medium text-space-text ml-auto pl-2">{entry.value}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-space-dim mb-2">In-Demand Skills</p>
            <div className="flex gap-1.5 mb-2">
              {SKILL_FIELDS.map(({ key, label }) => (
                <button
                  key={key}
                  onClick={() => setSkillField(key)}
                  className={`px-3 py-1 rounded text-xs font-semibold transition-colors
                    ${skillField === key ? 'bg-purple-600 text-white' : 'text-space-dim hover:text-space-text border border-space-border'}`}
                >
                  {label}
                </button>
              ))}
            </div>
            {skillError && <p className="text-xs text-space-dim/60">{skillError}</p>}
            {!skillError && skillFreq && !hasSkillData && (
              <p className="text-xs text-space-dim">No skill data yet.</p>
            )}
            {!skillError && skillFreq && hasSkillData && (
              isTechStack ? (
                <div className="flex items-center gap-3">
                  <ResponsiveContainer width={120} height={120}>
                    <PieChart>
                      <Pie
                        data={pieSlices}
                        cx="50%"
                        cy="50%"
                        innerRadius={30}
                        outerRadius={50}
                        dataKey="value"
                        strokeWidth={0}
                        activeIndex={activeSliceIndex >= 0 ? activeSliceIndex : undefined}
                        activeShape={renderRaisedSlice}
                        onClick={(_data, index) => handleSliceClick(pieSlices[index])}
                      >
                        {pieSlices.map((s) => (
                          <Cell key={s.skill} fill={s.color} cursor={s.isOther ? 'default' : 'pointer'} />
                        ))}
                      </Pie>
                      <Tooltip
                        contentStyle={{ background: '#0f0f1a', border: '1px solid #2a2a4a', borderRadius: 8, fontSize: 11 }}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="flex flex-col gap-1">
                    {pieSlices.map((s) => (
                      <button
                        key={s.skill}
                        onClick={() => handleSliceClick(s)}
                        disabled={s.isOther}
                        className={`flex items-center gap-1.5 text-left ${s.isOther ? 'cursor-default' : 'hover:opacity-80'} transition-opacity`}
                      >
                        <span className="w-2 h-2 rounded-full shrink-0" style={{ background: s.color }} />
                        <span className={`text-xs ${s.skill === activeSkill ? 'text-purple-300 font-semibold' : 'text-space-dim'}`}>{s.skill}</span>
                        <span className="text-xs font-medium text-space-text ml-auto pl-2">{s.value}</span>
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                <ResponsiveContainer width="100%" height={Math.max(160, skillBars.length * 22)}>
                  <BarChart
                    layout="vertical"
                    data={skillBars}
                    margin={{ top: 4, right: 12, bottom: 0, left: 8 }}
                  >
                    <defs>
                      <filter id="skill-bar-raise" x="-20%" y="-20%" width="140%" height="140%">
                        <feDropShadow dx="0" dy="0" stdDeviation="3" floodColor={ACTIVE_OUTLINE} floodOpacity="0.9" />
                      </filter>
                    </defs>
                    <XAxis type="number" allowDecimals={false} tick={{ fontSize: 10, fill: '#8888aa' }} />
                    <YAxis
                      type="category"
                      dataKey="skill"
                      width={90}
                      tick={{ fontSize: 10, fill: '#8888aa' }}
                    />
                    <Tooltip
                      cursor={false}
                      contentStyle={{ background: '#0f0f1a', border: '1px solid #2a2a4a', borderRadius: 8, fontSize: 11 }}
                      labelStyle={{ color: '#c8c8e8' }}
                      formatter={(value, name, item) => [
                        `${value} (${item.payload.pct}% of postings)`,
                        name,
                      ]}
                    />
                    <Legend wrapperStyle={{ fontSize: 11, color: '#8888aa' }} />
                    <Bar dataKey="required" name="Required" stackId="skill" cursor="pointer" onClick={handleSkillBarClick}>
                      {skillBars.map((row) => (
                        <Cell
                          key={row.skill}
                          fill={REQUIRED_COLOR}
                          stroke={row.skill === activeSkill ? ACTIVE_OUTLINE : 'none'}
                          strokeWidth={row.skill === activeSkill ? 2 : 0}
                          filter={row.skill === activeSkill ? 'url(#skill-bar-raise)' : undefined}
                        />
                      ))}
                    </Bar>
                    <Bar dataKey="preferred" name="Preferred" stackId="skill" radius={[0, 3, 3, 0]} cursor="pointer" onClick={handleSkillBarClick}>
                      {skillBars.map((row) => (
                        <Cell
                          key={row.skill}
                          fill={PREFERRED_COLOR}
                          stroke={row.skill === activeSkill ? ACTIVE_OUTLINE : 'none'}
                          strokeWidth={row.skill === activeSkill ? 2 : 0}
                          filter={row.skill === activeSkill ? 'url(#skill-bar-raise)' : undefined}
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )
            )}
          </div>
        </>
      )}

      <button
        onClick={() => setShowSwitchUser(true)}
        className="w-full py-2 rounded-lg border border-space-border text-sm text-space-dim hover:text-space-text hover:border-purple-500/50 transition-colors mt-2"
      >
        Switch User
      </button>
    </div>
  )
}
