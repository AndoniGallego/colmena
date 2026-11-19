import { describe, expect, it } from 'vitest'
import { mrsAutoSelectRef } from './mrsAutoSelect'

describe('mrsAutoSelectRef', () => {
  it('no elige en celu', () => {
    expect(
      mrsAutoSelectRef({ desktop: false, loaded: true, selected: null, visibleRefs: ['a'] }),
    ).toBeNull()
  })

  it('no elige si la lista no cargó', () => {
    expect(
      mrsAutoSelectRef({ desktop: true, loaded: false, selected: null, visibleRefs: ['a'] }),
    ).toBeNull()
  })

  it('no pisa una selección existente', () => {
    expect(
      mrsAutoSelectRef({ desktop: true, loaded: true, selected: 'b', visibleRefs: ['a', 'b'] }),
    ).toBeNull()
  })

  it('elige el primero visible en escritorio', () => {
    expect(
      mrsAutoSelectRef({ desktop: true, loaded: true, selected: null, visibleRefs: ['x', 'y'] }),
    ).toBe('x')
  })

  it('devuelve null si no hay visibles', () => {
    expect(
      mrsAutoSelectRef({ desktop: true, loaded: true, selected: null, visibleRefs: [] }),
    ).toBeNull()
  })
})
