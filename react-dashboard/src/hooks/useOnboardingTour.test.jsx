import { describe, it, expect, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useOnboardingTour } from './useOnboardingTour'

describe('useOnboardingTour', () => {
  it('starts idle', () => {
    const { result } = renderHook(() => useOnboardingTour({ onStateChange: vi.fn() }))
    expect(result.current.run).toBe(false)
  })

  it('start runs the tour', () => {
    const { result } = renderHook(() => useOnboardingTour({ onStateChange: vi.fn() }))
    act(() => result.current.start())
    expect(result.current.run).toBe(true)
  })

  it('finish persists completed and stops', () => {
    const onStateChange = vi.fn()
    const { result } = renderHook(() => useOnboardingTour({ onStateChange }))
    act(() => result.current.start())
    act(() => result.current.finish())
    expect(onStateChange).toHaveBeenCalledWith('completed')
    expect(result.current.run).toBe(false)
  })

  it('skip persists skipped and stops', () => {
    const onStateChange = vi.fn()
    const { result } = renderHook(() => useOnboardingTour({ onStateChange }))
    act(() => result.current.start())
    act(() => result.current.skip())
    expect(onStateChange).toHaveBeenCalledWith('skipped')
    expect(result.current.run).toBe(false)
  })
})
