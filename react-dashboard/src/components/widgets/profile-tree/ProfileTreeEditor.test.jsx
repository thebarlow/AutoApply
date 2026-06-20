import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import ProfileTreeEditor from './ProfileTreeEditor'
import * as api from '../../../api'

vi.mock('../../../api')

function serverTree() {
  return {
    type: 'root', id: 'r', children: [{
      type: 'section', id: 'sec-skills', name: 'Skills', role: 'skills',
      order: 0, visible: true, children: [{
        type: 'field', id: 'f-skills', name: 'Technical Skills', key: 'skills', order: 0,
        visible: true, kind: 'taglist', value: ['Python'],
        llm_output: false, llm_instructions: '', llm_input: false,
        regen_lock: false, min: null, max: null }],
    }],
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  api.getProfileTree.mockResolvedValue({ tree: serverTree() })
  api.putProfileTree.mockImplementation(async (_id, tree) => ({ tree }))
})

describe('ProfileTreeEditor', () => {
  it('loads and renders sections', async () => {
    render(<ProfileTreeEditor profileId={1} />)
    expect(await screen.findByText('Skills')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Expand section')) // collapsed by default
    expect(screen.getByText('Python')).toBeInTheDocument()
  })

  it('an edit sets dirty; Save PUTs the tree and clears dirty', async () => {
    render(<ProfileTreeEditor profileId={1} />)
    await screen.findByText('Skills')
    expect(screen.getByText('Save').closest('button')).toBeDisabled()
    fireEvent.click(screen.getByLabelText('Expand section'))
    fireEvent.click(screen.getByLabelText('Remove Python'))
    expect(screen.getByText('Save').closest('button')).not.toBeDisabled()
    fireEvent.click(screen.getByText('Save'))
    await waitFor(() => expect(api.putProfileTree).toHaveBeenCalledTimes(1))
    const [, sentTree] = api.putProfileTree.mock.calls[0]
    const skills = sentTree.children[0].children[0]
    expect(skills.value).toEqual([])
    await waitFor(() => expect(screen.getByText('Save').closest('button')).toBeDisabled())
  })

  it('Discard reverts edits', async () => {
    render(<ProfileTreeEditor profileId={1} />)
    await screen.findByText('Skills')
    fireEvent.click(screen.getByLabelText('Expand section'))
    fireEvent.click(screen.getByLabelText('Remove Python'))
    fireEvent.click(screen.getByText('Discard'))
    expect(screen.getByText('Python')).toBeInTheDocument()
    expect(screen.getByText('Save').closest('button')).toBeDisabled()
  })

  it('surfaces a 422 message and keeps edits', async () => {
    api.putProfileTree.mockRejectedValueOnce(new Error('PUT /api/config/profiles/1/tree → 422'))
    render(<ProfileTreeEditor profileId={1} />)
    await screen.findByText('Skills')
    fireEvent.click(screen.getByLabelText('Expand section'))
    fireEvent.click(screen.getByLabelText('Remove Python'))
    fireEvent.click(screen.getByText('Save'))
    expect(await screen.findByText(/could not be saved/i)).toBeInTheDocument()
    // still dirty (edit preserved)
    expect(screen.getByText('Save').closest('button')).not.toBeDisabled()
  })

  it('adds a blank custom section from the gallery', async () => {
    render(<ProfileTreeEditor profileId={1} />)
    await screen.findByText('Skills')
    fireEvent.click(screen.getByText('+ Add section'))
    fireEvent.click(screen.getByText('Blank section'))
    expect(await screen.findByText('Blank section')).toBeInTheDocument()
  })

  it('adds a recommended template section from the gallery', async () => {
    render(<ProfileTreeEditor profileId={1} />)
    await screen.findByText('Skills')
    fireEvent.click(screen.getByText('+ Add section'))
    fireEvent.click(screen.getByText('Certifications'))
    expect(await screen.findByText('Certifications')).toBeInTheDocument()
  })
})
