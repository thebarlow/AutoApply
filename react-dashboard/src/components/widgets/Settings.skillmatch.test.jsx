/**
 * Settings.skillmatch.test.jsx
 *
 * Tests that ExtractionView passes job_key to getOwnedSkills,
 * renders the ↻ re-check button, and clicking it calls rematchSkills.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi, describe, it, expect, beforeEach } from 'vitest'

// ── API mock ──────────────────────────────────────────────────────────────────

vi.mock('../../api', () => ({
  getOwnedSkills: vi.fn().mockResolvedValue({ owned: ['Python'] }),
  rematchSkills: vi.fn().mockResolvedValue({}),
  // Stubs for other named exports Settings imports
  getProfiles: vi.fn().mockResolvedValue({ active_id: null, profiles: [] }),
  createProfile: vi.fn().mockResolvedValue({ id: 1 }),
  getProfile: vi.fn().mockResolvedValue({ name: 'P', data: {} }),
  updateProfile: vi.fn().mockResolvedValue({}),
  uploadProfileResume: vi.fn().mockResolvedValue({}),
  proposeParse: vi.fn().mockResolvedValue({ sections: [] }),
  applyParse: vi.fn().mockResolvedValue({}),
  markJobActionSeen: vi.fn().mockResolvedValue({}),
  deleteJob: vi.fn().mockResolvedValue({}),
  updateJobState: vi.fn().mockResolvedValue({}),
  updateJobFields: vi.fn().mockResolvedValue({}),
  flagJob: vi.fn().mockResolvedValue({}),
  getThemes: vi.fn().mockResolvedValue([]),
}))

import { getOwnedSkills, rematchSkills } from '../../api'

// ── Heavy child mocks ─────────────────────────────────────────────────────────

vi.mock('framer-motion', () => ({
  motion: { div: ({ children, ...p }) => <div {...p}>{children}</div> },
  AnimatePresence: ({ children }) => <>{children}</>,
}))
vi.mock('react-markdown', () => ({ default: ({ children }) => <>{children}</> }))
vi.mock('./UserHome', () => ({ default: () => null }))
vi.mock('./DocumentModal', () => ({ default: () => null }))
vi.mock('./SkillChipModal', () => ({ default: () => null }))
vi.mock('./ProfileDetail', () => ({ default: () => null }))
vi.mock('./ProfileEditorModal', () => ({ default: () => null }))
vi.mock('../shared/JobCard', () => ({ WarningIcon: () => null }))
vi.mock('../shared/GatedButton', () => ({
  default: ({ children, onClick, disabled }) => (
    <button onClick={onClick} disabled={disabled}>{children}</button>
  ),
}))
vi.mock('../shared/HelpIcon', () => ({ default: () => null }))
vi.mock('./parse/ParsePreview', () => ({ default: () => null }))

import Settings from './Settings'

// ── Fixture ───────────────────────────────────────────────────────────────────

const JOB = {
  job_key: 'j1',
  title: 'Engineer',
  company: 'Acme',
  state: 'new',
  final_score: null,
  flagged: false,
  extraction_json_exists: true,
  extraction: {
    required_skills: ['Python', 'Bachelors degree'],
    preferred_skills: [],
    tech_stack: [],
    seniority: null,
    role_type: null,
    domain: null,
    work_arrangement: null,
    employment_type: null,
    key_responsibilities: [],
    company_signals: [],
    skill_match_stale: true,
  },
}

function renderWithJob() {
  render(
    <Settings
      selectedJob={JOB}
      activeTab="Preview"
      onTabChange={() => {}}
      onJobDeleted={() => {}}
      onSkillFilter={() => {}}
      activeSkill={null}
    />
  )
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('ExtractionView — job_key + rematch button', () => {
  let user

  beforeEach(() => {
    vi.clearAllMocks()
    getOwnedSkills.mockResolvedValue({ owned: ['Python'] })
    rematchSkills.mockResolvedValue({})
    user = userEvent.setup()
  })

  it('passes job_key to getOwnedSkills', async () => {
    renderWithJob()
    await waitFor(() =>
      expect(getOwnedSkills).toHaveBeenCalledWith(
        expect.arrayContaining(['Python']),
        'j1'
      )
    )
  })

  it('renders the Python chip with owned (✓) styling', async () => {
    renderWithJob()
    // Wait for the owned fetch to resolve and the chip to re-render
    const chip = await screen.findByRole('button', { name: /✓.*Python/i })
    expect(chip).toBeInTheDocument()
    expect(chip.className).toMatch(/emerald/)
  })

  it('renders the ↻ re-check button beside Required Skills', async () => {
    renderWithJob()
    // Wait for extraction to appear
    await screen.findByText('Required Skills')
    const btn = screen.getByTitle('Re-check matches against your current profile')
    expect(btn).toBeInTheDocument()
    expect(btn.textContent).toBe('↻')
  })

  it('clicking ↻ calls rematchSkills with the job_key', async () => {
    renderWithJob()
    await screen.findByText('Required Skills')
    const btn = screen.getByTitle('Re-check matches against your current profile')
    await user.click(btn)
    expect(rematchSkills).toHaveBeenCalledWith('j1')
  })
})
