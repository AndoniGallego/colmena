import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Api } from '../api/types'

vi.hoisted(() => {
  vi.stubGlobal('window', { matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }), addEventListener() {} })
})
import { init, markSeen } from './app'

describe('markSeen', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('agrupa ráfagas de la misma sesión', () => {
    const f = vi.fn().mockResolvedValue(undefined)
    init({ markSeen: f } as unknown as Api)
    markSeen('a')
    markSeen('a')
    vi.advanceTimersByTime(400)
    expect(f).toHaveBeenCalledTimes(1)
  })

  it('no pierde el visto de una sesión al marcar otra enseguida', () => {
    const f = vi.fn().mockResolvedValue(undefined)
    init({ markSeen: f } as unknown as Api)
    markSeen('a')
    markSeen('b')
    vi.advanceTimersByTime(400)
    expect(f).toHaveBeenCalledWith('a')
    expect(f).toHaveBeenCalledWith('b')
  })
})
