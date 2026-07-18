import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, act, waitFor } from '@testing-library/react'
import UserHome from './UserHome'

// UserHome pulls in many API calls + recharts; stub everything it touches so we
// can isolate the profile-name refresh behaviour.
const getProfiles = vi.fn()
vi.mock('../../api', () => ({
  getProfiles: (...a) => getProfiles(...a),
  getStats: () => Promise.resolve({ totals: {} }),
  getSkillFrequency: () => Promise.resolve({ skills: [], categories: [], profile_skills: [] }),
  getJobsForSkill: () => Promise.resolve({ job_keys: [] }),
  getMe: () => Promise.resolve({ is_admin: false }),
  getPurchaseHistory: () => Promise.resolve([]),
  getCredits: () => Promise.resolve({ balance: 0 }),
}))

// Force the "Welcome back {name}" branch (not first-run) so the name is rendered.
vi.mock('../../hooks/usePrerequisites', () => ({
  usePrerequisites: () => ({ isFirstRun: false, refresh: vi.fn() }),
}))

describe('UserHome name refresh', () => {
  beforeEach(() => { getProfiles.mockReset() })

  it('refetches the profile name on auto-apply:profile-updated', async () => {
    // First fetch: profile has no parsed name yet → falls back to 'there'.
    getProfiles.mockResolvedValueOnce({ profiles: [{ id: 1, name: '' }], active_id: 1 })
    // After parse: the profile now carries the parsed name.
    getProfiles.mockResolvedValueOnce({
      profiles: [{ id: 1, name: '', first_name: 'Ada', last_name: 'Lovelace' }],
      active_id: 1,
    })

    render(<UserHome onSelect={() => {}} onCreateProfile={() => {}} />)

    await screen.findByText('there')

    act(() => { window.dispatchEvent(new CustomEvent('auto-apply:profile-updated')) })

    await waitFor(() => expect(screen.getByText('Ada Lovelace')).toBeInTheDocument())
    expect(getProfiles).toHaveBeenCalledTimes(2)
  })
})
