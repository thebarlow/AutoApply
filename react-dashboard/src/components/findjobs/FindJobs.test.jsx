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
  source: 'remotive', job_key: 'r1', candidate_id: 'cid1', title: 'Python Engineer',
  company: 'Acme', url: 'https://x.com/1', description: 'Build things',
  location: '', salary: '', remote: true, posted_at: '', scraped_at: '',
  status: 'none',
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  api.getLastSearch.mockResolvedValue({ query: '' })
  api.searchJobs.mockResolvedValue({ query: 'python', candidates: [CAND] })
  api.scrapeSelected.mockResolvedValue({ results: [{ job_key: 'r1', status: 'staged' }] })
  api.getMe.mockResolvedValue({})
})

async function search() {
  fireEvent.change(screen.getByPlaceholderText(/search/i), { target: { value: 'python' } })
  fireEvent.click(screen.getByRole('button', { name: /^search$/i }))
}

it('auto-runs the remembered search on mount', async () => {
  api.getLastSearch.mockResolvedValue({ query: 'rust', exclude: ['senior'] })
  renderFindJobs()
  await waitFor(() => expect(api.searchJobs).toHaveBeenCalledWith('rust', ['senior']))
})

it('forwards excluded words from the input', async () => {
  renderFindJobs()
  fireEvent.change(screen.getByPlaceholderText(/search remote/i), { target: { value: 'python' } })
  fireEvent.change(screen.getByPlaceholderText(/exclude/i), { target: { value: 'senior, lead' } })
  fireEvent.click(screen.getByRole('button', { name: /^search$/i }))
  await waitFor(() =>
    expect(api.searchJobs).toHaveBeenCalledWith('python', ['senior', 'lead']))
})

it('shows region counts and filters the list by the selected region', async () => {
  const usa = { ...CAND, job_key: 'u', candidate_id: 'cu', title: 'USA Role', location: 'USA Only' }
  const eu = { ...CAND, job_key: 'e', candidate_id: 'ce', title: 'EU Role', location: 'Europe' }
  api.searchJobs.mockResolvedValue({ query: 'x', candidates: [usa, eu] })
  renderFindJobs()
  await search()
  await screen.findAllByText('USA Role')
  const select = screen.getByRole('combobox', { name: /location/i })
  // counts reflect the snapshot
  expect(screen.getByRole('option', { name: /USA \(1\)/ })).toBeInTheDocument()
  expect(screen.getByRole('option', { name: /Europe \(1\)/ })).toBeInTheDocument()
  // selecting USA hides the Europe-only card
  fireEvent.change(select, { target: { value: 'USA' } })
  expect(screen.getAllByText('USA Role').length).toBeGreaterThan(0)
  // EU-only card animates out; wait for it to leave the DOM
  await waitFor(() => expect(screen.queryByText('EU Role')).not.toBeInTheDocument())
})

it('renders candidate cards after searching', async () => {
  renderFindJobs()
  await search()
  // Title appears in both the card and the auto-selected preview.
  expect((await screen.findAllByText('Python Engineer')).length).toBeGreaterThan(0)
})

it('auto-previews the first result after searching', async () => {
  renderFindJobs()
  await search()
  expect(await screen.findByText('Build things')).toBeInTheDocument()
})

it('checkmark scrapes the job and removes it from the list', async () => {
  renderFindJobs()
  await search()
  await screen.findAllByText('Python Engineer')
  fireEvent.click(screen.getAllByRole('button', { name: /scrape job/i })[0])
  await waitFor(() =>
    expect(api.scrapeSelected).toHaveBeenCalledWith([expect.objectContaining({ job_key: 'r1' })]))
  await waitFor(() =>
    expect(screen.queryByText('Python Engineer')).not.toBeInTheDocument())
})

it('x deletes the job and caches its id so a re-search hides it', async () => {
  renderFindJobs()
  await search()
  await screen.findAllByText('Python Engineer')
  fireEvent.click(screen.getAllByRole('button', { name: /delete job/i })[0])
  await waitFor(() =>
    expect(screen.queryByText('Python Engineer')).not.toBeInTheDocument())
  // id persisted to the client cache
  expect(JSON.parse(localStorage.getItem('findjobs:deletedIds'))).toContain('cid1')
  // re-searching still returns it, but it stays hidden
  fireEvent.click(screen.getByRole('button', { name: /^search$/i }))
  await waitFor(() => expect(api.searchJobs).toHaveBeenCalledTimes(2))
  expect(screen.queryByText('Python Engineer')).not.toBeInTheDocument()
})

it('clicking a card body previews that job', async () => {
  const second = { ...CAND, job_key: 'r2', candidate_id: 'cid2', title: 'Rust Engineer', description: 'Ship crates' }
  api.searchJobs.mockResolvedValue({ query: 'python', candidates: [CAND, second] })
  renderFindJobs()
  await search()
  const title = await screen.findByText('Rust Engineer')
  fireEvent.click(title)
  expect(await screen.findByText('Ship crates')).toBeInTheDocument()
})
