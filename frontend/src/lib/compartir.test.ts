import { describe, expect, it } from 'vitest'
import { compartir } from './compartir'

describe('compartir', () => {
  it('devuelve prev cuando next es estructuralmente igual', () => {
    const prev = { a: [1, 2, { x: 1 }], b: 'k' }
    expect(compartir(prev, { a: [1, 2, { x: 1 }], b: 'k' })).toBe(prev)
  })
  it('reutiliza las ramas iguales y crea objeto nuevo solo en la rama que cambió', () => {
    const prev = { l: [{ id: 'a', v: 1 }, { id: 'b', v: 1 }], o: { z: 1 } }
    const out = compartir(prev, { l: [{ id: 'a', v: 1 }, { id: 'b', v: 2 }], o: { z: 1 } })
    expect(out).not.toBe(prev)
    expect(out.l[0]).toBe(prev.l[0])
    expect(out.l[1]).not.toBe(prev.l[1])
    expect(out.o).toBe(prev.o)
  })
  it('un array más largo o más corto es nuevo, pero conserva los elementos iguales', () => {
    const prev = [{ id: 1 }, { id: 2 }]
    const out = compartir(prev, [{ id: 1 }, { id: 2 }, { id: 3 }])
    expect(out).not.toBe(prev)
    expect(out[0]).toBe(prev[0])
    expect(compartir(prev, [{ id: 1 }])).not.toBe(prev)
  })
  it('claves que desaparecen o aparecen cuentan como cambio; undefined y null no se confunden', () => {
    const prev = { a: 1, b: undefined as unknown }
    expect(compartir(prev, { a: 1 } as typeof prev)).not.toBe(prev)
    expect(compartir({ a: null } as { a: unknown }, { a: undefined })).toEqual({ a: undefined })
    expect(compartir({ a: 1 } as Record<string, unknown>, { a: 1, c: 1 })).toEqual({ a: 1, c: 1 })
  })
  it('prev undefined o de otro tipo devuelve next', () => {
    const next = { a: 1 }
    expect(compartir(undefined, next)).toBe(next)
    expect(compartir([1] as unknown, { a: 1 })).toEqual({ a: 1 })
  })
})
