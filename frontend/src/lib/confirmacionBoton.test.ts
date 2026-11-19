import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { effectScope } from 'vue'
import { useConfirmacionBoton } from './confirmacionBoton'

vi.mock('../motion', () => ({
  gsap: { fromTo: vi.fn() },
  haptic: vi.fn(),
  isSoft: () => true,
  useGsap: () => ({ run: (fn: () => void) => fn() }),
}))

describe('useConfirmacionBoton', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('cambia a estado hecho y vuelve', async () => {
    const scope = effectScope()
    const out = await scope.run(async () => {
      const c = useConfirmacionBoton(500)
      await c.pulsarHecho()
      expect(c.hecho.value).toBe(true)
      vi.advanceTimersByTime(500)
      expect(c.hecho.value).toBe(false)
      return c
    })
    scope.stop()
    expect(out).toBeTruthy()
  })
})
