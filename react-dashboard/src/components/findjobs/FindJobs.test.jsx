import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import FindJobs from '../FindJobs'
import * as api from '../../api'

vi.mock('../../api')

function renderFindJobs() {
  return render(
    <MemoryRouter>
      <FindJobs />
    </MemoryRouter>
  )
}

const CAND = {
  source: 'remotive', job_key: 'r1', title: 'Python Engineer',
  company: 'Acme', url: 'https://x.com/1', description: 'Build things',
  location: '', salary: '', remote: true, posted_at: '', scraped_at: '',
  status: 'none',
}

beforeEach(() => {
  vi.clearAllMocks()
  api.getLastSearch.mockResolvedValue({ query: '' })
  api.searchJobs.mockResolvedValue({ query: 'python', candidates: [CAND] })
  api.scrapeSelected.mockResolvedValue({ results: [{ job_key: 'r1', status: 'staged' }] })
  api.getMe.mockResolvedValue({})
})

it('auto-runs the remembered search on mount', async () => {
  api.getLastSearch.mockResolvedValue({ query: 'rust' })
  renderFindJobs()
  await waitFor(() => expect(api.searchJobs).toHaveBeenCalledWith('rust'))
})

it('renders candidate cards after searching', async () => {
  renderFindJobs()
  fireEvent.change(screen.getByPlaceholderText(/search/i), { target: { value: 'python' } })
  fireEvent.click(screen.getByRole('button', { name: /^search$/i }))
  expect(await screen.findByText('Python Engineer')).toBeInTheDocument()
})

it('selecting a card and scraping calls scrapeSelected', async () => {
  renderFindJobs()
  fireEvent.change(screen.getByPlaceholderText(/search/i), { target: { value: 'python' } })
  fireEvent.click(screen.getByRole('button', { name: /^search$/i }))
  await screen.findByText('Python Engineer')
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.click(screen.getByRole('button', { name: /scrape \(1\)/i }))
  await waitFor(() =>
    expect(api.scrapeSelected).toHaveBeenCalledWith([expect.objectContaining({ job_key: 'r1' })]))
})

it('does not mark a card scraped when the server reports duplicate', async () => {
  api.scrapeSelected.mockResolvedValue({ results: [{ job_key: 'r1', status: 'duplicate' }] })
  renderFindJobs()
  fireEvent.change(screen.getByPlaceholderText(/search/i), { target: { value: 'python' } })
  fireEvent.click(screen.getByRole('button', { name: /^search$/i }))
  await screen.findByText('Python Engineer')
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.click(screen.getByRole('button', { name: /scrape \(1\)/i }))
  await waitFor(() => expect(api.scrapeSelected).toHaveBeenCalled())
  // selection cleared -> Scrape button reverts to (0)
  await waitFor(() =>
    expect(screen.getByRole('button', { name: /scrape \(0\)/i })).toBeInTheDocument())
  expect(screen.getByRole('checkbox')).not.toBeChecked()
})

it('clicking the card body marks it viewed', async () => {
  renderFindJobs()
  fireEvent.change(screen.getByPlaceholderText(/search/i), { target: { value: 'python' } })
  fireEvent.click(screen.getByRole('button', { name: /^search$/i }))
  const title = await screen.findByText('Python Engineer')
  fireEvent.click(title)
  // detail preview shows the description
  expect(await screen.findByText('Build things')).toBeInTheDocument()
})
