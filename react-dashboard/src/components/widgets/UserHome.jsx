import { useState, useEffect } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer,
  PieChart, Pie, Cell, Sector, LabelList,
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
  { key: 'skills', label: 'By Skill' },
  { key: 'categories', label: 'Categories' },
]

const TIER_COLORS = { high: '#7c3aed', med: '#3b82f6', low: '#06b6d4' }
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

// Donut + legend for a set of slices. `labelKey` names each slice ('category' or 'skill').
// Slices: { [labelKey]: string, value: number, color: string }.
function SkillPie({ slices, labelKey, emphasisIndex, activeName, onSliceClick, onHover }) {
  return (
    <div className="flex items-center gap-3">
      <ResponsiveContainer width={120} height={120}>
        <PieChart>
          <Pie
            data={slices}
            cx="50%"
            cy="50%"
            innerRadius={30}
            outerRadius={50}
            dataKey="value"
            strokeWidth={0}
            activeIndex={emphasisIndex}
            activeShape={renderRaisedSlice}
            onMouseEnter={(_d, i) => onHover(i)}
            onMouseLeave={() => onHover(null)}
            onClick={(_d, i) => { onHover(null); onSliceClick(slices[i]) }}
          >
            {slices.map((s) => (
              <Cell key={s[labelKey]} fill={s.color} cursor="pointer" />
            ))}
          </Pie>
          <Tooltip
            content={({ active, payload }) =>
              active && payload && payload.length ? (
                <div className="bg-[#0f0f1a] border border-[#2a2a4a] rounded px-2 py-0.5 text-[11px] text-space-text inline-block">
                  {payload[0].payload[labelKey]} — {payload[0].payload.value}
                </div>
              ) : null
            }
          />
        </PieChart>
      </ResponsiveContainer>
      <div className="flex flex-col gap-1">
        {slices.map((s, i) => (
          <button
            key={s[labelKey]}
            onClick={() => { onHover(null); onSliceClick(s) }}
            onMouseEnter={() => onHover(i)}
            onMouseLeave={() => onHover(null)}
            className="flex items-center gap-1.5 text-left hover:opacity-80 transition-opacity"
          >
            <span className="w-2 h-2 rounded-full shrink-0" style={{ background: s.color }} />
            <span className={`text-xs ${s[labelKey] === activeName ? 'text-purple-300 font-semibold' : 'text-space-dim'}`}>{s[labelKey]}</span>
            <span className="text-xs font-medium text-space-text ml-auto pl-2">{s.value}</span>
          </button>
        ))}
      </div>
    </div>
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
  const [hoveredSkill, setHoveredSkill] = useState(null)
  const [hoveredIndex, setHoveredIndex] = useState(null)
  const [drillCategory, setDrillCategory] = useState(null)

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

  const isCategories = skillField === 'categories'

  // Unified skills: each row {skill, high, med, low, category}. Pre-sorted by total desc.
  const skills = skillFreq?.skills ?? []
  const skillBars = skills.slice(0, 12).map((row) => ({
    skill: row.skill,
    high: row.high,
    med: row.med,
    low: row.low,
    total: row.high + row.med + row.low,
  }))
  const emphasizedSkill = hoveredSkill ?? activeSkill

  // Category pie + per-skill drill pie.
  const categories = skillFreq?.categories ?? []
  const categorySlices = categories.map((r, i) => ({
    category: r.category,
    value: r.count,
    color: r.category === 'Other' ? OTHER_COLOR : TECH_COLORS[i % TECH_COLORS.length],
  }))
  const drillSlices = drillCategory
    ? skills
        .filter((s) => s.category === drillCategory)
        .slice(0, 10)
        .map((s, i) => ({
          skill: s.skill,
          value: s.high + s.med + s.low,
          color: TECH_COLORS[i % TECH_COLORS.length],
        }))
    : []

  const categoryEmphasisIndex = hoveredIndex ?? undefined
  const drillActiveIndex = drillSlices.findIndex((s) => s.skill === activeSkill)
  const drillEmphasisIndex = hoveredIndex ?? (drillActiveIndex >= 0 ? drillActiveIndex : undefined)

  const hasSkillData = isCategories
    ? (drillCategory ? drillSlices.length > 0 : categorySlices.length > 0)
    : skillBars.length > 0

  const handleSkillClick = (skillName) => {
    if (!skillName || !onSkillFilter || skillName === activeSkill) return
    getJobsForSkill(skillName)
      .then(({ job_keys }) => onSkillFilter({ skill: skillName, jobKeys: job_keys }))
      .catch(() => setSkillError('Could not load jobs for skill'))
  }

  // Bar labels: shown only for the emphasized (hovered or active) skill.
  const renderSegmentLabel = ({ x, y, width, height, value, index }) => {
    const row = skillBars[index]
    if (!row || row.skill !== emphasizedSkill || !value) return null
    return (
      <text x={x + width / 2} y={y + height / 2} fill={ACTIVE_OUTLINE} fontSize={10} textAnchor="middle" dominantBaseline="central">
        {value}
      </text>
    )
  }
  const renderTotalLabel = ({ x, y, width, height, index }) => {
    const row = skillBars[index]
    if (!row || row.skill !== emphasizedSkill) return null
    return (
      <text x={x + width + 6} y={y + height / 2} fill="#c8c8e8" fontSize={10} textAnchor="start" dominantBaseline="central">
        {row.total}
      </text>
    )
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
                  onClick={() => { setSkillField(key); setDrillCategory(null); setHoveredIndex(null) }}
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
              isCategories ? (
                drillCategory ? (
                  <div className="flex flex-col gap-2">
                    <button
                      onClick={() => { setDrillCategory(null); setHoveredIndex(null) }}
                      className="flex items-center gap-1.5 text-xs text-space-dim hover:text-purple-400 transition-colors self-start"
                    >
                      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M10 12L6 8l4-4" />
                      </svg>
                      {drillCategory}
                    </button>
                    <SkillPie
                      slices={drillSlices}
                      labelKey="skill"
                      emphasisIndex={drillEmphasisIndex}
                      activeName={activeSkill}
                      onSliceClick={(s) => handleSkillClick(s.skill)}
                      onHover={setHoveredIndex}
                    />
                  </div>
                ) : (
                  <SkillPie
                    slices={categorySlices}
                    labelKey="category"
                    emphasisIndex={categoryEmphasisIndex}
                    activeName={null}
                    onSliceClick={(s) => { setDrillCategory(s.category); setHoveredIndex(null) }}
                    onHover={setHoveredIndex}
                  />
                )
              ) : (
                <ResponsiveContainer width="100%" height={Math.max(160, skillBars.length * 22)}>
                  <BarChart
                    layout="vertical"
                    data={skillBars}
                    margin={{ top: 4, right: 28, bottom: 0, left: 8 }}
                  >
                    <defs>
                      <filter id="skill-bar-raise" x="-50%" y="-50%" width="200%" height="200%">
                        <feDropShadow dx="0" dy="0" stdDeviation="3" floodColor={ACTIVE_OUTLINE} floodOpacity="0.9" />
                      </filter>
                    </defs>
                    <XAxis type="number" allowDecimals={false} tick={{ fontSize: 10, fill: '#8888aa' }} />
                    <YAxis type="category" dataKey="skill" width={90} tick={{ fontSize: 10, fill: '#8888aa' }} />
                    <Tooltip
                      cursor={false}
                      content={({ active, payload }) =>
                        active && payload && payload.length ? (
                          <div className="bg-[#0f0f1a] border border-[#2a2a4a] rounded px-2 py-0.5 text-[11px] text-space-text inline-block">
                            {payload[0].payload.skill}
                          </div>
                        ) : null
                      }
                    />
                    <Legend wrapperStyle={{ fontSize: 11, color: '#8888aa' }} />
                    <Bar
                      dataKey="high" name="High" stackId="skill" cursor="pointer"
                      onMouseEnter={(_d, i) => setHoveredSkill(skillBars[i].skill)}
                      onMouseLeave={() => setHoveredSkill(null)}
                      onClick={(d) => handleSkillClick(d?.skill ?? d?.payload?.skill)}
                    >
                      {skillBars.map((row) => (
                        <Cell
                          key={row.skill}
                          fill={TIER_COLORS.high}
                          stroke={row.skill === activeSkill ? ACTIVE_OUTLINE : 'none'}
                          strokeWidth={row.skill === activeSkill ? 2 : 0}
                          filter={row.skill === activeSkill ? 'url(#skill-bar-raise)' : undefined}
                        />
                      ))}
                      <LabelList dataKey="high" content={renderSegmentLabel} />
                    </Bar>
                    <Bar
                      dataKey="med" name="Med" stackId="skill" cursor="pointer"
                      onMouseEnter={(_d, i) => setHoveredSkill(skillBars[i].skill)}
                      onMouseLeave={() => setHoveredSkill(null)}
                      onClick={(d) => handleSkillClick(d?.skill ?? d?.payload?.skill)}
                    >
                      {skillBars.map((row) => (
                        <Cell
                          key={row.skill}
                          fill={TIER_COLORS.med}
                          stroke={row.skill === activeSkill ? ACTIVE_OUTLINE : 'none'}
                          strokeWidth={row.skill === activeSkill ? 2 : 0}
                          filter={row.skill === activeSkill ? 'url(#skill-bar-raise)' : undefined}
                        />
                      ))}
                      <LabelList dataKey="med" content={renderSegmentLabel} />
                    </Bar>
                    <Bar
                      dataKey="low" name="Low" stackId="skill" radius={[0, 3, 3, 0]} cursor="pointer"
                      onMouseEnter={(_d, i) => setHoveredSkill(skillBars[i].skill)}
                      onMouseLeave={() => setHoveredSkill(null)}
                      onClick={(d) => handleSkillClick(d?.skill ?? d?.payload?.skill)}
                    >
                      {skillBars.map((row) => (
                        <Cell
                          key={row.skill}
                          fill={TIER_COLORS.low}
                          stroke={row.skill === activeSkill ? ACTIVE_OUTLINE : 'none'}
                          strokeWidth={row.skill === activeSkill ? 2 : 0}
                          filter={row.skill === activeSkill ? 'url(#skill-bar-raise)' : undefined}
                        />
                      ))}
                      <LabelList dataKey="low" content={renderSegmentLabel} />
                      {/* total sits on the low (rightmost) segment so it renders just past the bar end */}
                      <LabelList dataKey="total" content={renderTotalLabel} />
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
