import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createHold } from './hold'

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

describe('hold to confirm', () => {
  it('confirms only after sustaining the full time', () => {
    const done = vi.fn()
    const h = createHold(1000, done)
    h.start()
    vi.advanceTimersByTime(999)
    expect(done).not.toHaveBeenCalled()
    vi.advanceTimersByTime(2)
    expect(done).toHaveBeenCalledTimes(1)
    expect(h.active).toBe(false)
  })
  it('releasing early cancels and never confirms', () => {
    const done = vi.fn()
    const h = createHold(1000, done)
    h.start()
    vi.advanceTimersByTime(600)
    h.cancel()
    vi.advanceTimersByTime(2000)
    expect(done).not.toHaveBeenCalled()
  })
  it('a second start while holding does not double fire', () => {
    const done = vi.fn()
    const h = createHold(500, done)
    h.start()
    h.start()
    vi.advanceTimersByTime(2000)
    expect(done).toHaveBeenCalledTimes(1)
  })
})
