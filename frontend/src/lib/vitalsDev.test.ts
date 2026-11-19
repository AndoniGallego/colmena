import { afterEach, describe, expect, it, vi } from 'vitest'
import { medirVitalsDev } from './vitalsDev'

afterEach(() => vi.unstubAllGlobals())

describe('medirVitalsDev', () => {
  it('loguea LCP e INP con los observers nativos', () => {
    const cbs: Record<string, (l: { getEntries: () => unknown[] }) => void> = {}
    class PO {
      constructor(private cb: (l: { getEntries: () => unknown[] }) => void) {}
      observe(o: { type: string }) {
        cbs[o.type] = this.cb
      }
    }
    vi.stubGlobal('PerformanceObserver', PO)
    const log = vi.fn()
    medirVitalsDev(log)
    cbs['largest-contentful-paint']({ getEntries: () => [{ startTime: 1234.4 }] })
    cbs.event({ getEntries: () => [{ interactionId: 1, duration: 80, name: 'click' }, { interactionId: 2, duration: 50, name: 'keydown' }] })
    expect(log).toHaveBeenCalledWith('[vitals] LCP', 1234, 'ms')
    expect(log).toHaveBeenCalledWith('[vitals] INP (peor interaccion)', 80, 'ms', 'click')
    expect(log).toHaveBeenCalledTimes(2)
  })

  it('sin PerformanceObserver no rompe', () => {
    vi.stubGlobal('PerformanceObserver', undefined)
    expect(() => medirVitalsDev(vi.fn())).not.toThrow()
  })
})
