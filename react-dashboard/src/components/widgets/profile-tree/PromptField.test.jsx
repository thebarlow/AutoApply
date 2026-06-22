import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import {
  buildChipGroups, buildLabelMap, splitSegments, serializeNode, renderHtml,
  ChipTray, PromptField, buildFoldedPreview, entryLabel,
} from './PromptField'

const tree = {
  type: 'root', id: 'r', children: [{
    type: 'section', id: 'sec1', name: 'My Skills', role: null, order: 0, visible: true,
    children: [{ type: 'group', id: 'g', name: 'G', order: 0, visible: true, children: [
      { type: 'field', id: 'fld1', name: 'Tech', key: 'tech', order: 0, visible: true,
        kind: 'taglist', value: ['Python'] }] }],
  }],
}

describe('buildChipGroups', () => {
  it('uses node-id tokens with human-readable display labels', () => {
    const groups = buildChipGroups(tree)
    const job = groups.find((g) => g.label === 'Job')
    expect(job.chips.some((c) => c.token === '{job.description}' && c.display === 'Job: description')).toBe(true)
    const sec = groups.find((g) => g.label === 'My Skills')
    expect(sec.chips.some((c) => c.token === '{profile:sec1}')).toBe(true)
    const fieldChip = sec.chips.find((c) => c.token === '{profile:fld1}')
    expect(fieldChip.display).toBe('My Skills › Tech')
  })
})

describe('splitSegments / serializeNode / renderHtml', () => {
  it('splits text and tokens in order', () => {
    expect(splitSegments('a {profile:fld1} b {job.title}')).toEqual([
      { type: 'text', value: 'a ' },
      { type: 'token', value: '{profile:fld1}' },
      { type: 'text', value: ' b ' },
      { type: 'token', value: '{job.title}' },
    ])
  })

  it('renderHtml emits a pill span with the display label and data-token', () => {
    const html = renderHtml('{profile:fld1}', buildLabelMap(tree))
    expect(html).toContain('data-token="{profile:fld1}"')
    expect(html).toContain('My Skills › Tech')
  })

  it('serializeNode turns pill spans back into their tokens', () => {
    const div = document.createElement('div')
    div.innerHTML = 'hi ' + renderHtml('{job.title}', buildLabelMap(tree))
    expect(serializeNode(div)).toBe('hi {job.title}')
  })
})

describe('ChipTray', () => {
  it('inserts a token on chip click after expanding its folder', () => {
    const onInsert = vi.fn()
    render(<ChipTray groups={buildChipGroups(tree)} onInsert={onInsert} />)
    fireEvent.click(screen.getByText('Job'))
    fireEvent.click(screen.getByText('description'))
    expect(onInsert).toHaveBeenCalledWith('{job.description}', 'Job: description')
  })
})

const listSection = {
  type: 'section', id: 'sec1', name: 'Experience', role: 'experience',
  prompt: 'Lead with impact',
  children: [{
    type: 'list', id: 'lst1', name: 'Experience',
    children: [
      { type: 'group', id: 'e1', name: 'Research Assistant', prompt: 'stress ML pubs',
        children: [{ type: 'field', id: 'f1', name: 'Title', key: 'title', value: 'RA' }] },
      { type: 'group', id: 'e2', name: '', prompt: '',
        children: [{ type: 'field', id: 'f2', name: 'Title', key: 'title', value: 'Barista' }] },
    ],
  }],
}
const listTree = { type: 'root', id: 'r', children: [listSection] }

it('builds one sub-folder per entry with whole-entry + field pills', () => {
  const groups = buildChipGroups(listTree)
  const exp = groups.find((g) => g.label === 'Experience')
  expect(exp.subfolders).toHaveLength(2)
  const first = exp.subfolders[0]
  expect(first.label).toBe('Research Assistant')
  expect(first.chips.map((c) => c.token)).toEqual(['{profile:e1}', '{profile:f1}'])
})

it('labels an unnamed entry from its first field value', () => {
  expect(entryLabel({ name: '', children: [{ value: 'Barista' }] })).toBe('Barista')
})

it('buildFoldedPreview mirrors the Python format', () => {
  expect(buildFoldedPreview(listSection)).toBe(
    '[Experience: Lead with impact [Research Assistant: stress ML pubs]]',
  )
})

it('buildFoldedPreview returns empty when nothing authored', () => {
  expect(buildFoldedPreview({ name: 'Skills', prompt: '', children: [] })).toBe('')
})

describe('PromptField', () => {
  it('renders a stored token as a pill showing its label', () => {
    render(<PromptField value="{profile:fld1}" onChange={vi.fn()} tree={tree} ariaLabel="Section prompt" />)
    expect(screen.getByText('My Skills › Tech')).toBeInTheDocument()
  })

  it('appends a clicked chip token to the value via onChange', () => {
    const onChange = vi.fn()
    render(<PromptField value="" onChange={onChange} tree={tree} ariaLabel="Section prompt" />)
    fireEvent.click(screen.getByText('Job'))
    fireEvent.click(screen.getByText('title'))
    expect(onChange).toHaveBeenCalled()
    expect(onChange.mock.calls.at(-1)[0]).toContain('{job.title}')
  })

  it('opens and closes the pop-out editor', () => {
    render(<PromptField value="x" onChange={vi.fn()} tree={tree} ariaLabel="Section prompt" />)
    fireEvent.click(screen.getByLabelText('Expand editor'))
    expect(screen.getByLabelText('Section prompt (expanded)')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Close editor'))
    expect(screen.queryByLabelText('Section prompt (expanded)')).toBeNull()
  })
})
