import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MoveButtons, VisibleToggle, RenameLabel, RemoveButton, AddButton } from './structuralControls'

describe('MoveButtons', () => {
  it('disables up at top and down at bottom', () => {
    const onUp = vi.fn(); const onDown = vi.fn()
    render(<MoveButtons canUp={false} canDown onUp={onUp} onDown={onDown} />)
    fireEvent.click(screen.getByLabelText('Move up'))
    expect(onUp).not.toHaveBeenCalled()
    fireEvent.click(screen.getByLabelText('Move down'))
    expect(onDown).toHaveBeenCalled()
  })
})

describe('VisibleToggle', () => {
  it('toggles and labels by state', () => {
    const onToggle = vi.fn()
    render(<VisibleToggle visible onToggle={onToggle} />)
    fireEvent.click(screen.getByLabelText('Hide'))
    expect(onToggle).toHaveBeenCalled()
  })
})

describe('RenameLabel', () => {
  it('commits on Enter when editable', () => {
    const onRename = vi.fn()
    render(<RenameLabel name="Old" editable onRename={onRename} />)
    fireEvent.click(screen.getByText('Old'))
    const input = screen.getByDisplayValue('Old')
    fireEvent.change(input, { target: { value: 'New' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onRename).toHaveBeenLastCalledWith('New')
  })

  it('cancels on Escape', () => {
    const onRename = vi.fn()
    render(<RenameLabel name="Old" editable onRename={onRename} />)
    fireEvent.click(screen.getByText('Old'))
    const input = screen.getByDisplayValue('Old')
    fireEvent.change(input, { target: { value: 'X' } })
    fireEvent.keyDown(input, { key: 'Escape' })
    expect(onRename).not.toHaveBeenCalled()
    expect(screen.getByText('Old')).toBeInTheDocument()
  })

  it('is static when not editable', () => {
    render(<RenameLabel name="Fixed" editable={false} onRename={vi.fn()} />)
    fireEvent.click(screen.getByText('Fixed'))
    expect(screen.queryByDisplayValue('Fixed')).toBeNull()
  })
})

describe('RemoveButton', () => {
  it('requires a confirm click', () => {
    const onRemove = vi.fn()
    render(<RemoveButton onRemove={onRemove} label="Remove section" />)
    fireEvent.click(screen.getByLabelText('Remove section'))
    expect(onRemove).not.toHaveBeenCalled()
    fireEvent.click(screen.getByText('Confirm?'))
    expect(onRemove).toHaveBeenCalled()
  })
})

describe('AddButton', () => {
  it('fires onClick', () => {
    const onClick = vi.fn()
    render(<AddButton label="+ Add field" onClick={onClick} />)
    fireEvent.click(screen.getByText('+ Add field'))
    expect(onClick).toHaveBeenCalled()
  })
})
