import { describe, expect, it, vi } from 'vitest'
import { effectScope } from 'vue'
import { useErrorEnLugar } from './errorEnLugar'

vi.mock('../motion', () => ({
  gsap: { fromTo: vi.fn() },
  isSoft: () => true,
  useGsap: () => ({ run: (fn: () => void) => fn() }),
}))

describe('useErrorEnLugar', () => {
  it('expone error con role alert en el consumidor', () => {
    const scope = effectScope()
    scope.run(() => {
      const { error, mostrar } = useErrorEnLugar()
      mostrar('No pude guardar el orden')
      expect(error.value).toBe('No pude guardar el orden')
    })
    scope.stop()
  })
})
