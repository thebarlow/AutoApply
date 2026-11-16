import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

const api = vi.hoisted(() => ({
  getLlmKey: vi.fn(),
  getLlmKeyModels: vi.fn(),
  testLlmKey: vi.fn(),
  saveLlmKey: vi.fn(),
  setLlmDefaultModel: vi.fn(),
  deleteLlmKey: vi.fn(),
}))
vi.mock('../../api', () => api)

import ApiKeySettings from './ApiKeySettings'

const PROVIDERS = [{ id: 'openrouter', label: 'OpenRouter' }, { id: 'openai', label: 'OpenAI' }]
const EMPTY = { has_key: false, storage_available: true, providers: PROVIDERS }
const SAVED = {
  has_key: true, storage_available: true, providers: PROVIDERS,
  provider: 'openai', provider_label: 'OpenAI', masked_key: '••••9876', default_model: 'gpt-4o-mini',
}

beforeEach(() => vi.clearAllMocks())

describe('ApiKeySettings', () => {
  it('checks the key, then saves it with the chosen model', async () => {
    api.getLlmKey.mockResolvedValue(EMPTY)
    api.testLlmKey.mockResolvedValue({ ok: true, models: [{ id: 'gpt-4o-mini', name: 'gpt-4o-mini' }] })
    api.saveLlmKey.mockResolvedValue(SAVED)
    api.getLlmKeyModels.mockResolvedValue({ models: [] })

    render(<ApiKeySettings />)
    fireEvent.change(await screen.findByLabelText('Provider'), { target: { value: 'openai' } })
    fireEvent.change(screen.getByPlaceholderText('Paste your API key'), { target: { value: 'sk-live-9876' } })
    fireEvent.click(screen.getByText('Check key'))
    fireEvent.click(await screen.findByText('Save key'))

    await waitFor(() => expect(api.saveLlmKey).toHaveBeenCalledWith('openai', 'sk-live-9876', 'gpt-4o-mini'))
    expect(await screen.findByText('••••9876')).toBeInTheDocument()
    expect(screen.queryByDisplayValue('sk-live-9876')).toBeNull()
  })

  it('shows the provider error when the key is rejected', async () => {
    api.getLlmKey.mockResolvedValue(EMPTY)
    api.testLlmKey.mockResolvedValue({ ok: false, error: 'OpenRouter rejected this key.' })

    render(<ApiKeySettings />)
    fireEvent.change(await screen.findByPlaceholderText('Paste your API key'), { target: { value: 'sk-bad-key-0000' } })
    fireEvent.click(screen.getByText('Check key'))

    expect(await screen.findByRole('alert')).toHaveTextContent('OpenRouter rejected this key.')
    expect(api.saveLlmKey).not.toHaveBeenCalled()
  })

  it('removes a saved key', async () => {
    api.getLlmKey.mockResolvedValue(SAVED)
    api.getLlmKeyModels.mockResolvedValue({ models: [{ id: 'gpt-4o-mini', name: 'gpt-4o-mini' }] })
    api.deleteLlmKey.mockResolvedValue(EMPTY)

    render(<ApiKeySettings />)
    fireEvent.click(await screen.findByText('Remove key'))

    await waitFor(() => expect(api.deleteLlmKey).toHaveBeenCalled())
    expect(await screen.findByText('Check key')).toBeInTheDocument()
  })
})
