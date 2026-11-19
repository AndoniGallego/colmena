import { describe, expect, it } from 'vitest'
import { mover, teclaMovimiento } from './cambios'

describe('mover', () => {
  it('avanza y retrocede sin salirse de la lista', () => {
    expect(mover(0, 1, 3)).toBe(1)
    expect(mover(2, 1, 3)).toBe(2)
    expect(mover(0, -1, 3)).toBe(0)
    expect(mover(2, -1, 3)).toBe(1)
  })
  it('sin selección, abajo elige el primero y arriba el último', () => {
    expect(mover(-1, 1, 3)).toBe(0)
    expect(mover(-1, -1, 3)).toBe(2)
  })
  it('lista vacía', () => {
    expect(mover(-1, 1, 0)).toBe(-1)
  })
})

describe('teclaMovimiento', () => {
  it('j y flecha abajo bajan; k y flecha arriba suben', () => {
    expect(teclaMovimiento('j')).toBe(1)
    expect(teclaMovimiento('ArrowDown')).toBe(1)
    expect(teclaMovimiento('k')).toBe(-1)
    expect(teclaMovimiento('ArrowUp')).toBe(-1)
    expect(teclaMovimiento('x')).toBe(0)
  })
})
