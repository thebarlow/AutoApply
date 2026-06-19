import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { FieldWidget } from './fieldWidgets'

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
})
