import { useState, useEffect } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer,
  PieChart, Pie, Cell, Sector, LabelList,
} from 'recharts'
import { getProfiles, getStats, getSkillFrequency, getJobsForSkill, getMe, getPurchaseHistory } from '../../api'
import SkillChipModal from './SkillChipModal'
import CreditBalance from './CreditBalance'
import BuyCreditsModal from './BuyCreditsModal'
import { usePrerequisites } from '../../hooks/usePrerequisites'

const WINDOWS = [
  { key: 'today', label: 'Today' },
  { key: 'week', label: 'Week' },
  { key: 'all_time', label: 'All Time' },
]

// Rotating stat counter: clicking the highlighted phrase advances to the next.
// `verb` is the highlighted, clickable text; the count is woven into it.
const STAT_METRICS = [
  { key: 'applied', verb: (n) => `applied to ${n}` },
  { key: 'scraped', verb: (n) => `scraped ${n}` },
  { key: 'resumes', verb: (n) => `made resumes for ${n}` },
]

const SKILL_FIELDS = [
  { key: 'categories', label: 'Categories' },
  { key: 'skills', label: 'By Skill' },
]

const TIER_COLORS = { high: '#7c3aed', med: '#3b82f6', low: '#06b6d4' }
const TECH_COLORS = ['#7c3aed', '#3b82f6', '#06b6d4', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899']
const OTHER_COLOR = '#555'
const CATEGORY_COLORS = {
  Languages: '#7c3aed',
  Frontend: '#3b82f6',
  Backend: '#06b6d4',
  Cloud: '#10b981',
  DevOps: '#f59e0b',
  Databases: '#ef4444',
  'Data/ML': '#8b5cf6',
  Mobile: '#ec4899',
  Other: OTHER_COLOR,
}
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
// Small inline status icon: green check (profile covers the skill) or red x (it doesn't).
function SkillBadge({ status }) {
  if (status === 'have') {
    return (
      <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="#10b981" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="shrink-0" aria-label="In your profile">
        <path d="M3 8.5l3.5 3.5L13 4" />
      </svg>
    )
  }
  return (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="#ef4444" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="shrink-0" aria-label="Not in your profile">
      <path d="M4 4l8 8M12 4l-8 8" />
    </svg>
  )
}

function SkillPie({ slices, labelKey, emphasisIndex, activeName, onSliceClick, onHover, badgeFor, onLabelClick }) {
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
          <div
            key={s[labelKey]}
            onMouseEnter={() => onHover(i)}
            onMouseLeave={() => onHover(null)}
            className="flex items-center gap-1.5"
          >
            <span className="w-2 h-2 rounded-full shrink-0" style={{ background: s.color }} />
            {badgeFor && <SkillBadge status={badgeFor(s)} />}
            {onLabelClick ? (
              <button
                type="button"
                onClick={() => onLabelClick(s[labelKey])}
                className={`text-xs hover:underline ${s[labelKey] === activeName ? 'text-purple-300 font-semibold' : 'text-space-dim'}`}
              >
                {s[labelKey]}
              </button>
            ) : (
              <button
                type="button"
                onClick={() => { onHover(null); onSliceClick(s) }}
                className={`text-xs hover:opacity-80 transition-opacity ${s[labelKey] === activeName ? 'text-purple-300 font-semibold' : 'text-space-dim'}`}
              >
                {s[labelKey]}
              </button>
            )}
            {onLabelClick && (
              <button
                type="button"
                title="Filter jobs by this skill"
                onClick={() => { onHover(null); onSliceClick(s) }}
                className="text-space-dim hover:text-purple-400 transition-colors shrink-0"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" />
                </svg>
              </button>
            )}
            <span className="text-xs font-medium text-space-text ml-auto pl-2">{s.value}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function UserHome({ onSelect, onCreateProfile, onSkillFilter, activeSkill }) {
  const { isFirstRun } = usePrerequisites()
  const [activeProfile, setActiveProfile] = useState(null)
  const [profilesLoaded, setProfilesLoaded] = useState(false)
  const [win, setWin] = useState('all_time')
  const [metricIdx, setMetricIdx] = useState(0)
  const [stats, setStats] = useState(null)
  const [statsLoading, setStatsLoading] = useState(false)
  const [statsError, setStatsError] = useState(null)
  const [skillFreq, setSkillFreq] = useState(null)
  const [skillField, setSkillField] = useState('categories')
  const [skillError, setSkillError] = useState(null)
  const [hoveredSkill, setHoveredSkill] = useState(null)
  const [hoveredIndex, setHoveredIndex] = useState(null)
  const [drillCategory, setDrillCategory] = useState(null)
  const [modalSkill, setModalSkill] = useState(null)
  const [history, setHistory] = useState([])
  const [buyOpen, setBuyOpen] = useState(false)
  const [isAdmin, setIsAdmin] = useState(false)

  useEffect(() => { getMe().then((me) => setIsAdmin(!!me?.is_admin)).catch(() => {}) }, [])

  useEffect(() => { getPurchaseHistory().then(setHistory).catch(() => {}) }, [])

  // Refresh purchase history after a successful checkout (navbar dispatches this).
  useEffect(() => {
    const onPurchase = () => getPurchaseHistory().then(setHistory).catch(() => {})
    window.addEventListener('auto-apply:purchase-success', onPurchase)
    return () => window.removeEventListener('auto-apply:purchase-success', onPurchase)
  }, [])

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
    return (
      <div className="flex flex-col items-center gap-3 py-6">
        <p className="text-sm text-space-dim text-center">
          A profile is required to use the app.
        </p>
        <button
          onClick={onCreateProfile}
          className="shiny-border border border-transparent bg-[#0a0a14] text-purple-300 hover:text-white rounded-lg px-4 py-2 text-sm transition-colors"
        >
          + Create your profile
        </button>
      </div>
    )
  }

  const fullName = [activeProfile.first_name, activeProfile.last_name].filter(Boolean).join(' ')
  const displayName = fullName || activeProfile.name || 'there'

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

  // Skills the active profile already covers (canonical names from the API).
  const profileSkills = new Set(skillFreq?.profile_skills ?? [])
  const skillStatus = (s) => (profileSkills.has(s.skill) ? 'have' : 'missing')

  // Category pie + per-skill drill pie.
  const categories = skillFreq?.categories ?? []
  const categorySlices = categories.map((r) => ({
    category: r.category,
    value: r.count,
    color: CATEGORY_COLORS[r.category] ?? OTHER_COLOR,
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
  const renderSkillTick = ({ x, y, payload }) => (
    <text
      x={x} y={y} dy={3} textAnchor="end"
      fontSize={10} fill="#8888aa"
      style={{ cursor: 'pointer' }}
      onClick={() => setModalSkill(payload.value)}
    >
      {payload.value}
    </text>
  )
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
      <div className="flex flex-col items-center gap-2">
        {isFirstRun ? (
          <>
            <span className="text-xs text-space-dim uppercase tracking-widest">Ready to set up</span>
            <button
              onClick={() => window.dispatchEvent(new CustomEvent('auto-apply:open-wizard'))}
              title="Set up your profile"
              className="max-w-full truncate px-4 py-1.5 rounded-lg border border-space-border text-lg font-semibold text-purple-300 hover:text-purple-200 hover:border-purple-500 transition-colors"
            >
              your profile
            </button>
          </>
        ) : (
          <>
            <span className="text-xs text-space-dim uppercase tracking-widest">Welcome back</span>
            <button
              onClick={() => onSelect(activeProfile.id)}
              title="Edit your profile"
              className="max-w-full truncate px-4 py-1.5 rounded-lg border border-space-border text-lg font-semibold text-purple-300 hover:text-purple-200 hover:border-purple-500 transition-colors"
            >
              {displayName}
            </button>
          </>
        )}
        <CreditBalance
          variant="settings"
          isAdmin={isAdmin}
          onClick={() => setBuyOpen(true)}
        />
      </div>

      <div className="flex flex-col gap-2">
        {history.length > 0 && (
          <div className="mt-3">
            <p className="text-xs uppercase tracking-widest text-space-dim mb-1">Purchases</p>
            <ul className="flex flex-col gap-1">
              {history.map((h) => (
                <li key={h.stripe_session_id} className="flex justify-between text-xs text-space-text">
                  <span>{new Date(h.created_at).toLocaleDateString()}</span>
                  <span>{h.credits.toLocaleString()} cr</span>
                  <span className="text-space-dim">${h.amount_usd.toFixed(2)} · {h.status}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
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
            {statsLoading && !stats && <p className="text-xs text-space-dim">Loading…</p>}
            {stats && (() => {
              const metric = STAT_METRICS[metricIdx]
              const count = stats.totals?.[metric.key] ?? 0
              return (
                <p className="text-sm text-space-dim">
                  You've{' '}
                  <button
                    type="button"
                    onClick={() => setMetricIdx((i) => (i + 1) % STAT_METRICS.length)}
                    title="Click to see another stat"
                    className="font-semibold text-purple-300 hover:text-purple-200 transition-colors"
                  >
                    {metric.verb(count)}
                  </button>{' '}
                  jobs
                </p>
              )
            })()}
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
                      badgeFor={skillStatus}
                      onLabelClick={(skillName) => setModalSkill(skillName)}
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
                    <YAxis type="category" dataKey="skill" width={90} tick={renderSkillTick} />
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
                    <Legend
                      wrapperStyle={{ fontSize: 11, color: '#8888aa' }}
                      payload={[
                        { value: 'High', type: 'square', id: 'high', color: TIER_COLORS.high },
                        { value: 'Med', type: 'square', id: 'med', color: TIER_COLORS.med },
                        { value: 'Low', type: 'square', id: 'low', color: TIER_COLORS.low },
                      ]}
                    />
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
      {modalSkill && (
        <SkillChipModal
          skill={modalSkill}
          isOwned={profileSkills.has(modalSkill)}
          onClose={() => setModalSkill(null)}
          onChanged={() => { getSkillFrequency().then(setSkillFreq).catch(() => {}) }}
        />
      )}
      {buyOpen && <BuyCreditsModal onClose={() => setBuyOpen(false)} />}
    </div>
  )
}
