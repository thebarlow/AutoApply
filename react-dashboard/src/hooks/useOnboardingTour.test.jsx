import { describe, it, expect, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useOnboardingTour } from './useOnboardingTour'

describe('useOnboardingTour', () => {
  it('starts idle', () => {
    const { result } = renderHook(() =>
      useOnboardingTour({ tourState: 'unstarted', jobCount: 0, onStateChange: vi.fn() }))
    expect(result.current.run).toBe(false)
    expect(result.current.part).toBe(null)
  })

  it('launchPart1 runs part 1', () => {
    const { result } = renderHook(() =>
      useOnboardingTour({ tourState: 'unstarted', jobCount: 0, onStateChange: vi.fn() }))
    act(() => result.current.launchPart1())
    expect(result.current.run).toBe(true)
    expect(result.current.part).toBe(1)
  })

  it('finishPart1 persists part1_done and stops', () => {
    const onStateChange = vi.fn()
    const { result } = renderHook(() =>
      useOnboardingTour({ tourState: 'unstarted', jobCount: 0, onStateChange }))
    act(() => result.current.launchPart1())
    act(() => result.current.finishPart1())
    expect(onStateChange).toHaveBeenCalledWith('part1_done')
    expect(result.current.run).toBe(false)
  })

  it('finishTour persists completed', () => {
    const onStateChange = vi.fn()
    const { result } = renderHook(() =>
      useOnboardingTour({ tourState: 'part1_done', jobCount: 1, onStateChange }))
    act(() => result.current.launchPart2())
    act(() => result.current.finishTour())
    expect(onStateChange).toHaveBeenCalledWith('completed')
    expect(result.current.run).toBe(false)
  })

  it('skip persists skipped', () => {
    const onStateChange = vi.fn()
    const { result } = renderHook(() =>
      useOnboardingTour({ tourState: 'unstarted', jobCount: 0, onStateChange }))
    act(() => result.current.launchPart1())
    act(() => result.current.skip())
    expect(onStateChange).toHaveBeenCalledWith('skipped')
    expect(result.current.run).toBe(false)
  })

  it('replay runs without changing stored state until finish', () => {
    const onStateChange = vi.fn()
    const { result } = renderHook(() =>
      useOnboardingTour({ tourState: 'completed', jobCount: 2, onStateChange }))
    act(() => result.current.replay())
    expect(result.current.run).toBe(true)
    expect(result.current.part).toBe(1)
    expect(onStateChange).not.toHaveBeenCalled()
  })
})
