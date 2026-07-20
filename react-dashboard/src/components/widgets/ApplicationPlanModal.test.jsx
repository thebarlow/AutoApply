import { render, screen, waitFor } from '@testing-library/react'
import { vi, describe, it, expect } from 'vitest'
import ApplicationPlanModal from './ApplicationPlanModal'
import * as api from '../../api'

describe('ApplicationPlanModal', () => {
  it('renders planned fields with status', async () => {
    vi.spyOn(api, 'getApplicationPlan').mockResolvedValue({
      plan: {
        job_key: 'j1',
        ats_type: 'greenhouse',
        fields: [
          { field_id: 'email', label: 'Email', value: 'a@b.c', status: 'filled', source: 'static_schema' },
          { field_id: 'q_why', label: 'Why us?', value: 'Because', status: 'drafted', source: 'essay' },
        ],
      },
      application_answers_complete: false,
    })
    render(<ApplicationPlanModal jobKey="j1" open onClose={() => {}} />)
    await waitFor(() => expect(screen.getByText('Email')).toBeInTheDocument())
    expect(screen.getByText('a@b.c')).toBeInTheDocument()
    expect(screen.getByText(/drafted/i)).toBeInTheDocument()
  })

  it('shows empty-state when no plan computed yet', async () => {
    vi.spyOn(api, 'getApplicationPlan').mockResolvedValue({ plan: null, application_answers_complete: true })
    render(<ApplicationPlanModal jobKey="j2" open onClose={() => {}} />)
    await waitFor(() => expect(screen.getByText(/no application plan/i)).toBeInTheDocument())
  })
})
