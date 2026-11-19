import { describe, expect, it } from 'vitest'
import { estaALaVista } from './aLaVista'

const doc = (visibilityState: DocumentVisibilityState, hasFocus: boolean) =>
  ({ visibilityState, hasFocus: () => hasFocus }) as Pick<Document, 'visibilityState' | 'hasFocus'>

describe('estaALaVista', () => {
  it('sin documento cuenta como a la vista', () => {
    expect(estaALaVista(undefined, true)).toBe(true)
    expect(estaALaVista(undefined, false)).toBe(true)
  })

  it('en móvil solo mira visibilityState', () => {
    expect(estaALaVista(doc('visible', false), false)).toBe(true)
    expect(estaALaVista(doc('hidden', true), false)).toBe(false)
  })

  it('en escritorio exige visible y foco', () => {
    expect(estaALaVista(doc('visible', true), true)).toBe(true)
    expect(estaALaVista(doc('visible', false), true)).toBe(false)
    expect(estaALaVista(doc('hidden', true), true)).toBe(false)
  })
})
