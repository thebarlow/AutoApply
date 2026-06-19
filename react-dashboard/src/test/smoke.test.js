import { describe, it, expect } from 'vitest'

describe('test harness', () => {
  it('runs and supports jsdom', () => {
    const el = document.createElement('div')
    el.textContent = 'ok'
    expect(el.textContent).toBe('ok')
  })
})
