import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { FieldWidget, MarkdownField } from './fieldWidgets'
import * as api from '../../../api'

vi.mock('../../../api', () => ({
  getSkillAliases: vi.fn(async () => ({
    groups: [{ canonical: 'Python', members: ['python', 'py'] }],
  })),
  assignSkillAlias: vi.fn(async (skill, canonical) => ({
    canonical, members: ['python', 'py', skill.toLowerCase()],
  })),
  removeSkillAliasMember: vi.fn(async () => {}),
}))

beforeEach(() => { vi.clearAllMocks() })

const field = (over) => ({
  type: 'field', id: 'f', name: 'X', key: 'x', kind: 'text', value: '',
  visible: true, ...over,
})

describe('FieldWidget', () => {
  it('text: emits string on change', () => {
    const onChange = vi.fn()
    render(<FieldWidget field={field({ kind: 'text', value: 'a' })} onChange={onChange} />)
    fireEvent.change(screen.getByDisplayValue('a'), { target: { value: 'ab' } })
    expect(onChange).toHaveBeenLastCalledWith('ab')
  })

  it('markdown: renders a textarea and emits string', () => {
    const onChange = vi.fn()
    render(<FieldWidget field={field({ kind: 'markdown', value: 'hi' })} onChange={onChange} />)
    const ta = screen.getByRole('textbox')
    expect(ta.tagName).toBe('TEXTAREA')
    fireEvent.change(ta, { target: { value: 'hey' } })
    expect(onChange).toHaveBeenLastCalledWith('hey')
  })

  it('bullets: add and remove a line emit string[]', () => {
    const onChange = vi.fn()
    render(<FieldWidget field={field({ kind: 'bullets', value: ['one'] })} onChange={onChange} />)
    fireEvent.click(screen.getByText('+ Add bullet'))
    expect(onChange).toHaveBeenLastCalledWith(['one', ''])
    onChange.mockClear()
    fireEvent.click(screen.getByLabelText('Remove bullet 1'))
    expect(onChange).toHaveBeenLastCalledWith([])
  })

  it('bullets: editing a line emits the updated array', () => {
    const onChange = vi.fn()
    render(<FieldWidget field={field({ kind: 'bullets', value: ['one'] })} onChange={onChange} />)
    fireEvent.change(screen.getByDisplayValue('one'), { target: { value: 'two' } })
    expect(onChange).toHaveBeenLastCalledWith(['two'])
  })

  it('taglist: add via Enter and remove a chip emit string[]', () => {
    const onChange = vi.fn()
    render(<FieldWidget field={field({ kind: 'taglist', value: ['Python'] })} onChange={onChange} />)
    const input = screen.getByPlaceholderText('Add…')
    fireEvent.change(input, { target: { value: 'SQL' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onChange).toHaveBeenLastCalledWith(['Python', 'SQL'])
    onChange.mockClear()
    fireEvent.click(screen.getByLabelText('Remove Python'))
    expect(onChange).toHaveBeenLastCalledWith([])
  })

  it('taglist: clicking a chip opens the edit modal; ✕ still deletes', async () => {
    const onChange = vi.fn()
    render(<FieldWidget field={field({ kind: 'taglist', value: ['Python'] })} onChange={onChange} />)
    // ✕ deletes, does not open the modal
    fireEvent.click(screen.getByLabelText('Remove Python'))
    expect(onChange).toHaveBeenLastCalledWith([])
    expect(screen.queryByText('Edit tag')).toBeNull()
    // clicking the chip label opens the modal
    fireEvent.click(screen.getByText('Python'))
    expect(screen.getByText('Edit tag')).toBeInTheDocument()
    // let the async alias load settle (avoids act() warnings)
    expect(await screen.findByText('py')).toBeInTheDocument()
  })

  it('taglist modal: renames the chip and loads/edits aliases', async () => {
    const onChange = vi.fn()
    render(<FieldWidget field={field({ kind: 'taglist', value: ['Python'] })} onChange={onChange} />)
    fireEvent.click(screen.getByText('Python'))
    // alias group loads (canonical self 'python' filtered out, 'py' shown)
    expect(await screen.findByText('py')).toBeInTheDocument()
    // add an alias
    fireEvent.change(screen.getByPlaceholderText('Add alias…'), { target: { value: 'py3' } })
    fireEvent.click(screen.getByText('Add'))
    await waitFor(() => expect(screen.getByText('py3')).toBeInTheDocument())
    // rename the chip
    fireEvent.change(screen.getByDisplayValue('Python'), { target: { value: 'Python 3' } })
    fireEvent.click(screen.getByText('Save'))
    await waitFor(() => expect(onChange).toHaveBeenLastCalledWith(['Python 3']))
  })

  it('taglist modal: renaming the canonical migrates the whole alias group', async () => {
    const onChange = vi.fn()
    render(<FieldWidget field={field({ kind: 'taglist', value: ['Python'] })} onChange={onChange} />)
    fireEvent.click(screen.getByText('Python'))
    expect(await screen.findByText('py')).toBeInTheDocument()
    fireEvent.change(screen.getByDisplayValue('Python'), { target: { value: 'Python 3' } })
    fireEvent.click(screen.getByText('Save'))
    // canonical 'Python' + member 'py' both re-assigned to the new canonical
    await waitFor(() => {
      expect(api.assignSkillAlias).toHaveBeenCalledWith('Python', 'Python 3')
      expect(api.assignSkillAlias).toHaveBeenCalledWith('py', 'Python 3')
    })
    expect(onChange).toHaveBeenLastCalledWith(['Python 3'])
  })

  it('taglist modal: clicking an alias swaps focus so it can be renamed', async () => {
    const onChange = vi.fn()
    render(<FieldWidget field={field({ kind: 'taglist', value: ['Python'] })} onChange={onChange} />)
    fireEvent.click(screen.getByText('Python'))
    // Name field starts on the canonical
    expect(screen.getByDisplayValue('Python')).toBeInTheDocument()
    // click the alias to focus it
    fireEvent.click(await screen.findByText('py'))
    expect(screen.getByDisplayValue('py')).toBeInTheDocument()
    expect(screen.getByText(/Renaming alias of/)).toBeInTheDocument()
    // rename the alias in place: remove old + assign new under same canonical
    fireEvent.change(screen.getByDisplayValue('py'), { target: { value: 'py3' } })
    fireEvent.click(screen.getByText('Save'))
    await waitFor(() => {
      expect(api.removeSkillAliasMember).toHaveBeenCalledWith('py')
      expect(api.assignSkillAlias).toHaveBeenCalledWith('py3', 'Python')
    })
    // renaming an alias does NOT touch the field-value chip
    expect(onChange).not.toHaveBeenCalled()
  })
})

describe('TagListField valueOnly mode', () => {
  it('suppresses add/remove/rename and alias modal', () => {
    const onChange = vi.fn()
    render(<FieldWidget field={field({ kind: 'taglist', value: ['Python', 'SQL'] })} onChange={onChange} valueOnly />)
    // Tags are rendered as plain text spans, not buttons
    expect(screen.getByText('Python')).toBeTruthy()
    expect(screen.getByText('Python').tagName).toBe('SPAN')
    // No add input, no remove buttons
    expect(screen.queryByPlaceholderText('Add…')).toBeNull()
    expect(screen.queryByLabelText('Remove Python')).toBeNull()
    // Clicking the tag text does not open the alias modal
    fireEvent.click(screen.getByText('Python'))
    expect(screen.queryByText('Edit tag')).toBeNull()
  })
})

describe('MarkdownField pop-out', () => {
  it('expands to a large editor and edits there', () => {
    const onChange = vi.fn()
    render(<MarkdownField value="hello" onChange={onChange} />)
    fireEvent.click(screen.getByLabelText('Expand field editor'))
    const big = screen.getByLabelText('Expanded field editor')
    fireEvent.change(big, { target: { value: 'hello world' } })
    expect(onChange).toHaveBeenLastCalledWith('hello world')
    fireEvent.click(screen.getByLabelText('Close field editor'))
    expect(screen.queryByLabelText('Expanded field editor')).toBeNull()
  })
})
