import { describe, expect, it } from 'vitest'
import { mostrarFranja } from './sinConexion'

describe('mostrarFranja', () => {
  const t0 = 1_000_000

  it('live → false', () => {
    expect(mostrarFranja('live', t0, t0 + 5000)).toBe(false)
  })

  it('reconnecting menos de 3 s → false', () => {
    expect(mostrarFranja('reconnecting', t0, t0 + 2999)).toBe(false)
  })

  it('reconnecting 3 s o más → true', () => {
    expect(mostrarFranja('reconnecting', t0, t0 + 3000)).toBe(true)
  })

  it('connecting 3 s o más → true', () => {
    expect(mostrarFranja('connecting', t0, t0 + 4000)).toBe(true)
  })
})
