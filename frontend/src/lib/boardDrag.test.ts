import { describe, expect, it } from 'vitest'
import { corrimientoPx, deltaArrastreY, indicesCorrimientoArrastre } from './boardDrag'

describe('boardDrag', () => {
  it('deltaArrastreY sigue el dedo', () => {
    expect(deltaArrastreY(120, 100)).toBe(20)
    expect(deltaArrastreY(80, 100)).toBe(-20)
  })

  it('indicesCorrimientoArrastre entre origen y destino', () => {
    expect(indicesCorrimientoArrastre(0, 2, 4)).toEqual([1, 2])
    expect(indicesCorrimientoArrastre(3, 1, 4)).toEqual([1, 2])
    expect(indicesCorrimientoArrastre(1, 1, 3)).toEqual([])
  })

  it('corrimientoPx abre hueco', () => {
    const step = 50
    expect(corrimientoPx(0, 2, 1, step)).toBe(-50)
    expect(corrimientoPx(0, 2, 0, step)).toBe(0)
    expect(corrimientoPx(3, 1, 2, step)).toBe(50)
  })
})
