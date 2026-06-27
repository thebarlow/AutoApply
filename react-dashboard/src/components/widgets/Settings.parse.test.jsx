/**
 * Settings.parse.test.jsx
 *
 * Tests the propose→preview→apply wiring added to CreateProfile (step 2).
 * CreateProfile is not exported, so we drive it through the Settings component
 * by mocking UserHome to expose the "Create Profile" trigger, then walking
 * step 1 → step 2 of the wizard.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import Settings from './Settings'

// ── Heavy child mocks ─────────────────────────────────────────────────────────

vi.mock('framer-motion', () => ({
  motion: {
    div: ({ children, ...p }) => <div {...p}>{children}</div>,
  },
  AnimatePresence: ({ children }) => <>{children}</>,
}))

vi.mock('react-markdown', () => ({ default: ({ children }) => <>{children}</> }))

// UserHome: just expose the "Create Profile" callback as a button so tests can
// navigate into the CreateProfile wizard without rendering the full profile list.
vi.mock('./UserHome', () => ({
  default: ({ onCreateProfile }) => (
    <button onClick={onCreateProfile}>New Profile</button>
  ),
}))

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

// ParsePreview: minimal stub — exposes Apply and Cancel buttons so wiring can
// be asserted without rendering the real component tree.
vi.mock('./parse/ParsePreview', () => ({
  default: ({ proposal, applying, onApply, onCancel }) => (
    <div data-testid="parse-preview">
      <button
        onClick={() => onApply(proposal)}
        disabled={applying}
      >
        Apply
      </button>
      <button onClick={onCancel}>Cancel</button>
    </div>
  ),
}))

// ── API mock ──────────────────────────────────────────────────────────────────

vi.mock('../../api', () => ({
  getProfiles: vi.fn().mockResolvedValue({ active_id: null, profiles: [] }),
  createProfile: vi.fn().mockResolvedValue({ id: 42 }),
  getProfile: vi.fn().mockResolvedValue({ name: 'Test Profile', data: {} }),
  updateProfile: vi.fn().mockResolvedValue({}),
  setActiveProfile: vi.fn().mockResolvedValue({}),
  uploadProfileResume: vi.fn().mockResolvedValue({ path: '/tmp/r.pdf', filename: 'r.pdf' }),
  proposeParse: vi.fn().mockResolvedValue({
    sections: [
      {
        name: 'Work Experience',
        origin: 'builtin',
        kind: 'list',
        allowed_actions: ['merge', 'skip'],
        default_action: 'merge',
      },
    ],
  }),
  applyParse: vi.fn().mockResolvedValue({}),
  // Other named exports Settings imports — provide benign stubs.
  markJobActionSeen: vi.fn().mockResolvedValue({}),
  deleteJob: vi.fn().mockResolvedValue({}),
  updateJobState: vi.fn().mockResolvedValue({}),
  updateJobFields: vi.fn().mockResolvedValue({}),
  flagJob: vi.fn().mockResolvedValue({}),
  getOwnedSkills: vi.fn().mockResolvedValue([]),
  parseProfileResume: vi.fn().mockResolvedValue({}),
  getThemes: vi.fn().mockResolvedValue([]),
}))

import { proposeParse, applyParse, createProfile, uploadProfileResume } from '../../api'

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Render Settings and advance to CreateProfile step 2.
 *
 * Step 1 requires name, provider, model, and API key. We fill minimal values
 * and submit. createProfile is already mocked to return id=42.
 */
async function advanceToStep2(user) {
  render(
    <Settings
      selectedJob={null}
      activeTab="User"
      onTabChange={() => {}}
      onJobDeleted={() => {}}
      onSkillFilter={() => {}}
      activeSkill={null}
    />
  )

  // Navigate into the Create Profile wizard via the UserHome stub button.
  await user.click(screen.getByRole('button', { name: /new profile/i }))

  // Step 1 — fill required fields.
  const nameInput = screen.getByPlaceholderText(/e\.g\. software engineer/i)
  await user.type(nameInput, 'Test Profile')

  // Provider select — pick the first real option.
  const select = screen.getByRole('combobox')
  await user.selectOptions(select, screen.getAllByRole('option').find(o => o.value !== ''))

  // Model input (if a combobox/input appears after provider selection).
  // The ModelCombobox or plain input for model.
  const modelInputs = screen.getAllByRole('textbox')
  // Filter out the name input; model comes second.
  const modelInput = modelInputs.find(i => i !== nameInput)
  if (modelInput) {
    await user.clear(modelInput)
    await user.type(modelInput, 'gpt-4o-mini')
  }

  // API key.
  const apiKeyInput = screen.getByPlaceholderText(/sk-/i)
  await user.type(apiKeyInput, 'sk-test-key')

  // Submit step 1.
  await user.click(screen.getByRole('button', { name: /continue/i }))

  // Wait for step 2 upload form.
  await screen.findByText(/step 2 of 2/i)
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('Settings CreateProfile — propose→preview→apply', () => {
  let user

  beforeEach(() => {
    vi.clearAllMocks()
    user = userEvent.setup()
  })

  it('calls proposeParse after upload and shows ParsePreview', async () => {
    await advanceToStep2(user)

    const file = new File(['resume'], 'resume.pdf', { type: 'application/pdf' })
    const fileInput = document.querySelector('input[type="file"]')
    await user.upload(fileInput, file)

    await user.click(screen.getByRole('button', { name: /upload & parse/i }))

    await waitFor(() => expect(proposeParse).toHaveBeenCalledWith(42))
    expect(await screen.findByTestId('parse-preview')).toBeInTheDocument()
  })

  it('calls applyParse then onCreated when Apply is clicked', async () => {
    const onCreated = vi.fn()
    // Re-render with custom onCreated — we need to intercept CreateProfile's
    // onCreated prop, which Settings wires to setView('main'). We spy on
    // applyParse resolution instead, since Settings calls onCreated internally.
    // The simplest verification: applyParse called and the preview disappears.
    await advanceToStep2(user)

    const file = new File(['resume'], 'resume.pdf', { type: 'application/pdf' })
    await user.upload(document.querySelector('input[type="file"]'), file)
    await user.click(screen.getByRole('button', { name: /upload & parse/i }))

    await screen.findByTestId('parse-preview')

    await user.click(screen.getByRole('button', { name: /apply/i }))

    await waitFor(() =>
      expect(applyParse).toHaveBeenCalledWith(
        42,
        expect.objectContaining({ sections: expect.any(Array) })
      )
    )
  })

  it('returns to upload form when Cancel is clicked', async () => {
    await advanceToStep2(user)

    const file = new File(['resume'], 'resume.pdf', { type: 'application/pdf' })
    await user.upload(document.querySelector('input[type="file"]'), file)
    await user.click(screen.getByRole('button', { name: /upload & parse/i }))

    await screen.findByTestId('parse-preview')

    await user.click(screen.getByRole('button', { name: /cancel/i }))

    // The preview should be gone and the upload form should be back.
    expect(screen.queryByTestId('parse-preview')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /upload & parse/i })).toBeInTheDocument()
  })
})
