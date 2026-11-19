import { describe, expect, it } from 'vitest'
import { aplicarBarraScroll, medirBarraScroll } from './scrollbar'

function fakeDoc(offset: number, client: number) {
  const props: Record<string, string> = {}
  let removed = false
  const div = { style: { cssText: '' }, offsetWidth: offset, clientWidth: client, remove: () => { removed = true } }
  const doc = {
    createElement: () => div,
    body: { appendChild: () => div },
    documentElement: { style: { setProperty: (k: string, v: string) => { props[k] = v } } },
  } as unknown as Document
  return { doc, props, removed: () => removed }
}

describe('barra de scroll', () => {
  it('mide la diferencia entre ancho total y ancho útil y limpia el nodo', () => {
    const f = fakeDoc(100, 89)
    expect(medirBarraScroll(f.doc)).toBe(11)
    expect(f.removed()).toBe(true)
  })
  it('en celu (barra superpuesta) da 0, nunca negativo', () => {
    expect(medirBarraScroll(fakeDoc(100, 100).doc)).toBe(0)
    expect(medirBarraScroll(fakeDoc(100, 104).doc)).toBe(0)
  })
  it('publica --sbw en el documento', () => {
    const f = fakeDoc(100, 92)
    aplicarBarraScroll(f.doc)
    expect(f.props['--sbw']).toBe('8px')
  })
})
