import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import ErrorLog from './ErrorLog'
import * as api from '../../api'

describe('ErrorLog', () => {
  it('renders grouped error rows with count', async () => {
    vi.spyOn(api, 'getErrors').mockResolvedValue({
      total: 1,
      errors: [{
        id: 1, level: 'ERROR', logger: 'x', message: 'boom',
        route: '/api/x', profile_id: 2, count: 5,
        created_at: '2026-07-23T00:00:00+00:00', last_seen: '2026-07-23T00:00:00+00:00',
      }],
    })
    render(<ErrorLog />)
    await waitFor(() => expect(screen.getByText('boom')).toBeInTheDocument())
    expect(screen.getByText('/api/x')).toBeInTheDocument()
    expect(screen.getByText(/×\s*5/)).toBeInTheDocument()
  })
})
